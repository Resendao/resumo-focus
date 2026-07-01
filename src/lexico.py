"""
src/lexico.py

Baseline léxico hawkish/dovish para atas do Copom.

Referências metodológicas
--------------------------
Loughran & McDonald (2011) — "When Is a Liability Not a Liability?"
    Dicionário de sentimento financeiro; mostrou que listas genéricas (Harvard IV)
    classificam errada ~75% dos termos negativos em documentos financeiros.
    Lição: o léxico precisa ser calibrado ao domínio.

Apel & Grimaldi (2012) — "The Information Content of Central Bank Minutes"
    Contagem direta de termos hawkish/dovish em atas do Riksbank; correlação
    significativa com decisões subsequentes de taxa.
    Lição: listas pequenas e precisas superam NLP genérico em textos de BC.

Score
-----
    raw   = (n_hawkish - n_dovish) / (n_hawkish + n_dovish)  ∈ [-1, +1]
    score = raw × 3                                            ∈ [-3, +3]

    • n_h = n_d = 0  →  score = 0.0  (neutro por omissão)
    • Todos hawkish  →  score = +3.0
    • Todos dovish   →  score = -3.0

Papel do léxico no pipeline
----------------------------
É intencionalmente o PISO metodológico:
    • Sem custo de API — cálculo determinístico e instantâneo
    • Totalmente reproducível (grep no texto limpo)
    • Sem alucinação, sem variância entre runs
    • Limite inferior: captura apenas o que está literalmente escrito
    Serve de benchmark: se os LLMs ficam abaixo do léxico em correlação com
    Δ Selic, há problema no prompt ou no modelo, não nos dados.
"""

import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Léxico hawkish
# ---------------------------------------------------------------------------
# Termos que sinalizam aperto monetário, inflação como ameaça,
# expectativas desancoradas ou forward guidance de alta da Selic.
# Fonte: leitura sistemática de 50 atas do Copom (2003–2024) +
#         glossário do Relatório de Inflação do BCB.

HAWKISH: list[str] = [
    # Inflação como ameaça explícita
    "pressão inflacionária",
    "pressões inflacionárias",
    "inflação persistente",
    "persistência da inflação",
    "persistência inflacionária",
    "inflação elevada",
    "aceleração da inflação",
    "repique inflacionário",

    # Posição relativa à meta (sinal claro de preocupação)
    "acima da meta",
    "acima do centro da meta",
    "acima do intervalo de tolerância",
    "acima do limite superior",

    # Desancoragem de expectativas
    "desancoragem",
    "desancoradas",
    "desancoramento",
    "expectativas desancoradas",
    "expectativas acima da meta",

    # Balanço de riscos altista
    "risco altista",
    "riscos altistas",
    "viés altista",
    "assimétrico para cima",
    "assimetria altista",
    "predominantemente altista",

    # Postura e ação hawkish
    "aperto monetário",
    "aperto adicional",
    "aperto das condições monetárias",
    "elevação da taxa",
    "elevação da selic",
    "aumento da taxa selic",
    "elevação adicional",
    "vigilância",
    "vigilante",
    "tempestividade",
    "agir de forma tempestiva",
    "combate à inflação",
    "proativo",
    "firme comprometimento",
    "determinação em trazer",
]

# ---------------------------------------------------------------------------
# Léxico dovish
# ---------------------------------------------------------------------------
# Termos que sinalizam afrouxamento monetário, demanda fraca,
# expectativas ancoradas (criando espaço para cortes) ou
# forward guidance de redução da Selic.

DOVISH: list[str] = [
    # Atividade fraca / ociosidade (justifica corte)
    "atividade econômica fraca",
    "fraqueza da atividade",
    "desaceleração da atividade",
    "retração econômica",
    "contração da atividade",
    "ociosidade",
    "capacidade ociosa",
    "hiato do produto negativo",
    "ociosidade dos fatores",

    # Inflação cedendo / convergindo
    "arrefecimento",
    "arrefecimento da inflação",
    "desinflação",
    "desaceleração da inflação",
    "convergência para a meta",
    "convergência em direção à meta",
    "abaixo da meta",
    "abaixo do centro da meta",
    "abaixo do limite inferior",

    # Balanço de riscos baixista
    "risco baixista",
    "riscos baixistas",
    "viés baixista",
    "assimétrico para baixo",
    "assimetria baixista",
    "predominantemente baixista",

    # Expectativas ancoradas (cria espaço para flexibilização)
    "expectativas ancoradas",
    "expectativas bem ancoradas",
    "bem ancoradas",
    "projeções convergindo",

    # Postura e ação dovish
    "afrouxamento",
    "afrouxamento monetário",
    "afrouxamento das condições",
    "redução da taxa",
    "corte da taxa",
    "redução da selic",
    "corte da selic",
    "acomodação monetária",
    "política acomodatícia",
    "estímulo monetário",
    "flexibilização monetária",
    "ciclo de reduções",
]

# ---------------------------------------------------------------------------
# Pré-compila os padrões (boundary \b garante que "vigilância" não casa
# dentro de "super-vigilância" etc.; re.IGNORECASE para robustez)
# ---------------------------------------------------------------------------

