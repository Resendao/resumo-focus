"""Testes para src/coletar_expectativas.py — funções puras, sem rede."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from coletar_expectativas import (
    alinhar_reunioes,
    meta_inflacao,
    ultima_pesquisa_ate,
)


# ---------------------------------------------------------------------------
# meta_inflacao — metas CMN por ano-calendário
# ---------------------------------------------------------------------------

def test_meta_inflacao_anos_conhecidos():
    assert meta_inflacao(2016) == 4.50
    assert meta_inflacao(2017) == 4.50
    assert meta_inflacao(2018) == 4.50
    assert meta_inflacao(2019) == 4.25
    assert meta_inflacao(2020) == 4.00
    assert meta_inflacao(2021) == 3.75
    assert meta_inflacao(2022) == 3.50
    assert meta_inflacao(2023) == 3.25
    assert meta_inflacao(2024) == 3.00


def test_meta_inflacao_meta_continua_futuro():
    # Meta contínua de 3% vigente a partir de 2025 — vale para qualquer ano futuro
    assert meta_inflacao(2027) == 3.00
    assert meta_inflacao(2030) == 3.00


def test_meta_inflacao_ano_fora_da_cobertura():
    with pytest.raises(ValueError):
        meta_inflacao(2015)


# ---------------------------------------------------------------------------
# ultima_pesquisa_ate — última pesquisa Focus com Data <= cutoff
# ---------------------------------------------------------------------------

def _df_pesquisas(datas: list[str], medianas: list[float]) -> pd.DataFrame:
    return pd.DataFrame({
        "Data": pd.to_datetime(datas),
        "Mediana": medianas,
    })


def test_ultima_pesquisa_ate_inclusivo():
    df = _df_pesquisas(["2026-06-10", "2026-06-14", "2026-06-16"], [5.0, 5.1, 5.2])
    row = ultima_pesquisa_ate(df, pd.Timestamp("2026-06-16"))
    assert row is not None
    assert row["Mediana"] == 5.2


def test_ultima_pesquisa_ate_entre_datas():
    df = _df_pesquisas(["2026-06-10", "2026-06-14", "2026-06-16"], [5.0, 5.1, 5.2])
    row = ultima_pesquisa_ate(df, pd.Timestamp("2026-06-15"))
    assert row["Mediana"] == 5.1


def test_ultima_pesquisa_ate_sem_dados_anteriores():
    df = _df_pesquisas(["2026-06-10"], [5.0])
    assert ultima_pesquisa_ate(df, pd.Timestamp("2026-06-09")) is None


# ---------------------------------------------------------------------------
# alinhar_reunioes — expectativas na véspera de cada reunião do Copom
# ---------------------------------------------------------------------------

def _raw_sintetico() -> pd.DataFrame:
    """Base bruta com pesquisas em 16/06 e 17/06 (dia da reunião)."""
    rows = []
    for data in ["2026-06-16", "2026-06-17"]:
        rows += [
            {"Indicador": "IPCA",      "Data": data, "DataReferencia": "2026", "Mediana": 5.30, "baseCalculo": 0},
            {"Indicador": "IPCA",      "Data": data, "DataReferencia": "2027", "Mediana": 4.10, "baseCalculo": 0},
            {"Indicador": "Selic",     "Data": data, "DataReferencia": "2026", "Mediana": 14.00, "baseCalculo": 0},
            {"Indicador": "Câmbio",    "Data": data, "DataReferencia": "2026", "Mediana": 5.20, "baseCalculo": 0},
            {"Indicador": "PIB Total", "Data": data, "DataReferencia": "2026", "Mediana": 1.97, "baseCalculo": 0},
            {"Indicador": "IPCA_12m",  "Data": data, "DataReferencia": "12m",  "Mediana": 4.60, "baseCalculo": 0},
        ]
    # Pesquisa do dia 17 tem medianas diferentes — não deve ser usada (véspera!)
    df = pd.DataFrame(rows)
    df.loc[df["Data"] == "2026-06-17", "Mediana"] = 99.0
    df["Data"] = pd.to_datetime(df["Data"])
    return df


def test_alinhar_reunioes_usa_vespera():
    reunioes = [{"nro_reuniao": 279, "data": "2026-06-17"}]
    df = alinhar_reunioes(_raw_sintetico(), reunioes)

    assert len(df) == 1
    r = df.iloc[0]
    assert r["nro_reuniao"] == 279
    # Usa a pesquisa de 16/06, nunca a do próprio dia 17/06
    assert r["data_focus"] == "2026-06-16"
    assert r["ipca_ano_corrente"] == 5.30
    assert r["ipca_ano_seguinte"] == 4.10
    assert r["selic_fim_ano"] == 14.00
    assert r["cambio_fim_ano"] == 5.20
    assert r["pib_ano_corrente"] == 1.97
    assert r["ipca_12m"] == 4.60


def test_alinhar_reunioes_desvio_meta():
    reunioes = [{"nro_reuniao": 279, "data": "2026-06-17"}]
    df = alinhar_reunioes(_raw_sintetico(), reunioes)
    r = df.iloc[0]
    # desvio_meta = E[IPCA 2027] − meta 2027 = 4.10 − 3.00
    assert r["meta_ano_seguinte"] == 3.00
    assert r["desvio_meta"] == pytest.approx(1.10)


def test_alinhar_reunioes_indicador_ausente_vira_nan():
    raw = _raw_sintetico()
    raw = raw[raw["Indicador"] != "PIB Total"]
    reunioes = [{"nro_reuniao": 279, "data": "2026-06-17"}]
    df = alinhar_reunioes(raw, reunioes)
    assert pd.isna(df.iloc[0]["pib_ano_corrente"])
    # Os demais campos continuam preenchidos
    assert df.iloc[0]["ipca_ano_corrente"] == 5.30
