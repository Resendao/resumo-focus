"""Testes para calibrar_multivariado — dados sintéticos, sem rede."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from calibrar import calibrar_multivariado


def _dados_sinteticos(n: int = 40, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ΔSelic gerado por relação linear conhecida: 0.2·score + 0.15·desvio + ruído."""
    rng = np.random.default_rng(seed)
    score = rng.uniform(-3, 3, n)
    desvio = rng.uniform(-0.5, 2.5, n)
    delta = 0.2 * score + 0.15 * desvio + rng.normal(0, 0.05, n)

    nros = np.arange(232, 232 + n)
    datas = pd.date_range("2020-08-05", periods=n, freq="45D").strftime("%Y-%m-%d")

    scores = pd.DataFrame({
        "nro_reuniao": nros, "data": datas,
        "delta_selic": delta, "score_medio": score,
    })
    exp = pd.DataFrame({
        "nro_reuniao": nros, "data": datas, "desvio_meta": desvio,
    })
    return scores, exp


def test_recupera_coeficientes_conhecidos():
    scores, exp = _dados_sinteticos()
    tab = calibrar_multivariado(df_scores=scores, df_exp=exp)

    linha = tab[tab["modelo"] == "tom + desvio_meta"].iloc[0]
    assert linha["n"] == 40
    assert linha["beta_score"] == pytest.approx(0.2, abs=0.05)
    assert linha["beta_desvio"] == pytest.approx(0.15, abs=0.05)
    assert linha["r2"] > 0.9


def test_inclui_modelos_univariados_para_comparacao():
    scores, exp = _dados_sinteticos()
    tab = calibrar_multivariado(df_scores=scores, df_exp=exp)
    assert set(tab["modelo"]) == {"tom", "desvio_meta", "tom + desvio_meta"}


def test_nan_no_regressor_reduz_n_sem_quebrar():
    scores, exp = _dados_sinteticos()
    exp.loc[:4, "desvio_meta"] = np.nan
    tab = calibrar_multivariado(df_scores=scores, df_exp=exp)
    linha = tab[tab["modelo"] == "tom + desvio_meta"].iloc[0]
    assert linha["n"] == 35
