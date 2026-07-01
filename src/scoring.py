"""
src/scoring.py

Schema TomAta e chains LangChain para pontuar atas do Copom com LLMs.

Fluxo de dados:
    texto_ab (str)
        → prompt  (ChatPromptTemplate)
        → LLM.with_structured_output(TomAta)   ← força tool-calling nativo
        → TomAta(score=float)                   ← zero parsing manual

Por que with_structured_output?
    O modelo não "responde com um float em texto" — ele preenche um parâmetro
    tipado de uma function call. O framework valida range/tipo antes de retornar.
    Isso elimina try/except em cima de regex, que quebraria em respostas longas.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Annotated

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Caminhos de cache de scores (nível 3 da hierarquia de cache do projeto)
# ---------------------------------------------------------------------------

_CACHE_GEMINI = Path("output/scores/scores_gemini_cache.csv")
_CACHE_CLAUDE = Path("output/scores/scores_claude_cache.csv")
_CACHE_OPENAI = Path("output/scores/scores_openai_cache.csv")

# ---------------------------------------------------------------------------
# Schema de saída estruturada
# ---------------------------------------------------------------------------

class TomAta(BaseModel):
    """Tom monetário de uma ata do Copom — saída estruturada do LLM."""

    score: Annotated[
        float,
        Field(
            ge=-3.0,
            le=3.0,
            description=(
                "Score de tom monetário: "
                "−3.0 = fortemente dovish, 0.0 = neutro, +3.0 = fortemente hawkish. "
                "Precisão de 0.25. Veja INSTRUCOES_SISTEMA para âncoras completas."
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Instruções de sistema — compartilhadas pelos três provedores
# ---------------------------------------------------------------------------
# Separar system/human é essencial: cada provider mapeia para o campo nativo
# correto (OpenAI role:system, Anthropic system:, Gemini systemInstruction:),
# o que melhora o seguimento de instruções em relação a tudo numa mensagem human.

INSTRUCOES_SISTEMA = """\
Você é um economista sênior especializado em política monetária do Banco Central \
do Brasil, com profundo conhecimento das atas do Copom desde 2000, dos comunicados \
de política monetária e do framework de metas de inflação do BCB.

Sua tarefa é ler um trecho das seções A (conjuntura econômica) e B (cenários e \
riscos) de uma ata do Copom e atribuir um SCORE DE TOM MONETÁRIO na escala \
contínua de −3.0 a +3.0, conforme as âncoras abaixo.

ÂNCORAS DA ESCALA
─────────────────
 −3.0  FORTEMENTE DOVISH
       Linguagem explicitamente afrouxadora. Projeções de inflação muito abaixo da meta. \
Riscos baixistas dominantes e não contestados. Menção a recessão, deflação ou \
colapso da demanda. Forward guidance claro de cortes iminentes ou ciclo longo de \
reduções.

 −2.0  DOVISH
       Viés de afrouxamento claro. Inflação convergindo para abaixo da meta. Balanço \
de riscos inclinado para o lado negativo. Atividade econômica fraca mencionada \
de forma explícita e recorrente. Expectativas ancoradas ou abaixo da meta.

 −1.0  LEVEMENTE DOVISH
       Inclinação cautelosa para afrouxamento. Inflação dentro da meta com riscos \
baixistas presentes. Comitê mais preocupado com atividade do que com inflação. \
Forward guidance suave: "monitorar", "acompanhar com atenção".

  0.0  NEUTRO / DATA-DEPENDENT
       Balanço equilibrado entre riscos altistas e baixistas. Sem viés direcional \
claro. Linguagem condicional: "dependendo da evolução dos dados", "avaliar o \
conjunto de informações". Inflação na meta com expectativas bem ancoradas.

 +1.0  LEVEMENTE HAWKISH
       Vigilância inflacionária presente mas sem comprometimento explícito. Inflação \
acima da meta ou riscos altistas emergentes. Expectativas com alguma desancoragem \
incipiente. Menção à necessidade de "cautela" ou "atenção especial" aos preços.

 +2.0  HAWKISH
       Viés de aperto claro. Inflação persistentemente acima da meta. Balanço de \
riscos inclinado para cima. Expectativas desancoradas mencionadas explicitamente. \
Forward guidance sinalizando altas ou manutenção em patamar elevado por longo período.

 +3.0  FORTEMENTE HAWKISH
       Combate ativo e urgente à inflação. Aperto agressivo sinalizado ou em curso. \
Inflação muito acima da meta com perspectiva de persistência. Expectativas muito \
desancoradas. Comprometimento explícito com ciclo longo de altas ou elevações \
de grande magnitude.

