"""Testes para o carregamento de cache por provedor em src/scoring.py."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scoring import _cache_df


def test_cache_df_arquivo_inexistente_devolve_vazio_tipado(tmp_path):
    df = _cache_df(tmp_path / "nao_existe.csv")
    assert list(df.columns) == ["nro_reuniao", "data", "score"]
    assert len(df) == 0
    # dtypes compatíveis com merge em chaves int/str — não podem ser object puro
    assert pd.api.types.is_integer_dtype(df["nro_reuniao"])
    assert pd.api.types.is_float_dtype(df["score"])


def test_cache_df_le_arquivo_existente(tmp_path):
    p = tmp_path / "cache.csv"
    pd.DataFrame({
        "nro_reuniao": [277, 278],
        "data": ["2026-03-18", "2026-04-29"],
        "score": [1.25, 2.00],
    }).to_csv(p, index=False)

    df = _cache_df(p)
    assert len(df) == 2
    assert df["score"].tolist() == [1.25, 2.00]


def test_cache_df_vazio_faz_merge_outer_sem_erro():
    # Contrato usado por montar_tabela: merge outer com chaves int64/str
    base = pd.DataFrame({
        "nro_reuniao": [277, 278],
        "data": ["2026-03-18", "2026-04-29"],
        "score_lexico": [0.33, 0.00],
    })
    vazio = _cache_df(Path("nao_existe_em_lugar_nenhum.csv")).rename(
        columns={"score": "score_claude"}
    )
    df = pd.merge(base, vazio, on=["nro_reuniao", "data"], how="outer")
    assert len(df) == 2
    assert df["score_claude"].isna().all()
