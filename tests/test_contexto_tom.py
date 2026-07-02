"""Testes para src/gerar_contexto_tom.py — montagem do markdown, sem I/O."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gerar_contexto_tom import montar_md


def _scores() -> pd.DataFrame:
    return pd.DataFrame({
        "nro_reuniao": [277, 278, 279],
        "data": ["2026-03-18", "2026-04-29", "2026-06-17"],
        "selic": [15.00, 14.75, 14.50],
        "delta_selic": [float("nan"), -0.25, -0.25],
        "score_lexico": [0.33, 0.00, 0.00],
        "score_gemini": [1.25, 2.00, 1.75],
        "score_claude": [float("nan")] * 3,
        "score_openai": [float("nan")] * 3,
        "score_medio": [1.25, 2.00, 1.75],
    })


def _coefs() -> pd.DataFrame:
    return pd.DataFrame({
        "modelo": ["gemini"], "n": [47],
        "alpha": [-0.1], "beta": [0.2], "se_beta": [0.05],
        "t": [4.0], "p": [0.0002],
        "ci95_lo": [0.1], "ci95_hi": [0.3],
        "r2": [0.45], "r2_adj": [0.44], "aic": [10.0],
    })


def test_montar_md_contem_ultimo_score_e_reuniao():
    md = montar_md(_scores(), _coefs(), None)
    assert "279" in md
    assert "+1.75" in md         # último score_medio, com sinal
    assert "hawkish" in md.lower()


def test_montar_md_previsao_implicita_usa_calibracao():
    # ΔSelic implícita = alpha + beta·score_gemini = −0.1 + 0.2·1.75 = +0.25
    md = montar_md(_scores(), _coefs(), None)
    assert "+0.25" in md


def test_montar_md_previsao_usa_score_do_proprio_modelo():
    # O β de cada modelo foi calibrado no SEU score — o melhor modelo por R²
    # (aqui: lexico) deve ser aplicado a score_lexico (0.00), não a score_medio.
    coefs = pd.DataFrame({
        "modelo": ["lexico", "gemini"], "n": [47, 47],
        "alpha": [0.14, -0.1], "beta": [0.2, 0.2], "se_beta": [0.04, 0.05],
        "t": [5.0, 4.0], "p": [0.0001, 0.0002],
        "ci95_lo": [0.12, 0.1], "ci95_hi": [0.28, 0.3],
        "r2": [0.41, 0.34], "r2_adj": [0.40, 0.33], "aic": [59.6, 64.4],
    })
    md = montar_md(_scores(), coefs, None)
    # lexico: 0.14 + 0.2·0.00 = +0.14 (e não 0.14 + 0.2·1.75 = +0.49)
    assert "+0.14" in md
    assert "+0.49" not in md


def test_montar_md_sem_calibracao_exibe_indisponivel():
    md = montar_md(_scores(), None, None)
    assert "dado indisponível" in md
    # Nunca vaza NaN no markdown
    assert "nan" not in md.lower().replace("indisponível", "")