REGRAS OBRIGATÓRIAS
───────────────────
1. Avalie APENAS o tom implícito nas seções de diagnóstico e balanço de riscos. \
   NÃO se baseie na decisão de taxa já anunciada — ela não deve influenciar o score.

2. Foque nos seguintes sinais linguísticos:
   • Perspectivas para inflação (acima/abaixo/na meta, trajetória)
   • Ancoragem de expectativas (bem ancoradas / desancoradas / incipiente)
   • Balanço de riscos (altistas vs. baixistas, simétrico vs. assimétrico)
   • Forward guidance implícito ou explícito ("prudência", "tempestividade", "vigilância")

3. Use valores intermediários (ex.: −1.5, +0.5, +2.25) quando o texto estiver \
   entre dois pontos de ancoragem. Precisão de 0.25.

4. Consistência: atas com linguagem similar devem receber scores próximos, \
   independentemente da decisão final de taxa.

5. Se riscos altistas e baixistas forem mencionados em intensidade equivalente, \
   score próximo de 0.0.\
"""

# ---------------------------------------------------------------------------
# Templates — um por provedor
# ---------------------------------------------------------------------------

# Gemini e OpenAI: tuple ("system", str) — cada provider converte para seu campo nativo
_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", INSTRUCOES_SISTEMA),
    ("human",  "TRECHO DA ATA:\n{texto_ab}"),
])

# Anthropic: SystemMessage com content como lista de blocos tipados, o que permite
# anexar cache_control a cada bloco individualmente.
# cache_control {"type": "ephemeral"} instrui a API a armazenar o bloco no
# prompt cache por até 5 minutos. Da 2ª chamada em diante:
#   • ~90% de desconto no custo de input tokens do system prompt
#   • TTFT (time-to-first-token) menor — tokens cacheados são pré-computados
# Mínimo para caching: 1024 tokens de input (INSTRUCOES_SISTEMA tem ~600 tokens,
# portanto o bloco + texto da ata ultrapassa o limiar facilmente).
_TEMPLATE_CLAUDE = ChatPromptTemplate.from_messages([
    SystemMessage(
        content=[
            {
                "type": "text",
                "text": INSTRUCOES_SISTEMA,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    ),
    ("human", "TRECHO DA ATA:\n{texto_ab}"),
])

# ---------------------------------------------------------------------------
# Fábrica de chains — uma por provedor
# ---------------------------------------------------------------------------

def criar_scorer_gemini(
    model: str = "gemini-flash-lite-latest",
    temperature: float = 0.0,
):
    """
    Chain Gemini: {"texto_ab": str} → TomAta.

    Como funciona internamente:
    1. _TEMPLATE formata o prompt com o trecho da ata.
    2. ChatGoogleGenerativeAI.with_structured_output(TomAta) converte TomAta
       num tool/function schema e instrui o Gemini a chamar essa função.
    3. O Gemini retorna um JSON com o campo "score" preenchido.
    4. LangChain desserializa em TomAta e valida ge=-3/le=+3 via Pydantic.
       Se o modelo violar o range, Pydantic lança ValidationError antes de
       o dado chegar ao seu código.

    Usa GOOGLE_API_KEY de .env.gemini.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    load_dotenv(Path(".env.gemini"), override=True)
    # Aceita GOOGLE_API_KEY (LangChain padrão) ou GEMINI_API_KEY (alias comum)
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "Chave do Gemini não encontrada. "
            "Adicione GOOGLE_API_KEY=<sua-chave> (ou GEMINI_API_KEY) em .env.gemini."
        )

    llm = ChatGoogleGenerativeAI(
        model=model,
        temperature=temperature,
        google_api_key=api_key,
    )

    # A chain resultante é chamável: chain.invoke({"texto_ab": texto}) → TomAta
    return _TEMPLATE | llm.with_structured_output(TomAta)


def criar_scorer_claude(
    model: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.0,
):
    """
    Chain Anthropic: {"texto_ab": str} → TomAta.

    Usa _TEMPLATE_CLAUDE (SystemMessage com cache_control ephemeral).
    Requer langchain-anthropic >= 0.1.x e acesso ao beta prompt-caching.
    Chave lida de .env.claude (ANTHROPIC_API_KEY ou ANTHROPIC_KEY).
    """
    from langchain_anthropic import ChatAnthropic

    load_dotenv(Path(".env.claude"), override=True)
    api_key = os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY não encontrada em .env.claude.")

    llm = ChatAnthropic(
        model=model,
        temperature=temperature,
        anthropic_api_key=api_key,
    )
    # _TEMPLATE_CLAUDE já carrega cache_control no bloco de system —
    # a Anthropic detecta automaticamente e ativa o caching sem header extra
    return _TEMPLATE_CLAUDE | llm.with_structured_output(TomAta)


