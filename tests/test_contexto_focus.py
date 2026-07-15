"""
Testes do fallback de cache do gerar_contexto_focus.

O ambiente das rotinas cloud bloqueia olinda.bcb.gov.br (403 no proxy de
saída — logs/erros.md 2026-07-01). O contexto deve então ser gerado a
partir do cache versionado data/focus_expectativas_raw.csv, que o GitHub
Actions atualiza toda segunda.
"""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import gerar_contexto_focus as gcf


@pytest.fixture
def cache_csv(tmp_path):
    """Cache bruto mínimo: duas semanas de IPCA e Selic."""
    df = pd.DataFrame([
        # semana antiga (fora da janela de 10 dias a partir do máximo)
        {"Indicador": "IPCA",  "Data": "2026-06-15", "DataReferencia": "2026", "Mediana": 5.10, "baseCalculo": 0},
        # semana anterior (dentro da janela — base do delta semanal)
        {"Indicador": "IPCA",  "Data": "2026-06-29", "DataReferencia": "2026", "Mediana": 5.00, "baseCalculo": 0},
        {"Indicador": "IPCA",  "Data": "2026-06-29", "DataReferencia": "2027", "Mediana": 4.40, "baseCalculo": 0},
        # semana mais recente
        {"Indicador": "IPCA",  "Data": "2026-07-06", "DataReferencia": "2026", "Mediana": 4.90, "baseCalculo": 0},
        {"Indicador": "IPCA",  "Data": "2026-07-06", "DataReferencia": "2027", "Mediana": 4.30, "baseCalculo": 0},
        {"Indicador": "Selic", "Data": "2026-07-06", "DataReferencia": "2026", "Mediana": 14.75, "baseCalculo": 0},
    ])
    path = tmp_path / "focus_expectativas_raw.csv"
    df.to_csv(path, index=False)
    return path


def test_anual_do_cache_filtra_indicador_e_janela(cache_csv):
    df = gcf._anual_do_cache("IPCA", cache_path=cache_csv)
    assert not df.empty
    assert set(df["Indicador"]) == {"IPCA"}
    # a linha de 2026-06-15 está fora da janela de 10 dias do máximo (07-06)
    assert df["Data"].min() >= pd.Timestamp("2026-06-29")
    # mais recente primeiro (mesma ordenação do caminho OData)
    assert df.iloc[0]["Data"] == pd.Timestamp("2026-07-06")


def test_anual_do_cache_compativel_com_medianas(cache_csv):
    df = gcf._anual_do_cache("IPCA", cache_path=cache_csv)
    assert gcf._mediana(df, 2026) == 4.90
    assert gcf._mediana_semana_passada(df, 2026) == 5.00


def test_anual_do_cache_sem_arquivo(tmp_path):
    df = gcf._anual_do_cache("IPCA", cache_path=tmp_path / "nao_existe.csv")
    assert df.empty


def test_anual_cai_para_cache_quando_odata_indisponivel(cache_csv, monkeypatch):
    monkeypatch.setattr(gcf, "_conectar", lambda: False)
    monkeypatch.setattr(gcf, "_CACHE_RAW", cache_csv)
    df = gcf._anual("IPCA")
    assert gcf._mediana(df, 2026) == 4.90
    assert gcf._usou_cache()
