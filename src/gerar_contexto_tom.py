"""
src/gerar_contexto_tom.py

Gera data/contexto-tom.md — o Índice de Tom quantificado para consumo do
hub-agentes. Mesmo padrão de gerar_contexto_focus.py: markdown compacto,
copiado para hub-agentes/context/, sem NaN (regra de ouro: valor
incalculável → "dado indisponível").

Uso:
    python src/gerar_contexto_tom.py
"""

import logging
import shutil
from datetime import date
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

_CSV_SCORES = Path("output/scores/scores_consolidado.csv")
_CSV_COEFS  = Path("output/scores/calibracao_coefs.csv")
_CSV_EXP    = Path("output/focus/expectativas_reunioes.csv")
_DEST       = Path("data/contexto-tom.md")
_HUB        = Path("C:/Users/Andre/OneDrive/Desktop/hub-agentes/context")


# ---------------------------------------------------------------------------
# Helpers de formatação — nunca deixam NaN vazar para o markdown
# ---------------------------------------------------------------------------

def _fmt(v, casas: int = 2, sinal: bool = False) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v:+.{casas}f}" if sinal else f"{v:.{casas}f}"


def _classificar(score: float) -> str:
    if pd.isna(score):
        return "indefinido"
    if score > 0.5:
        return "hawkish"
    if score < -0.5:
        return "dovish"
    return "neutro"


# ---------------------------------------------------------------------------
# Montagem do markdown (pura — testável sem I/O)
# ---------------------------------------------------------------------------