def criar_scorer_openai(
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
):
    """
    Chain OpenAI: {"texto_ab": str} → TomAta.

    with_structured_output usa tool calling nativo (parallel_tool_calls=False
    é forçado internamente pelo LangChain para evitar múltiplas tool calls num
    mesmo turno). Sem caching explícito — a OpenAI aplica prompt caching
    automático para prefixos idênticos com >= 1024 tokens (sem configuração).
    Chave lida de .env.openai.
    """
    from langchain_openai import ChatOpenAI

    load_dotenv(Path(".env.openai"), override=True)
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY não encontrada em .env.openai.")

    llm = ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
    )
    return _TEMPLATE | llm.with_structured_output(TomAta)


# ---------------------------------------------------------------------------
# Cache CSV helpers (compartilhados pelos três provedores)
# ---------------------------------------------------------------------------

def _carregar_cache_csv(path: Path) -> dict[int, dict]:
    """Carrega CSV de scores como {nro_reuniao: {nro_reuniao, data, score}}."""
    if not path.exists():
        return {}
    df = pd.read_csv(path, dtype={"nro_reuniao": int, "score": float})
    return {
        int(r.nro_reuniao): {
            "nro_reuniao": int(r.nro_reuniao),
            "data": str(r.data),
            "score": float(r.score),
        }
        for _, r in df.iterrows()
    }