def _compilar(termos: list[str]) -> list[tuple[str, re.Pattern]]:
    return [
        (t, re.compile(r"\b" + re.escape(t) + r"\b", re.IGNORECASE))
        for t in termos
    ]


_PAD_HAWKISH = _compilar(HAWKISH)
_PAD_DOVISH  = _compilar(DOVISH)


# ---------------------------------------------------------------------------
# Função de scoring por ata
# ---------------------------------------------------------------------------

def pontuar_lexico(texto: str) -> dict:
    """
    Conta ocorrências de termos hawkish e dovish no texto e calcula o score.

    Retorna dict:
        n_hawkish     int     total de ocorrências hawkish
        n_dovish      int     total de ocorrências dovish
        score_lexico  float   (n_h - n_d)/(n_h + n_d) × 3, em [-3, +3]
        hits_hawkish  Counter termo → contagem (para auditoria)
        hits_dovish   Counter termo → contagem (para auditoria)
    """
    hits_h: Counter = Counter()
    for termo, pat in _PAD_HAWKISH:
        c = len(pat.findall(texto))
        if c:
            hits_h[termo] = c

    hits_d: Counter = Counter()
    for termo, pat in _PAD_DOVISH:
        c = len(pat.findall(texto))
        if c:
            hits_d[termo] = c

    n_h = sum(hits_h.values())
    n_d = sum(hits_d.values())

    total = n_h + n_d
    raw   = (n_h - n_d) / total if total > 0 else 0.0
    score = float(np.clip(raw * 3, -3.0, 3.0))

    return {
        "n_hawkish":    n_h,
        "n_dovish":     n_d,
        "score_lexico": round(score, 2),
        "hits_hawkish": hits_h,
        "hits_dovish":  hits_d,
    }


# ---------------------------------------------------------------------------
# Batch — lista de Documents → DataFrame
# ---------------------------------------------------------------------------

def pontuar_lexico_batch(docs: list) -> pd.DataFrame:
    """
    Aplica o léxico a todos os docs e devolve DataFrame(nro_reuniao, data,
    score_lexico, n_hawkish, n_dovish).

    Imprime progresso ata a ata (sem custo: é operação local, ~1 ms/ata).
    """
    rows = []

    print(f"\nLéxico Copom · {len(docs)} ata(s)  [sem API — cálculo local]")
    print(f"{'Nro':>5}  {'Data':<12}  {'Score':>6}  {'H':>4}  {'D':>4}  Tom")
    print("─" * 48)

    for doc in sorted(docs, key=lambda d: d.metadata["nro_reuniao"]):
        nro  = int(doc.metadata["nro_reuniao"])
        data = doc.metadata["data"]
        res  = pontuar_lexico(doc.page_content)
        s    = res["score_lexico"]

        if s > 0.5:
            tom = f"hawkish {'▲' * min(int(s), 3)}"
        elif s < -0.5:
            tom = f"dovish  {'▼' * min(int(-s), 3)}"
        else:
            tom = "neutro  ●"

        print(f"{nro:>5}  {data:<12}  {s:>+6.2f}  "
              f"{res['n_hawkish']:>4}  {res['n_dovish']:>4}  {tom}")

        rows.append({
            "nro_reuniao":  nro,
            "data":         data,
            "score_lexico": s,
            "n_hawkish":    res["n_hawkish"],
            "n_dovish":     res["n_dovish"],
        })

    print("─" * 48)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Auditoria — inspeciona quais termos foram encontrados em uma ata
# ---------------------------------------------------------------------------

def auditar(texto: str, nro: int | None = None) -> None:
    """Imprime os termos hawkish e dovish encontrados no texto."""
    res   = pontuar_lexico(texto)
    label = f"Reunião {nro}" if nro else "Ata"

    print(f"\n── Auditoria do léxico · {label} ──────────────────")
    print(f"  Score: {res['score_lexico']:+.2f}  "
          f"(H={res['n_hawkish']}, D={res['n_dovish']})")

    if res["hits_hawkish"]:
        print("\n  HAWKISH:")
        for t, c in res["hits_hawkish"].most_common():
            print(f"    [{c:>2}×]  {t}")
    else:
        print("\n  HAWKISH: nenhum termo encontrado")

    if res["hits_dovish"]:
        print("\n  DOVISH:")
        for t, c in res["hits_dovish"].most_common():
            print(f"    [{c:>2}×]  {t}")
    else:
        print("\n  DOVISH: nenhum termo encontrado")
    print()


# ---------------------------------------------------------------------------
# Execução direta para teste
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io, logging
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    sys.path.insert(0, str(Path(__file__).parent))

    from baixar_atas import coletar

    docs = coletar(reuniao_inicial=277)

    df = pontuar_lexico_batch(docs)
    print(f"\nDataFrame:\n{df[['nro_reuniao','data','score_lexico','n_hawkish','n_dovish']].to_string(index=False)}")

    # Auditoria da ata mais recente
    doc_ultimo = max(docs, key=lambda d: d.metadata["nro_reuniao"])
    auditar(doc_ultimo.page_content, nro=doc_ultimo.metadata["nro_reuniao"])