def montar_md(
    scores: pd.DataFrame,
    coefs: pd.DataFrame | None,
    exp: pd.DataFrame | None,
) -> str:
    """
    Markdown do contexto de tom a partir dos CSVs consolidados.

    scores : scores_consolidado.csv (obrigatório)
    coefs  : calibracao_coefs.csv ou None — sem ele, a previsão implícita
             vira "dado indisponível"
    exp    : expectativas_reunioes.csv ou None — acrescenta desancoragem
    """
    scores = scores.sort_values("nro_reuniao").reset_index(drop=True)
    ultimo = scores.iloc[-1]

    # Índice oficial: score do Claude; recua para score_medio se ausente
    usa_claude = "score_claude" in scores.columns and not pd.isna(ultimo["score_claude"])
    col_indice = "score_claude" if usa_claude else "score_medio"
    rotulo = "Claude" if usa_claude else "média dos LLMs"
    tom_atual = ultimo[col_indice]
    mm3 = scores[col_indice].tail(3).mean()

    linhas = [
        f"# Contexto: Índice de Tom do Copom — reunião {int(ultimo['nro_reuniao'])} "
        f"({ultimo['data']})",
        "",
        "> Gerado automaticamente a partir de output/scores/ (léxico + LLMs, "
        f"{len(scores)} atas desde {scores.iloc[0]['data']}). "
        "Escala: −3 (fortemente dovish) a +3 (fortemente hawkish).",
        "",
        "## Sinal atual",
        "",
        f"- **Tom da última ata ({rotulo})**: {_fmt(tom_atual, sinal=True)} "
        f"({_classificar(tom_atual)})",
        f"- **Média móvel (3 reuniões)**: {_fmt(mm3, sinal=True)} "
        f"({_classificar(mm3)})",
        f"- **Selic vigente**: {_fmt(ultimo.get('selic'))}% a.a. "
        f"(Δ última reunião: {_fmt(ultimo.get('delta_selic'), sinal=True)} p.p.)",
    ]

    # Previsão implícita da calibração (melhor modelo por R²).
    # O β de cada modelo foi estimado sobre o SEU score — a previsão usa a
    # coluna correspondente da última ata, nunca score_medio de outro modelo.
    colunas_modelo = {
        "lexico": "score_lexico",
        "gemini": "score_gemini",
        "claude": "score_claude",
        "openai": "score_openai",
    }
    linhas += ["", "## Previsão implícita para a próxima reunião", ""]
    melhor = None
    score_modelo = float("nan")
    if coefs is not None and not coefs.empty:
        melhor = coefs.loc[coefs["r2"].idxmax()]
        col = colunas_modelo.get(str(melhor["modelo"]))
        if col and col in scores.columns:
            score_modelo = ultimo[col]
    if melhor is not None and not pd.isna(score_modelo):
        implicita = float(melhor["alpha"]) + float(melhor["beta"]) * float(score_modelo)
        linhas += [
            f"- **ΔSelic implícita pelo tom atual**: {_fmt(implicita, sinal=True)} p.p. "
            f"(modelo {melhor['modelo']} sobre score {_fmt(score_modelo, sinal=True)}: "
            f"β̂ = {_fmt(melhor['beta'], 3, sinal=True)}, "
            f"R² = {_fmt(melhor['r2'])}, n = {int(melhor['n'])})",
            "- Interpretação: β̂ > 0 significa que tom mais hawkish antecipa "
            "ΔSelic mais alta (menos corte / mais alta).",
        ]
    else:
        linhas += [
            "- ΔSelic implícita: dado indisponível "
            "(calibração ausente ou score do melhor modelo não disponível)"
        ]

    # Desancoragem de expectativas (Focus na véspera)
    if exp is not None and not exp.empty:
        exp = exp.sort_values("nro_reuniao")
        ult_exp = exp.iloc[-1]
        linhas += [
            "",
            "## Expectativas na véspera da última reunião (Focus)",
            "",
            f"- **Desvio da meta (ano seguinte)**: {_fmt(ult_exp.get('desvio_meta'), sinal=True)} p.p. "
            f"(E[IPCA] = {_fmt(ult_exp.get('ipca_ano_seguinte'))}% vs meta "
            f"{_fmt(ult_exp.get('meta_ano_seguinte'))}%)",
            f"- **IPCA 12m suavizado**: {_fmt(ult_exp.get('ipca_12m'))}%",
            f"- **Selic fim de ano**: {_fmt(ult_exp.get('selic_fim_ano'))}% a.a.",
        ]

    # Série recente
    linhas += [
        "",
        "## Últimas 8 reuniões",
        "",
        "| Reunião | Data | Tom | Léxico | Selic | ΔSelic |",
        "|---------|------|-----|--------|-------|--------|",
    ]
    for _, r in scores.tail(8).iterrows():
        linhas.append(
            f"| {int(r['nro_reuniao'])} | {r['data']} | "
            f"{_fmt(r[col_indice], sinal=True)} | "
            f"{_fmt(r.get('score_lexico'), sinal=True)} | "
            f"{_fmt(r.get('selic'))} | {_fmt(r.get('delta_selic'), sinal=True)} |"
        )

    linhas += [
        "",
        f"_Fonte: output/scores/scores_consolidado.csv · Gerado em {date.today().isoformat()}_",
    ]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------------------
# Geração + cópia para o hub
# ---------------------------------------------------------------------------

def gerar(destino: Path = _DEST) -> Path:
    if not _CSV_SCORES.exists():
        raise FileNotFoundError(f"{_CSV_SCORES} não encontrado — rode montar_tabela() antes.")
    scores = pd.read_csv(_CSV_SCORES)

    coefs = pd.read_csv(_CSV_COEFS) if _CSV_COEFS.exists() else None
    exp   = pd.read_csv(_CSV_EXP)   if _CSV_EXP.exists()   else None

    conteudo = montar_md(scores, coefs, exp)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    print(f"Gerado: {destino}")

    # Copia para hub-agentes (falha silenciosa em ambientes cloud/CI)
    try:
        _HUB.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destino, _HUB / "contexto-tom.md")
        print(f"Copiado: {_HUB / 'contexto-tom.md'}")
    except Exception as e:
        print(f"Aviso: hub-agentes inacessível ({e}), pulando cópia.")

    return destino


if __name__ == "__main__":
    import io
    import sys

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    gerar()
