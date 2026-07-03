"""
src/coletar_selic.py

Coleta a meta Selic (SGS 432) do BCB via API JSON, alinha por data de
reunião do Copom e calcula variação em p.p. a cada reunião.

Cache incremental em selic_cache.json:
- Consulta a API apenas para datas além do último registro salvo.
- Fallback automático para o cache se a API estiver fora do ar.
- Para re-baixar do zero: apague selic_cache.json.

Uso rápido:
    from src.coletar_selic import alinhar_selic
    from src.baixar_atas import _listar_reunioes, _criar_session

    session  = _criar_session()
    reunioes = _listar_reunioes(session, reuniao_inicial=232)
    df_selic = alinhar_selic(reunioes)
"""

import json
import logging
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_URL_SGS     = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
_CACHE_PATH  = Path("selic_cache.json")

# Data de início: um ano antes da reunião 200 (jun/2016) para garantir
# que a reunião anterior (199) tenha Selic no cache e delta_selic[200]
# seja calculado corretamente.
_DATA_INICIO_PADRAO = "2015-06-01"

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session com retry e backoff exponencial
# ---------------------------------------------------------------------------

def _criar_session() -> requests.Session:
    retry = Retry(
        total=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"Accept": "application/json"})
    return s

# ---------------------------------------------------------------------------
# Conversão de formatos de data
# ---------------------------------------------------------------------------

def _para_bcb(data_iso: str) -> str:
    """YYYY-MM-DD → DD/MM/YYYY (formato exigido pela API do BCB)."""
    return datetime.strptime(data_iso, "%Y-%m-%d").strftime("%d/%m/%Y")


def _para_iso(data_bcb: str) -> str:
    """DD/MM/YYYY → YYYY-MM-DD."""
    return datetime.strptime(data_bcb, "%d/%m/%Y").strftime("%Y-%m-%d")

# ---------------------------------------------------------------------------
# Cache (selic_cache.json)
# ---------------------------------------------------------------------------

def _carregar_cache() -> dict[str, float]:
    """Carrega selic_cache.json como {data_iso: selic_float}."""
    if _CACHE_PATH.exists():
        raw = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return {k: float(v) for k, v in raw.items()}
    return {}


def _salvar_cache(cache: dict[str, float]) -> None:
    _CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

# ---------------------------------------------------------------------------
# Coleta da série SGS 432 com cache incremental
# ---------------------------------------------------------------------------

def _janelas(inicio: str, fim: str, anos: int = 9) -> list[tuple[str, str]]:
    """
    Divide [inicio, fim] em fatias de no máximo `anos` anos.

    A API SGS retorna HTTP 406 para janelas maiores que 10 anos em séries
    diárias — o backfill de 2015 → hoje precisa ser buscado em pedaços.
    Fatias são contíguas (o fim de uma é o início da próxima; a sobreposição
    de 1 dia é absorvida pelo dict do cache).
    """
    ini = datetime.strptime(inicio, "%Y-%m-%d").date()
    fim_d = datetime.strptime(fim, "%Y-%m-%d").date()
    fatias = []
    while True:
        corte = date(ini.year + anos, ini.month, ini.day)
        if corte >= fim_d:
            fatias.append((ini.isoformat(), fim_d.isoformat()))
            return fatias
        fatias.append((ini.isoformat(), corte.isoformat()))
        ini = corte


