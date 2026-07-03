"""
src/coletar_expectativas.py

Série histórica de expectativas do Focus (OData BCB) alinhada às reuniões
do Copom — a quantificação do Boletim Focus para o modelo multivariado.

Fluxo:
    OData (python-bcb) → cache bruto data/focus_expectativas_raw.csv
        → alinhar_reunioes() na véspera de cada reunião
        → output/focus/expectativas_reunioes.csv

Regra da véspera: para cada reunião usa-se a última pesquisa com
Data <= data_reuniao − 1 dia. A expectativa precisa ter sido formada ANTES
da decisão — usar a pesquisa do próprio dia contaminaria o regressor com
informação posterior ao anúncio.

Uso:
    python src/coletar_expectativas.py          # baixa/atualiza e alinha
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

_CACHE_RAW  = Path("data/focus_expectativas_raw.csv")
_CSV_SAIDA  = Path("output/focus/expectativas_reunioes.csv")
_CSV_SCORES = Path("output/scores/scores_consolidado.csv")

_DATA_INICIO = "2016-01-01"   # cobre a reunião 200 (jun/2016) com folga

_INDICADORES_ANUAIS = ["IPCA", "Selic", "Câmbio", "PIB Total"]

# Rótulo interno para a expectativa de inflação 12 meses à frente (suavizada)
_IPCA_12M = "IPCA_12m"

# Metas de inflação do CMN por ano-calendário. A partir de 2025 vigora a
# meta contínua de 3,00% (Resolução CMN 5.108/2023) — vale para qualquer
# ano futuro sem necessidade de atualização deste dicionário.
_METAS = {
    2016: 4.50, 2017: 4.50, 2018: 4.50, 2019: 4.25,
    2020: 4.00, 2021: 3.75, 2022: 3.50, 2023: 3.25, 2024: 3.00,
}
_META_CONTINUA = 3.00
_ANO_META_CONTINUA = 2025


# ---------------------------------------------------------------------------
# Funções puras (testáveis sem rede)
# ---------------------------------------------------------------------------

def meta_inflacao(ano: int) -> float:
    """Meta de inflação do CMN para o ano-calendário."""
    if ano in _METAS:
        return _METAS[ano]
    if ano >= _ANO_META_CONTINUA:
        return _META_CONTINUA
    raise ValueError(f"Meta de inflação não mapeada para {ano} (cobertura: 2020+).")


def ultima_pesquisa_ate(df: pd.DataFrame, cutoff: pd.Timestamp) -> pd.Series | None:
    """Linha da pesquisa mais recente com Data <= cutoff (inclusive), ou None."""
    sub = df[df["Data"] <= cutoff]
    if sub.empty:
        return None
    return sub.loc[sub["Data"].idxmax()]


def _valor_na_vespera(
    df_raw: pd.DataFrame,
    indicador: str,
    referencia: str | None,
    cutoff: pd.Timestamp,
) -> tuple[float, pd.Timestamp | None]:
    """(mediana, data_da_pesquisa) do indicador na véspera; (NaN, None) se ausente."""
    sub = df_raw[df_raw["Indicador"] == indicador]
    if referencia is not None:
        sub = sub[sub["DataReferencia"] == referencia]
    if "baseCalculo" in sub.columns:
        sub = sub[sub["baseCalculo"] == 0]
    row = ultima_pesquisa_ate(sub, cutoff)
    if row is None:
        return float("nan"), None
    return float(row["Mediana"]), row["Data"]


def alinhar_reunioes(df_raw: pd.DataFrame, reunioes: list[dict]) -> pd.DataFrame:
    """
    Expectativas do Focus na véspera de cada reunião do Copom.

    Parâmetros
    ----------
    df_raw   : base bruta com colunas Indicador, Data (datetime),
               DataReferencia (str), Mediana, baseCalculo
    reunioes : [{"nro_reuniao": int, "data": "AAAA-MM-DD"}, ...]

    Colunas de saída
    ----------------
    nro_reuniao, data, data_focus, ipca_12m, ipca_ano_corrente,
    ipca_ano_seguinte, meta_ano_seguinte, desvio_meta, selic_fim_ano,
    cambio_fim_ano, pib_ano_corrente

    desvio_meta = E[IPCA ano seguinte] − meta(ano seguinte): proxy de
    desancoragem no horizonte relevante da política monetária.
    """
    rows = []
    for r in sorted(reunioes, key=lambda x: x["data"]):
        data_reuniao = pd.Timestamp(r["data"])
        cutoff = data_reuniao - timedelta(days=1)
        ano = data_reuniao.year

        ipca_corr, data_focus = _valor_na_vespera(df_raw, "IPCA", str(ano), cutoff)
        ipca_seg,  _ = _valor_na_vespera(df_raw, "IPCA", str(ano + 1), cutoff)
        selic_fa,  _ = _valor_na_vespera(df_raw, "Selic", str(ano), cutoff)
        cambio_fa, _ = _valor_na_vespera(df_raw, "Câmbio", str(ano), cutoff)
        pib_corr,  _ = _valor_na_vespera(df_raw, "PIB Total", str(ano), cutoff)
        ipca_12m,  _ = _valor_na_vespera(df_raw, _IPCA_12M, None, cutoff)

        try:
            meta_seg = meta_inflacao(ano + 1)
        except ValueError:
            meta_seg = float("nan")

        rows.append({
            "nro_reuniao":       int(r["nro_reuniao"]),
            "data":              data_reuniao.strftime("%Y-%m-%d"),
            "data_focus":        data_focus.strftime("%Y-%m-%d") if data_focus is not None else None,
            "ipca_12m":          ipca_12m,
            "ipca_ano_corrente": ipca_corr,
            "ipca_ano_seguinte": ipca_seg,
            "meta_ano_seguinte": meta_seg,
            "desvio_meta":       ipca_seg - meta_seg,
            "selic_fim_ano":     selic_fa,
            "cambio_fim_ano":    cambio_fa,
            "pib_ano_corrente":  pib_corr,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Download OData com cache incremental
# ---------------------------------------------------------------------------

def _baixar_anuais(ep, indicador: str, data_inicio: str) -> pd.DataFrame:
    """ExpectativasMercadoAnuais de um indicador a partir de data_inicio."""
    df = (
        ep.query()
        .filter(ep.Indicador == indicador, ep.Data >= data_inicio)
        .select(ep.Indicador, ep.Data, ep.DataReferencia, ep.Mediana, ep.baseCalculo)
        .collect()
    )
    return df


def _baixar_ipca_12m(exp, data_inicio: str) -> pd.DataFrame:
    """Expectativa de IPCA 12 meses à frente, série suavizada."""
    ep = exp.get_endpoint("ExpectativasMercadoInflacao12Meses")
    df = (
        ep.query()
        .filter(ep.Indicador == "IPCA", ep.Data >= data_inicio, ep.Suavizada == "S")
        .select(ep.Indicador, ep.Data, ep.Mediana, ep.baseCalculo)
        .collect()
    )
    df["Indicador"] = _IPCA_12M
    df["DataReferencia"] = "12m"
    return df


def atualizar_cache_raw(cache_path: Path = _CACHE_RAW) -> pd.DataFrame:
    """
    Baixa expectativas do OData e mantém cache incremental em CSV.

    Só busca pesquisas com Data posterior à última já cacheada; o merge
    remove duplicatas por (Indicador, Data, DataReferencia).
    """
    from bcb import Expectativas

    antigo = pd.DataFrame()
    data_inicio = _DATA_INICIO
    if cache_path.exists():
        antigo = pd.read_csv(cache_path, parse_dates=["Data"])
        if not antigo.empty:
            if antigo["Data"].min().strftime("%Y-%m-%d") > _DATA_INICIO:
                # Backfill: o cache começa depois do início requerido (ex.:
                # cobertura ampliada de 2020 → 2016). Re-baixa o range
                # completo; o dedup do merge absorve a sobreposição.
                log.info("Cache começa em %s > %s — backfill completo.",
                         antigo["Data"].min().date(), _DATA_INICIO)
            else:
                # Re-baixa a partir do último dia cacheado (inclusive) para
                # capturar revisões intradiárias sem duplicar o histórico.
                data_inicio = antigo["Data"].max().strftime("%Y-%m-%d")

    log.info("OData: baixando expectativas a partir de %s...", data_inicio)
    exp = Expectativas()
    ep_anual = exp.get_endpoint("ExpectativasMercadoAnuais")

    partes = []
    for ind in _INDICADORES_ANUAIS:
        try:
            partes.append(_baixar_anuais(ep_anual, ind, data_inicio))
            log.info("  %s: ok", ind)
        except Exception as exc:
            log.warning("  %s: falhou (%s) — segue sem este indicador.", ind, exc)

    try:
        partes.append(_baixar_ipca_12m(exp, data_inicio))
        log.info("  IPCA 12m (suavizada): ok")
    except Exception as exc:
        log.warning("  IPCA 12m: falhou (%s).", exc)

    if not partes:
        if antigo.empty:
            raise RuntimeError("OData indisponível e sem cache local — nada a fazer.")
        log.warning("OData indisponível — usando apenas o cache local.")
        return antigo

    novo = pd.concat(partes, ignore_index=True)
    novo["Data"] = pd.to_datetime(novo["Data"])
    novo["DataReferencia"] = novo["DataReferencia"].astype(str)

    base = pd.concat([antigo, novo], ignore_index=True) if not antigo.empty else novo
    base["DataReferencia"] = base["DataReferencia"].astype(str)
    base = base.drop_duplicates(
        subset=["Indicador", "Data", "DataReferencia", "baseCalculo"], keep="last"
    ).sort_values(["Indicador", "Data", "DataReferencia"]).reset_index(drop=True)

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    base.to_csv(cache_path, index=False)
    log.info("Cache bruto: %d linhas → %s", len(base), cache_path)
    return base


# ---------------------------------------------------------------------------
# Registro de erros (convenção do projeto: falha por série, não global)
# ---------------------------------------------------------------------------

def _registrar_erro(msg: str) -> None:
    Path("logs").mkdir(exist_ok=True)
    with open("logs/erros.md", "a", encoding="utf-8") as f:
        f.write(f"\n## coletar_expectativas — {datetime.now():%Y-%m-%d %H:%M}\n- {msg}\n")


# ---------------------------------------------------------------------------
# Interface principal
# ---------------------------------------------------------------------------

def gerar(destino: Path = _CSV_SAIDA) -> pd.DataFrame:
    """
    Atualiza o cache OData, alinha às reuniões de scores_consolidado.csv
    e salva expectativas_reunioes.csv.
    """
    if not _CSV_SCORES.exists():
        raise FileNotFoundError(
            f"{_CSV_SCORES} não encontrado — rode montar_tabela() antes "
            "(as reuniões vêm de lá)."
        )
    scores = pd.read_csv(_CSV_SCORES)
    reunioes = scores[["nro_reuniao", "data"]].to_dict("records")

    try:
        raw = atualizar_cache_raw()
    except Exception as exc:
        _registrar_erro(f"OData: {type(exc).__name__}: {exc}")
        if not _CACHE_RAW.exists():
            raise
        log.warning("Usando cache bruto existente após falha do OData.")
        raw = pd.read_csv(_CACHE_RAW, parse_dates=["Data"])

    raw["DataReferencia"] = raw["DataReferencia"].astype(str)
    df = alinhar_reunioes(raw, reunioes)

    destino.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(destino, index=False, float_format="%.4f")
    log.info("expectativas_reunioes.csv salvo (%d reuniões).", len(df))
    return df


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    df = gerar()
    print("\nExpectativas Focus na véspera de cada reunião (últimas 8):")
    print(df.tail(8).to_string(index=False))
    print(f"\n→ {_CSV_SAIDA} ({len(df)} linhas)")