def _salvar_cache_csv(cache: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = sorted(cache.values(), key=lambda x: x["nro_reuniao"])
    pd.DataFrame(rows).to_csv(path, index=False, float_format="%.2f")


def _registrar_erros_scoring(erros: list[str], provedor: str = "gemini") -> None:
    """Appenda erros de scoring em logs/erros.md sem derrubar o pipeline."""
    Path("logs").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    linhas = [f"\n## Scoring {provedor} — {ts}\n"] + [f"- {e}\n" for e in erros]
    with open("logs/erros.md", "a", encoding="utf-8") as f:
        f.writelines(linhas)
    log.warning("%d erro(s) registrado(s) em logs/erros.md.", len(erros))


# ---------------------------------------------------------------------------
# Loop de inferência — compartilhado pelos três provedores
# ---------------------------------------------------------------------------

def _imprimir_linha(nro: int, data: str, score: float, origem: str) -> None:
    if score > 0.5:
        tom = f"hawkish {'▲' * min(int(score), 3)}"
    elif score < -0.5:
        tom = f"dovish  {'▼' * min(int(-score), 3)}"
    else:
        tom = "neutro  ●"
    print(f"{nro:>5}  {data:<12}  {score:>+6.2f}  {origem:<6}  {tom}")


def _loop_inferencia(
    docs: list,
    scorer_retry,
    cache: dict,
    cache_path: Path,
    label: str,
) -> pd.DataFrame:
    """
    Loop interno compartilhado por pontuar_gemini / pontuar_claude / pontuar_openai.

    Parâmetros
    ----------
    docs         : lista de Document
    scorer_retry : chain já envolvida com .with_retry(...)
    cache        : dict carregado por _carregar_cache_csv (modificado in-place)
    cache_path   : destino do CSV (salvo só se novos > 0)
    label        : string de cabeçalho, ex. "Gemini · gemini-flash-lite-latest"

    Estratégia de cache
    -------------------
    • nro_reuniao presente → reaproveita; NÃO toca a API.
    • nro_reuniao ausente  → scorer_retry.invoke(texto_ab) com até 6 tentativas
      (backoff exponencial + jitter); clipa score em [−3, +3]; persiste no cache.
    • Erros por ata: registra em logs/erros.md e continua o loop.
    • CSV salvo APENAS se houve ao menos 1 score novo.
    """
    novos  = 0
    erros  = []
    docs_s = sorted(docs, key=lambda d: d.metadata["nro_reuniao"])

    print(f"\n{label} · {len(docs)} ata(s)")
    print(f"{'Nro':>5}  {'Data':<12}  {'Score':>6}  {'Origem':<6}  Tom")
    print("─" * 44)

    for doc in docs_s:
        nro  = int(doc.metadata["nro_reuniao"])
        data = doc.metadata["data"]

        if nro in cache:
            _imprimir_linha(nro, data, cache[nro]["score"], "cache")
            continue

        print(f"{nro:>5}  {data:<12}  {'...':>6}  LLM    ⟳", end="\r", flush=True)
        try:
            resultado = scorer_retry.invoke({"texto_ab": doc.page_content})
            score = float(np.clip(resultado.score, -3.0, 3.0))
            cache[nro] = {"nro_reuniao": nro, "data": data, "score": score}
            novos += 1
            _imprimir_linha(nro, data, score, "LLM")
        except Exception as exc:
            msg = f"Reunião {nro} ({data}): {type(exc).__name__}: {exc}"
            erros.append(msg)
            log.error(msg)
            print(f"{nro:>5}  {data:<12}  {'ERRO':>6}  LLM    ✗  {type(exc).__name__}")

    print("─" * 44)
    if novos > 0:
        _salvar_cache_csv(cache, cache_path)
        print(f"✓ {cache_path}  [{novos} novo(s) / {len(cache)} total]")
    else:
        print(f"✓ Cache sem alterações — {cache_path.name} não foi modificado.")

    if erros:
        provedor = label.split(" ·")[0].lower()
        _registrar_erros_scoring(erros, provedor=provedor)
        print(f"✗ {len(erros)} erro(s) em logs/erros.md")

    return pd.DataFrame(
        sorted(cache.values(), key=lambda x: x["nro_reuniao"]),
        columns=["nro_reuniao", "data", "score"],
    )


# Palavras-chave que identificam erros de billing/quota — falha permanente, não transitória.
# Esses erros não devem ser retentados: quota esgotada não resolve com espera.
_BILLING_MSGS = (
    "credit balance",     # Anthropic
    "insufficient_quota", # OpenAI
    "quota exceeded",
    "billing",
)


class _TransientError(Exception):
    """Wrapper interno: só esta classe é retentada pelo with_retry."""


def _com_retry(scorer):
    """
    Envolve scorer com backoff exponencial + jitter (até 6 tentativas).

    Distingue erros:
      • Billing/quota (400/429 permanente) → re-lança imediatamente, SEM retry.
      • Erros transitórios (5xx, timeout, conexão) → encapsula em _TransientError
        para que with_retry retentar com espera 2^n + jitter segundos.

    Sem essa distinção, uma chave sem crédito esgotaria os 6 retries com
    ~60 s de espera acumulada por ata antes de registrar o erro.
    """
    from langchain_core.runnables import RunnableLambda

    def _guarded(inputs):
        try:
            return scorer.invoke(inputs)
        except Exception as exc:
            msg = str(exc).lower()
            if any(k in msg for k in _BILLING_MSGS):
                raise  # billing: falha imediata, sem retry
            raise _TransientError(str(exc)) from exc  # transitório: retry

    return RunnableLambda(_guarded).with_retry(
        stop_after_attempt=6,
        wait_exponential_jitter=True,
        retry_if_exception_type=(_TransientError,),  # só retentar erros transitórios
    )


# ---------------------------------------------------------------------------
# Pontuação por provedor
# ---------------------------------------------------------------------------

def pontuar_gemini(
    docs: list,
    cache_path: Path = _CACHE_GEMINI,
    model: str = "gemini-flash-lite-latest",
    temperature: float = 0.0,
) -> pd.DataFrame:
    """Pontua atas com Gemini. Cache incremental em scores_gemini_cache.csv."""
    cache = _carregar_cache_csv(cache_path)
    scorer = _com_retry(criar_scorer_gemini(model=model, temperature=temperature))
    return _loop_inferencia(docs, scorer, cache, cache_path, f"Gemini · {model}")


def pontuar_claude(
    docs: list,
    cache_path: Path = _CACHE_CLAUDE,
    model: str = "claude-haiku-4-5-20251001",
    temperature: float = 0.0,
) -> pd.DataFrame:
    """
    Pontua atas com Claude Haiku. Cache incremental em scores_claude_cache.csv.

    Prompt caching Anthropic
    ------------------------
    _TEMPLATE_CLAUDE envia INSTRUCOES_SISTEMA com cache_control {"type": "ephemeral"}.
    A Anthropic armazena o bloco de sistema por 5 minutos (TTL ephemeral).

    Efeito prático num batch de atas:
      • 1ª chamada: cobra os tokens do system prompt normalmente (cache miss).
      • 2ª–N atas:  cobra ~10% do custo de input do system (cache hit).
      • TTFT menor: tokens cacheados são pré-computados, não tokenizados na hora.

    O mínimo para ativar o cache é 1024 tokens de input total. Como
    INSTRUCOES_SISTEMA (~600 tokens) + texto da ata (~1000 tokens) ultrapassa
    esse limiar, o cache ativa já na segunda chamada do batch.
    """
    cache = _carregar_cache_csv(cache_path)
    scorer = _com_retry(criar_scorer_claude(model=model, temperature=temperature))
    return _loop_inferencia(docs, scorer, cache, cache_path, f"Claude · {model}")


def pontuar_openai(
    docs: list,
    cache_path: Path = _CACHE_OPENAI,
    model: str = "gpt-4.1-mini",
    temperature: float = 0.0,
) -> pd.DataFrame:
    """Pontua atas com GPT-4.1-mini. Cache incremental em scores_openai_cache.csv."""
    cache = _carregar_cache_csv(cache_path)
    scorer = _com_retry(criar_scorer_openai(model=model, temperature=temperature))
    return _loop_inferencia(docs, scorer, cache, cache_path, f"OpenAI · {model}")


# ---------------------------------------------------------------------------
# Tabela consolidada — três provedores + Selic
# ---------------------------------------------------------------------------

def montar_tabela(docs: list) -> pd.DataFrame:
    """
    Roda os três provedores e devolve uma única tabela alinhada por nro_reuniao.

    Colunas de saída
    ----------------
    nro_reuniao   int    número da reunião do Copom
    data          str    YYYY-MM-DD (data de referência)
    selic         float  meta Selic vigente na data da reunião (% a.a.)
    delta_selic   float  variação vs reunião anterior em p.p. (NaN na 1ª)
    score_gemini  float  score do Gemini Flash Lite
    score_claude  float  score do Claude Haiku
    score_openai  float  score do GPT-4.1-mini
    score_medio   float  média aritmética dos scores disponíveis (ignora NaN)

    Lógica de join
    --------------
    • Outer join entre os três CSVs de cache — uma ata com erro em um provedor
      aparece com NaN nessa coluna, mas não some da tabela.
    • score_medio calcula a média apenas das colunas não-NaN, preservando
      parcialidade (ex.: 2 provedores ok, 1 com erro → média de 2).
    • Selic alinhada com pd.Series.asof() via alinhar_selic() — robusto a
      feriados e fins de semana.
    • Salva em output/scores/scores_consolidado.csv para o paper Quarto.
    """
    from functools import reduce
    from coletar_selic import alinhar_selic
    from lexico import pontuar_lexico_batch

    # 1. Lexico (local, zero API, sempre disponivel)
    df_lex = pontuar_lexico_batch(docs)[["nro_reuniao", "data", "score_lexico"]]

    # 2. Pontua com cada LLM (usa cache; so chama API para atas novas)
    df_g = pontuar_gemini(docs)
    df_c = pontuar_claude(docs)
    df_o = pontuar_openai(docs)

    # 3. Merge outer por (nro_reuniao, data)
    dfs = [
        df_lex,
        df_g.rename(columns={"score": "score_gemini"}),
        df_c.rename(columns={"score": "score_claude"}),
        df_o.rename(columns={"score": "score_openai"}),
    ]
    df = reduce(
        lambda a, b: pd.merge(a, b, on=["nro_reuniao", "data"], how="outer"),
        dfs,
    ).sort_values("nro_reuniao").reset_index(drop=True)

    # 4. Score medio dos LLMs (lexico e baseline separado, nao entra na media)
    llm_cols = ["score_gemini", "score_claude", "score_openai"]
    df[llm_cols] = df[llm_cols].apply(pd.to_numeric, errors="coerce")
    df["score_medio"] = df[llm_cols].mean(axis=1).round(2)

    # 5. Junta Selic
    reunioes = df[["nro_reuniao", "data"]].to_dict("records")
    df_selic = alinhar_selic(reunioes)
    df = df.merge(df_selic, on=["nro_reuniao", "data"], how="left")

    # 6. Ordena colunas e salva
    cols_finais = [
        "nro_reuniao", "data",
        "selic", "delta_selic",
        "score_lexico",
        "score_gemini", "score_claude", "score_openai", "score_medio",
    ]
    df = df[[c for c in cols_finais if c in df.columns]]

    dest = Path("output/scores/scores_consolidado.csv")
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(dest, index=False, float_format="%.2f")
    log.info("scores_consolidado.csv salvo (%d linhas).", len(df))

    return df


# ---------------------------------------------------------------------------
# Teste rápido
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    sys.path.insert(0, str(Path(__file__).parent))

    from baixar_atas import coletar

    docs = coletar(reuniao_inicial=277)   # 3 atas do cache, sem rede

    df = montar_tabela(docs)

    print("\n" + "═" * 72)
    print("TABELA CONSOLIDADA — Tom das Atas × Selic")
    print("═" * 72)
    print(df.to_string(index=False))
    print("═" * 72)
    print(f"\n→ output/scores/scores_consolidado.csv ({len(df)} linhas)")
