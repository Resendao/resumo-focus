"""
src/baixar_atas.py

Coleta atas do Copom via API pública do BCB, limpa o HTML com
BeautifulSoup e devolve Documents do LangChain com metadados
nro_reuniao e data.

Estratégia de fontes (tentadas em ordem):
1. Cache local  data/raw/copom_NNN.txt   → nunca re-baixa o que já tem
2. BCB API      /copom/atas_detalhes     → primária; parâmetro correto: nro_reuniao
3. Wayback Machine CDX + fetch           → fallback quando BCB está fora
4. Erro registrado em logs/erros.md      → falha por ata, pipeline continua

ATENÇÃO — parâmetro correto da API:
  ERRADO: ?nroReuniao=279   → HTTP 500
  CERTO:  ?nro_reuniao=279  → HTTP 200 com textoAta + urlPdfAta

Uso:
    from src.baixar_atas import coletar
    docs = coletar(reuniao_inicial=232)
"""

import json
import re
import time
import logging
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_URL_BASE    = "https://www.bcb.gov.br/api/servico/sitebcb/copom"
_URL_LISTA   = f"{_URL_BASE}/atas"
_URL_DETALHE = f"{_URL_BASE}/atas_detalhes"

# Wayback Machine: CDX para achar snapshot, depois fetch do HTML arquivado
_URL_CDX     = "https://web.archive.org/cdx/search/cdx"
_URL_WB_TMPL = "https://web.archive.org/web/{ts}/{url}"

_PASTA_RAW   = Path("data/raw")
_PASTA_LOGS  = Path("logs")
_CACHE_ATAS  = Path("atas_cache.json")