def buscar_selic(data_inicio: str = _DATA_INICIO_PADRAO) -> pd.DataFrame:
    """
    Retorna DataFrame (data: datetime64, selic: float) com a meta Selic diária.

    Estratégia incremental
    -----------------------
    1. Carrega selic_cache.json.
    2. Compara a data máxima cacheada com hoje.
    3. Se desatualizado, busca apenas o intervalo [max_cache..hoje] na API.
    4. Mescla o resultado com o cache existente e salva.
    5. Se a API falhar mas o cache existir, usa o cache como fallback.

    Assim, rodadas semanais fazem no máximo uma chamada com ~5 registros novos,
    não re-baixam os ~2000 pontos históricos.
    Para re-baixar do zero: apague selic_cache.json.
    """
    cache = _carregar_cache()
    hoje  = date.today().isoformat()

    # Determina se o cache precisa ser atualizado
    data_max_cache = max(cache.keys()) if cache else ""
    data_min_cache = min(cache.keys()) if cache else ""
    backfill       = bool(cache) and data_min_cache > data_inicio
    precisa_fetch  = not cache or data_max_cache < hoje or backfill

    if precisa_fetch:
        # Backfill: cache começa depois do início requerido (cobertura
        # ampliada) → re-baixa o range completo e mescla por data.
        # Caso normal: pede apenas o slice ainda não cacheado.
        if backfill:
            log.info("SGS 432: cache começa em %s > %s — backfill completo.",
                     data_min_cache, data_inicio)
            inicio_fetch = data_inicio
        else:
            inicio_fetch = data_max_cache if data_max_cache else data_inicio
        log.info("SGS 432: buscando %s → %s...", inicio_fetch, hoje)
        session = _criar_session()
        try:
            novos: dict[str, float] = {}
            # Fatias de <= 9 anos: a API retorna 406 para janelas > 10 anos
            for ini_f, fim_f in _janelas(inicio_fetch, hoje):
                resp = session.get(
                    _URL_SGS,
                    params={
                        "formato":      "json",
                        "dataInicial":  _para_bcb(ini_f),
                        "dataFinal":    _para_bcb(fim_f),
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                novos.update({
                    _para_iso(r["data"]): float(r["valor"].replace(",", "."))
                    for r in resp.json()
                    if r.get("valor") not in (None, "", "null")
                })
            qtd_novos = len(set(novos) - set(cache))
            cache.update(novos)
            _salvar_cache(cache)
            log.info("SGS 432: +%d novas obs. (total %d). selic_cache.json salvo.",
                     qtd_novos, len(cache))

        except Exception as exc:
            if cache:
                log.warning(
                    "SGS 432 indisponível (%s). Usando cache até %s.",
                    exc, data_max_cache,
                )
            else:
                raise RuntimeError(
                    f"SGS 432 falhou e não há selic_cache.json: {exc}"
                ) from exc

    df = pd.DataFrame(sorted(cache.items()), columns=["data", "selic"])
    df["data"]  = pd.to_datetime(df["data"])
    df["selic"] = df["selic"].astype(float)
    return df.sort_values("data").reset_index(drop=True)

# ---------------------------------------------------------------------------
# Alinhamento por data de reunião e cálculo de Δ
# ---------------------------------------------------------------------------

def alinhar_selic(reunioes: list[dict]) -> pd.DataFrame:
    """
    Alinha a meta Selic com as datas de reunião do Copom.

    Parâmetros
    ----------
    reunioes : lista de dicts com ao menos {'nro_reuniao': int, 'data': 'YYYY-MM-DD'}.
               Vem diretamente de _listar_reunioes() ou do loop em coletar().

    Retorna DataFrame com colunas:
        nro_reuniao   (int)
        data          (str  YYYY-MM-DD)
        selic         (float)  — meta em % a.a. na data de referência
        delta_selic   (float)  — variação vs reunião anterior em p.p. (NaN na 1ª)

    Lógica de alinhamento: pd.Series.asof()
    -----------------------------------------
    A série SGS 432 tem valores apenas em dias úteis. Se a data de referência
    da reunião cair em feriado ou fim de semana, asof() devolve o valor do
    último dia útil anterior — que é exatamente a Selic vigente no momento
    em que o comitê se reuniu.

    Interpretação de delta_selic:
        > 0  → aperto monetário  (hawkish: subiu a Selic)
        < 0  → afrouxamento      (dovish:  cortou a Selic)
        = 0  → manutenção
        NaN  → primeira reunião na série (sem predecessora interna)

    Nota: para que delta_selic[232] não seja NaN, buscar_selic() busca dados
    desde 2019-01-01, garantindo que a reunião 231 (jul/2020) está na série.
    """
    df_selic = buscar_selic()
    serie    = df_selic.set_index("data")["selic"].sort_index()

    rows = []
    for item in sorted(reunioes, key=lambda x: x.get("data", "") or x.get("dataReferencia", "")):
        nro  = int(item.get("nro_reuniao") or item.get("nroReuniao") or 0)
        data_str = (
            item.get("data") or item.get("dataReferencia") or ""
        )
        data = pd.Timestamp(data_str[:10])
        selic_val = serie.asof(data)   # NaN se anterior ao início da série
        rows.append({"nro_reuniao": nro, "data": data_str[:10], "selic": selic_val})

    df = pd.DataFrame(rows)

    # Δ em p.p. arredondado para evitar ruído de ponto flutuante
    df["delta_selic"] = df["selic"].diff().round(4)
    return df


# ---------------------------------------------------------------------------
# Execução direta para teste
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # Simula lista de reuniões recentes
    reunioes_teste = [
        {"nro_reuniao": 277, "data": "2026-03-18"},
        {"nro_reuniao": 278, "data": "2026-04-29"},
        {"nro_reuniao": 279, "data": "2026-06-17"},
    ]

    df = alinhar_selic(reunioes_teste)
    print(df.to_string(index=False))
