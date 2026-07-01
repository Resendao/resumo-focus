"""
src/graficos.py

Dois gráficos diagnósticos para o paper Copom Tom Index.

Gráfico 1 — fig1_tom.png
    Índice de Tom ao longo do tempo, uma linha por LLM.
    Eixo y: −3 (fortemente dovish) → +3 (fortemente hawkish).
    O baseline léxico é omitido dos gráficos (aparece apenas nas tabelas).

Gráfico 2 — fig2_zscore.png
    Z-score do tom por modelo — a "surpresa de comunicação".
    z(t) = (score(t) − μ_modelo) / σ_modelo
    Facetado por modelo, barras coloridas por direção (hawkish/dovish).

Uso em chunk Quarto silencioso
--------------------------------
    ```{python}
    #| echo: false
    #| output: false
    import sys; sys.path.insert(0, "src")
    from graficos import salvar_graficos
    salvar_graficos()
    ```

    ```{python}
    #| echo: false
    from IPython.display import Image
    Image("output/graficos/fig1_tom.png")
    ```
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from plotnine import (
    ggplot, aes,
    geom_col, geom_hline, geom_line, geom_point,
    scale_color_manual, scale_fill_manual,
    scale_x_datetime, scale_x_discrete, scale_y_continuous,
    facet_wrap,
    labs, theme_bw, theme,
    element_blank, element_rect, element_text,
)

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ---------------------------------------------------------------------------
# Paleta Análise Macro
# ---------------------------------------------------------------------------

_PAL = {
    "Gemini": "#1d3557",   # azul-marinha profundo
    "Claude": "#e07b39",   # âmbar queimado
    "OpenAI": "#2e7d6e",   # verde-azulado
}
_CINZA    = "#888888"
_CINZA_CL = "#dddddd"

# Cores de direção (para z-score)
_PAL_DIR = {
    "Hawkish": "#c0392b",   # vermelho-tijolo
    "Dovish":  "#2e7d6e",   # verde-azulado
}

# Tema base reutilizável
def _tema(figure_size=(10, 5)):
    return (
        theme_bw()
        + theme(
            figure_size=figure_size,
            text=element_text(family="DejaVu Sans", size=10),
            plot_title=element_text(size=13, face="bold", color="#1d3557"),
            plot_subtitle=element_text(size=9.5, color="#555555"),
            plot_caption=element_text(size=8, color="#999999"),
            axis_title=element_text(size=10),
            legend_title=element_text(size=9, face="bold"),
            legend_text=element_text(size=9),
            legend_position="bottom",
            panel_grid_minor=element_blank(),
            panel_grid_major_x=element_blank(),
            panel_background=element_rect(fill="#f8f8f8"),
            plot_background=element_rect(fill="white"),
        )
    )

# ---------------------------------------------------------------------------
# Preparação dos dados
# ---------------------------------------------------------------------------

_CSV = Path("output/scores/scores_consolidado.csv")

_COLUNAS_LLM = ["score_gemini", "score_claude", "score_openai"]
_NOMES = {
    "score_gemini": "Gemini",
    "score_claude": "Claude",
    "score_openai": "OpenAI",
}


def _para_longo(df: pd.DataFrame) -> pd.DataFrame:
    """Wide → long, só colunas LLM disponíveis, sem NaN."""
    cols = [c for c in _COLUNAS_LLM if c in df.columns]
    if not cols:
        raise ValueError(
            "scores_consolidado.csv não tem nenhuma coluna de score de LLM "
            f"({', '.join(_COLUNAS_LLM)})."
        )
    longo = (
        df[["data"] + cols]
        .melt(id_vars="data", var_name="modelo", value_name="score")
        .dropna(subset=["score"])
    )
    longo["modelo"] = longo["modelo"].map(_NOMES)
    longo["data"]   = pd.to_datetime(longo["data"])
    return longo.sort_values(["modelo", "data"]).reset_index(drop=True)


def _zscore_por_modelo(longo: pd.DataFrame) -> pd.DataFrame:
    """Adiciona coluna z-score dentro de cada modelo."""
    def _z(x):
        s = x.std(ddof=1)
        return (x - x.mean()) / s if s > 1e-9 else pd.Series(0.0, index=x.index)

    df = longo.copy()
    df["zscore"]  = df.groupby("modelo")["score"].transform(_z)
    df["direcao"] = df["zscore"].apply(lambda z: "Hawkish" if z >= 0 else "Dovish")

    # Etiqueta de data como categórica ordenada (preserva ordem temporal no eixo x)
    df = df.sort_values("data")
    datas_ord = df["data"].dt.strftime("%b/%y").unique().tolist()
    df["reuniao"] = pd.Categorical(
        df["data"].dt.strftime("%b/%y"),
        categories=datas_ord,
        ordered=True,
    )
    return df.dropna(subset=["zscore"])


# ---------------------------------------------------------------------------
# Gráfico 1 — Índice de Tom ao longo do tempo
# ---------------------------------------------------------------------------

def grafico_tom(longo: pd.DataFrame) -> object:
    """
    Linha por LLM mostrando o Índice de Tom ao longo das reuniões do Copom.

    Linhas de referência:
      —— y = 0  (neutro)
      ·· y = ±1 (zona de leve viés)
    """
    # Intervalo de datas adaptativo: evita ticks ausentes (n pequeno) ou excesso (série longa)
    meses = (longo["data"].max() - longo["data"].min()).days / 30.5
    if meses < 6:
        _breaks = "1 month"
    elif meses < 24:
        _breaks = "3 months"
    elif meses < 60:
        _breaks = "6 months"
    elif meses < 120:
        _breaks = "1 year"
    else:
        _breaks = "2 years"

    p = (
        ggplot(longo, aes("data", "score", color="modelo", group="modelo"))
        # referências horizontais
        + geom_hline(yintercept=0,  linetype="dashed", color=_CINZA,    size=0.55)
        + geom_hline(yintercept=1,  linetype="dotted", color=_CINZA_CL, size=0.4)
        + geom_hline(yintercept=-1, linetype="dotted", color=_CINZA_CL, size=0.4)
        # séries
        + geom_line(size=1.0)
        + geom_point(size=3.0, fill="white")
        # escalas
        + scale_color_manual(name="Modelo", values=_PAL)
        + scale_y_continuous(
            name="Tom",
            limits=(-3.3, 3.3),
            breaks=[-3, -2, -1, 0, 1, 2, 3],
            labels=[
                "−3\n(dovish)", "−2", "−1",
                "0\n(neutro)",
                "+1", "+2", "+3\n(hawkish)",
            ],
        )
        + scale_x_datetime(date_labels="%b/%y", date_breaks=_breaks)
        # rótulos
        + labs(
            title="Índice de Tom das Atas do Copom",
            subtitle=(
                "Escala −3 (fortemente dovish) → +3 (fortemente hawkish)  ·  "
                "Scoring via LLM zero-shot  ·  Baseline léxico omitido"
            ),
            x="Data da Reunião",
            caption=(
                "Fonte: BCB — Atas do Copom.  "
                "Modelos: Gemini Flash Lite, Claude Haiku, GPT-4.1-mini."
            ),
        )
        + _tema((10, 5))
    )
    return p


# ---------------------------------------------------------------------------
# Gráfico 2 — Z-score (Surpresa de Comunicação)
# ---------------------------------------------------------------------------

def grafico_zscore(longo: pd.DataFrame) -> object:
    """
    Z-score do Índice de Tom por LLM.

    |z| > 1  →  comunicação incomum para os padrões do modelo.
    |z| > 2  →  comunicação muito atípica (raramente esperada).

    Facetado por modelo (ncol=1) para comparação vertical.
    Barras vermelhas: tom mais hawkish que o padrão histórico do modelo.
    Barras verdes   : tom mais dovish.
    """
    df_z = _zscore_por_modelo(longo)

    if df_z.empty:
        raise ValueError("Dados insuficientes para calcular z-score (n < 2).")

    p = (
        ggplot(df_z, aes("reuniao", "zscore", fill="direcao"))
        # referências
        + geom_hline(yintercept=0,   color=_CINZA,    size=0.55)
        + geom_hline(yintercept=1,   linetype="dashed", color=_CINZA_CL, size=0.4)
        + geom_hline(yintercept=-1,  linetype="dashed", color=_CINZA_CL, size=0.4)
        # barras
        + geom_col(width=0.55, alpha=0.88)
        # escalas
        + scale_fill_manual(
            name="Direção",
            values=_PAL_DIR,
        )
        + scale_x_discrete(name="Reunião do Copom")
        + scale_y_continuous(
            name="Z-score",
            breaks=[-2, -1, 0, 1, 2],
        )
        # faceta
        + facet_wrap("modelo", ncol=1, scales="free_x")
        # rótulos
        + labs(
            title="Surpresa de Comunicação — Z-score do Índice de Tom",
            subtitle=(
                "z > 0: comunicação mais hawkish que o padrão histórico do modelo  ·  "
                "|z| > 1 ≈ desvio incomum"
            ),
            caption=(
                "Z-score calculado dentro de cada modelo: "
                "z(t) = [score(t) − μ] / σ  (μ e σ históricos do próprio modelo)."
            ),
        )
        + _tema((10, 8))
        + theme(
            strip_text_x=element_text(size=9.5, face="bold", color="#1d3557"),
            panel_spacing=0.35,
        )
    )
    return p


# ---------------------------------------------------------------------------
# API pública — gera e salva os dois PNGs
# ---------------------------------------------------------------------------

def salvar_graficos(
    path_csv: Path = _CSV,
    dir_saida: Path = Path("output/graficos"),
    dpi: int = 150,
) -> tuple[Path, Path]:
    """
    Carrega scores_consolidado.csv, gera os dois gráficos e salva em PNG.

    Parâmetros
    ----------
    path_csv  : caminho para scores_consolidado.csv
    dir_saida : diretório de saída (criado se não existir)
    dpi       : resolução em pontos por polegada (150 = web, 300 = print)

    Retorna
    -------
    (path_fig1, path_fig2) — caminhos dos arquivos gerados
    """
    if not path_csv.exists():
        raise FileNotFoundError(
            f"{path_csv} não encontrado. Rode montar_tabela() primeiro."
        )

    df   = pd.read_csv(path_csv)
    long = _para_longo(df)

    dir_saida.mkdir(parents=True, exist_ok=True)

    f1 = dir_saida / "fig1_tom.png"
    f2 = dir_saida / "fig2_zscore.png"

    grafico_tom(long).save(
        str(f1), dpi=dpi, width=10, height=5, verbose=False
    )
    grafico_zscore(long).save(
        str(f2), dpi=dpi, width=10, height=8, verbose=False
    )

    return f1, f2


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).parent))

    f1, f2 = salvar_graficos()
    print(f"→ {f1}")
    print(f"→ {f2}")