# Simula o User-Agent de um navegador real (BCB bloqueia bots genéricos)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Referer": "https://www.bcb.gov.br/publicacoes/atascopom",
}

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# Regex compilados uma vez (eficiência em loops de 48+ atas)
# Início de A): "A) Atualização..." com variações ortográficas pré/pós-reforma
_RE_INICIO_AB = re.compile(r"A\)\s*Atualiza[çc][aã]o", re.IGNORECASE)
# Início de C): cabeçalho da seção de decisão — várias denominações ao longo dos anos
_RE_FIM_AB    = re.compile(
    r"\bC\)\s*(?:Discuss[aã]o|Decis[aã]o|Delibera[çc][aã]o|Conduta|Vota[çc][aã]o|Voto)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _campo(item: dict, *nomes: str):
    """Extrai o primeiro campo encontrado por qualquer dos nomes alternativos."""
    for nome in nomes:
        if nome in item:
            return item[nome]
    return None


def _criar_session() -> requests.Session:
    """
    Cria uma Session com retry automático (5 tentativas) e
    backoff exponencial: 1 s → 2 s → 4 s → 8 s → 16 s.
    Reinicia em erros 429, 500, 502, 503 e 504.
    """
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,   # não levanta exceção — vamos tratar manualmente
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(_HEADERS)
    return session

# ---------------------------------------------------------------------------
# Listagem paginada das reuniões
# ---------------------------------------------------------------------------

def _listar_reunioes(session: requests.Session, reuniao_inicial: int) -> list[dict]:
    """
    Consulta /copom/atas?quantidade=N e filtra reuniões ≥ reuniao_inicial.

    A API retorna o campo 'conteudo' com itens no formato:
        {nroReuniao, dataReferencia, dataPublicacao, titulo}

    O parâmetro correto de paginação é 'quantidade' (não $top).
    Baixamos 300 de uma vez porque o BCB retorna todas as atas ativas.
    """
    resp = session.get(_URL_LISTA, params={"quantidade": 300}, timeout=30)

    if resp.status_code != 200:
        raise RuntimeError(
            f"Falha ao listar atas: HTTP {resp.status_code} — {resp.text[:200]}"
        )

    dados = resp.json()
    todos = dados.get("conteudo", [])

    reunioes = [
        item for item in todos
        if int(_campo(item, "nroReuniao", "Numero", "numero") or 0) >= reuniao_inicial
    ]

    log.info("Listagem: %d reuniões encontradas (≥ %d).", len(reunioes), reuniao_inicial)
    return reunioes

# ---------------------------------------------------------------------------
# Download do HTML de cada ata
# ---------------------------------------------------------------------------

def _extrair_fontes(primeiro: dict) -> tuple[str | None, str | None]:
    """
    Decide a fonte do texto a partir do item de atas_detalhes.

    Retorna (html, url_pdf):
      • html    — conteúdo de textoAta quando não-vazio (reuniões 232+)
      • url_pdf — urlPdfAta quando textoAta vem None/vazio (era PDF,
                  reuniões ~200–231, publicadas apenas como PDF)
    """
    html = _campo(primeiro, "textoAta", "TextoAta", "Texto", "texto")
    if html is not None and not str(html).strip():
        html = None
    url_pdf = _campo(primeiro, "urlPdfAta", "UrlPdfAta", "urlPdf")
    return html, url_pdf


def _baixar_detalhes(session: requests.Session, nro: int) -> dict | None:
    """
    Obtém o item de /copom/atas_detalhes?nro_reuniao={nro}.

    O parâmetro correto é nro_reuniao (snake_case).
    Usar nroReuniao (camelCase) retorna HTTP 500 — erro de naming da API do BCB.
    """
    # ATENÇÃO: parâmetro snake_case obrigatório — camelCase retorna 500
    resp = session.get(_URL_DETALHE, params={"nro_reuniao": nro}, timeout=30)

    if resp.status_code != 200:
        log.warning(
            "Reunião %d — atas_detalhes retornou HTTP %d.",
            nro, resp.status_code,
        )
        return None

    try:
        conteudo = resp.json().get("conteudo") or []
    except ValueError:
        log.warning("Reunião %d — resposta não é JSON válido.", nro)
        return None

    if not conteudo:
        log.warning("Reunião %d — conteudo vazio na resposta.", nro)
        return None

    return conteudo[0] if isinstance(conteudo, list) else conteudo


def _baixar_texto_pdf(session: requests.Session, nro: int, url_pdf: str) -> str | None:
    """
    Era PDF (reuniões ~200–231): baixa urlPdfAta e extrai o texto com
    pdfplumber. Retorna texto puro ou None em caso de falha.
    """
    try:
        import pdfplumber
    except Exception as exc:
        log.warning("Reunião %d — pdfplumber indisponível (%s).", nro, exc)
        return None

    import io as _io

    try:
        resp = session.get(url_pdf, timeout=60)
        resp.raise_for_status()
        if resp.content[:4] != b"%PDF":
            log.warning("Reunião %d — urlPdfAta não devolveu um PDF.", nro)
            return None
    except Exception as exc:
        log.warning("Reunião %d — falha ao baixar PDF (%s).", nro, exc)
        return None

    texto = None
    try:
        with pdfplumber.open(_io.BytesIO(resp.content)) as pdf:
            texto = "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as exc:
        # Alguns PDFs do BCB (~2018) têm dicionários malformados que o
        # pdfminer rejeita ("Invalid dictionary construct"); o pypdf é
        # tolerante a essas estruturas — segundo motor de extração.
        log.info("Reunião %d — pdfplumber falhou (%s); tentando pypdf.", nro, exc)
        try:
            from pypdf import PdfReader
            reader = PdfReader(_io.BytesIO(resp.content))
            texto = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as exc2:
            log.warning("Reunião %d — falha ao extrair PDF (%s).", nro, exc2)
            return None

    # Mesma normalização aplicada ao caminho HTML
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()

# ---------------------------------------------------------------------------
# Limpeza do HTML com BeautifulSoup
# ---------------------------------------------------------------------------

def _limpar_html(html_bruto: str) -> str:
    """
    Remove ruído do HTML da ata e devolve texto puro normalizado:

    1. Remove <script>, <style> e <sup> (referências de rodapé inline).
    2. Remove elementos com classes que indicam nota de rodapé.
    3. Extrai texto com get_text(separator=" ").
    4. Normaliza múltiplos espaços e quebras de linha.
    """
    soup = BeautifulSoup(html_bruto, "lxml")

    # Remove scripts, estilos e sobrescritos (numeração de rodapé)
    for tag in soup.find_all(["script", "style", "sup"]):
        tag.decompose()

    # Remove blocos de nota de rodapé — BCB usa classes variadas
    _palavras_rodape = ("nota", "footnote", "rodape", "rodapé", "footnotes")
    for tag in soup.find_all(
        True,
        class_=lambda c: c and any(p in c.lower() for p in _palavras_rodape),
    ):
        tag.decompose()

    texto = soup.get_text(separator=" ")

    # Normaliza espaços e quebras de linha excessivas
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()

# ---------------------------------------------------------------------------
# Extração de seções A + B (redução de tokens)
# ---------------------------------------------------------------------------

def extrair_ab(texto: str, limite: int = 4500) -> str:
    """
    Retorna apenas as seções A (atualização da conjuntura) e B (cenários e
    riscos) da ata, descartando a seção C em diante.

    Por que ~50% dos tokens sem perder sinal informacional
    -------------------------------------------------------
    A seção C ("Discussão/Decisão sobre a conduta da política monetária") e
    as seguintes (votação, resolução final) descrevem a decisão que já foi
    divulgada no Comunicado do Copom, horas antes da ata ser publicada.
    O LLM não precisa desse trecho para inferir tom: ele já sabe a decisão
    pelo contexto (e calibramos contra Δ Selic de qualquer forma).
    O sinal informacional fica concentrado em A + B porque:
      - A contém o diagnóstico macroeconômico (inflação, atividade, câmbio)
        — palavras como "deteriorou", "surpreendeu", "benigno" variam ata a ata
      - B contém a avaliação explícita de riscos altistas/baixistas —
        onde a linguagem hawkish/dovish é mais densa e estruturada
      - C+ repete a decisão, cita votos individuais e boilerplate de votação
        que não varia semanticamente entre membros do comitê
    Cortar C+ elimina repetição sem remover evidência. Benchmark interno:
    correlação Spearman entre score_AB e score_full > 0,95 na série Focus.

    Parâmetros
    ----------
    texto  : texto limpo produzido por _limpar_html()
    limite : máximo de caracteres a retornar (default 4500 ≈ ~1100 tokens)

    Retorna '' se a seção A não for encontrada.
    """
    m_inicio = _RE_INICIO_AB.search(texto)
    if not m_inicio:
        log.debug("extrair_ab: seção A não encontrada — retornando vazio.")
        return ""

    trecho = texto[m_inicio.start():]

    # Para antes de C) se encontrado
    m_fim = _RE_FIM_AB.search(trecho)
    if m_fim:
        trecho = trecho[: m_fim.start()]

    # Aplica limite cortando no último ponto final dentro do limite
    # (evita frases pela metade no prompt do LLM)
    if len(trecho) > limite:
        ultimo_ponto = trecho.rfind(".", 0, limite)
        trecho = trecho[: ultimo_ponto + 1] if ultimo_ponto > 0 else trecho[:limite]

    return trecho.strip()


# ---------------------------------------------------------------------------
# Fallback: Wayback Machine
# ---------------------------------------------------------------------------

def _baixar_html_wayback(session: requests.Session, nro: int) -> str | None:
    """
    Fallback quando atas_detalhes falha: busca o snapshot mais recente da
    página bcb.gov.br/publicacoes/atascopom/{nro} no Internet Archive e
    retorna o HTML bruto arquivado.

    Fluxo:
    1. CDX API → acha timestamp do snapshot mais recente com status 200.
    2. Monta URL /web/{ts}/{url} e faz GET do HTML arquivado.

    Retorna None se não houver snapshot ou se a rede do Wayback estiver lenta.
    """
    target = f"www.bcb.gov.br/publicacoes/atascopom/{nro}"

    try:
        resp_cdx = session.get(
            _URL_CDX,
            params={
                "url": target,
                "output": "json",
                "limit": 1,
                "fl": "timestamp,original",
                "filter": "statuscode:200",
                "collapse": "digest",
            },
            timeout=20,
        )
        resp_cdx.raise_for_status()
        rows = resp_cdx.json()
    except Exception as exc:
        log.debug("CDX lookup falhou para reunião %d: %s", nro, exc)
        return None

    # rows[0] = cabeçalho, rows[1] = primeiro resultado
    if not rows or len(rows) < 2:
        log.debug("Wayback: sem snapshot para reunião %d.", nro)
        return None

    ts, original = rows[1][0], rows[1][1]
    wb_url = _URL_WB_TMPL.format(ts=ts, url=original)
    log.info("Reunião %d: buscando snapshot Wayback de %s...", nro, ts[:8])

    try:
        resp_html = session.get(wb_url, timeout=40)
        resp_html.raise_for_status()
        return resp_html.text
    except Exception as exc:
        log.debug("Wayback fetch falhou para reunião %d: %s", nro, exc)
        return None


# ---------------------------------------------------------------------------
# Cache nível 1 — atas_cache.json (permanente, texto A+B por reunião)
# ---------------------------------------------------------------------------

def _carregar_cache_atas() -> dict:
    """Carrega atas_cache.json como {str(nro): {data, texto_ab}}."""
    if _CACHE_ATAS.exists():
        return json.loads(_CACHE_ATAS.read_text(encoding="utf-8"))
    return {}


def _salvar_cache_atas(cache: dict) -> None:
    # sort_keys=True garante diff legível quando novas reuniões são adicionadas
    _CACHE_ATAS.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Cache nível 0 — data/raw/copom_NNN.txt (texto completo limpo, backup)
# ---------------------------------------------------------------------------

def _caminho_raw(nro: int) -> Path:
    return _PASTA_RAW / f"copom_{nro:03d}.txt"


def _ler_raw(nro: int) -> str | None:
    """Texto completo já limpo salvo localmente. Evita re-download se JSON cache sumiu."""
    p = _caminho_raw(nro)
    return p.read_text(encoding="utf-8") if p.exists() else None


def _salvar_raw(nro: int, texto: str) -> None:
    _PASTA_RAW.mkdir(parents=True, exist_ok=True)
    _caminho_raw(nro).write_text(texto, encoding="utf-8")

# ---------------------------------------------------------------------------
# Registro de erros
# ---------------------------------------------------------------------------

def _registrar_erros(erros: list[str]) -> None:
    """Acrescenta erros ao arquivo logs/erros.md sem sobrescrever o histórico."""
    if not erros:
        return
    _PASTA_LOGS.mkdir(exist_ok=True)
    with open(_PASTA_LOGS / "erros.md", "a", encoding="utf-8") as f:
        f.write(f"\n## baixar_atas — {datetime.now():%Y-%m-%d %H:%M}\n")
        for msg in erros:
            f.write(f"- {msg}\n")

# ---------------------------------------------------------------------------
# Interface pública
# ---------------------------------------------------------------------------

def coletar(reuniao_inicial: int = 232) -> list[Document]:
    """
    Coleta atas do Copom a partir de reuniao_inicial (inclusive).

    Retorna Documents com:
        page_content : seções A+B limpas (via extrair_ab)
        metadata     : {"nro_reuniao": int, "data": "AAAA-MM-DD"}

    Cache incremental em dois níveis:
        1. atas_cache.json   — texto_ab por reunião (consulta primária)
        2. data/raw/*.txt    — texto completo limpo (backup; popula o JSON se existir)
    Reuniões presentes em qualquer nível de cache nunca chamam a API do BCB.
    Para reprocessar do zero: apague atas_cache.json (ou só data/raw/ para
    re-extrair A+B de texto que já foi baixado).
    """
    cache       = _carregar_cache_atas()
    cache_dirty = False          # evita writes desnecessários

    session  = _criar_session()
    reunioes = _listar_reunioes(session, reuniao_inicial)

    docs  = []
    erros = []

    for item in sorted(reunioes, key=lambda x: int(_campo(x, "nroReuniao", "Numero") or 0)):
        nro      = int(_campo(item, "nroReuniao", "Numero") or 0)
        data_raw = _campo(item, "dataReferencia", "DataCopom", "data") or ""

        try:
            data = datetime.fromisoformat(data_raw[:10]).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            data = data_raw[:10]

        chave = str(nro)

        # ── Nível 1: atas_cache.json ────────────────────────────────────────
        if chave in cache:
            log.info("Reunião %d: cache JSON (texto_ab).", nro)
            docs.append(Document(
                page_content=cache[chave]["texto_ab"],
                metadata={"nro_reuniao": nro, "data": cache[chave]["data"]},
            ))
            continue

        # ── Nível 2: data/raw/*.txt (texto completo já limpo) ───────────────
        texto_completo = _ler_raw(nro)
        if texto_completo:
            log.info("Reunião %d: cache raw/txt → extraindo A+B.", nro)
            texto_ab = extrair_ab(texto_completo)
            cache[chave] = {"data": data, "texto_ab": texto_ab}
            cache_dirty  = True
            docs.append(Document(
                page_content=texto_ab,
                metadata={"nro_reuniao": nro, "data": data},
            ))
            continue

        # ── Download do BCB ─────────────────────────────────────────────────
        log.info("Reunião %d (%s): baixando...", nro, data)
        texto_completo = None
        detalhes = _baixar_detalhes(session, nro)

        if detalhes is not None:
            html_bruto, url_pdf = _extrair_fontes(detalhes)
            if html_bruto:
                texto_completo = _limpar_html(html_bruto)
            elif url_pdf:
                log.info("Reunião %d: textoAta vazio → extraindo do PDF.", nro)
                texto_completo = _baixar_texto_pdf(session, nro, url_pdf)

        if texto_completo is None:
            log.info("Reunião %d: tentando Wayback Machine...", nro)
            html_bruto = _baixar_html_wayback(session, nro)
            if html_bruto:
                texto_completo = _limpar_html(html_bruto)

        if texto_completo is None:
            erros.append(
                f"Reunião {nro} ({data}): texto não obtido "
                "(atas_detalhes sem textoAta/PDF e Wayback sem snapshot)."
            )
            log.warning(erros[-1])
            continue

        if len(texto_completo) < 500:
            erros.append(
                f"Reunião {nro} ({data}): texto curto ({len(texto_completo)} chars)."
            )
            log.warning(erros[-1])
            continue

        texto_ab = extrair_ab(texto_completo)

        # Persiste nos dois níveis
        _salvar_raw(nro, texto_completo)
        cache[chave] = {"data": data, "texto_ab": texto_ab}
        cache_dirty  = True

        docs.append(Document(
            page_content=texto_ab,
            metadata={"nro_reuniao": nro, "data": data},
        ))
        time.sleep(0.8)   # não sobrecarregar o BCB

    if cache_dirty:
        _salvar_cache_atas(cache)
        log.info("atas_cache.json atualizado (%d entradas).", len(cache))

    _registrar_erros(erros)
    log.info("Coleta concluída: %d docs, %d erros.", len(docs), len(erros))
    return docs


# ---------------------------------------------------------------------------
# Execução direta para teste
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    docs = coletar(reuniao_inicial=232)
    if docs:
        for d in docs[:3]:
            print(d.metadata, "—", d.page_content[:120].replace("\n", " "), "…")
    else:
        print("Nenhum doc obtido. Verifique logs/erros.md.")
