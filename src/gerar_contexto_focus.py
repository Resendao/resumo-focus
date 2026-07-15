"""
src/gerar_contexto_focus.py

Gera data/contexto-focus.md com as expectativas-chave do último Focus.
Usa python-bcb (OData BCB). Copia o resultado para hub-agentes/context/.

Uso:
    python src/gerar_contexto_focus.py
"""

import shutil
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

_DEST = Path("data/contexto-focus.md")
_HUB  = Path("C:/Users/Andre/OneDrive/Desktop/hub-agentes/context")

# Cutoff de 10 dias: captura a última semana mesmo com atrasos de publicação
_CUTOFF_DIAS = 10

_INDICADORES = [
    "IPCA",
    "PIB Total",
    "Câmbio",
    "Selic",
    "IGP-M",
]

_ANOS = [2026, 2027]

# ---------------------------------------------------------------------------
# BCB helpers
# ---------------------------------------------------------------------------

# Cache bruto versionado no repositório, atualizado toda segunda pelo
# GitHub Actions (focus-download.yml). É o fallback quando o host
# olinda.bcb.gov.br está inacessível — caso das rotinas cloud, cujo proxy
# de saída bloqueia esse host (logs/erros.md 2026-07-01).
_CACHE_RAW = Path("data/focus_expectativas_raw.csv")

# Endpoints OData construídos sob demanda: a construção já faz uma chamada
# de metadados ao olinda — no nível do módulo, derrubaria o import inteiro
# em ambientes onde o host é bloqueado, antes de qualquer fallback.
_ep_anual = None
_ep_selic = None
_CACHE_USADO = False


def _conectar() -> bool:
    """Inicializa os endpoints OData; False se o olinda estiver inacessível."""
    global _ep_anual, _ep_selic
    if _ep_anual is not None:
        return True
    try:
        from bcb import Expectativas
        exp = Expectativas()
        _ep_anual = exp.get_endpoint("ExpectativasMercadoAnuais")
        _ep_selic = exp.get_endpoint("ExpectativasMercadoSelic")  # Selic por reunião
        return True
    except Exception as e:
        print(f"  Aviso OData inacessível: {e}")
        return False


def _usou_cache() -> bool:
    return _CACHE_USADO


def _anual_do_cache(indicador: str, cache_path: Path | None = None) -> pd.DataFrame:
    """
    Última janela de _CUTOFF_DIAS do indicador a partir do cache bruto.

    A janela é relativa à pesquisa mais recente DO CACHE (não a hoje):
    se o cache estiver defasado, ainda produz o melhor contexto possível.
    """
    if cache_path is None:
        cache_path = _CACHE_RAW
    if not cache_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(cache_path, parse_dates=["Data"])
    df = df[df["Indicador"] == indicador]
    if df.empty:
        return df
    df = df[df["Data"] >= df["Data"].max() - pd.Timedelta(days=_CUTOFF_DIAS)]
    df["DataReferencia"] = df["DataReferencia"].astype(str)
    return df.sort_values(["Data", "DataReferencia"], ascending=[False, True])


def _anual(indicador: str, n: int = 30) -> pd.DataFrame:
    """
    Retorna expectativas anuais do indicador — até n linhas, ordenadas
    por Data desc em Python (a API não aceita orderby confiável).
    OData primeiro; cache versionado como fallback.
    """
    global _CACHE_USADO
    if _conectar():
        try:
            cutoff = (date.today() - timedelta(days=_CUTOFF_DIAS)).strftime("%Y-%m-%d")
            df = _ep_anual.query().filter(
                _ep_anual.Indicador == indicador,
                _ep_anual.Data >= cutoff,
            ).limit(n).collect()
            return df.sort_values(["Data", "DataReferencia"], ascending=[False, True])
        except Exception as e:
            print(f"  Aviso {indicador} via OData: {e} — tentando cache.")
    df = _anual_do_cache(indicador)
    if not df.empty:
        _CACHE_USADO = True
    return df


def _selic_reunioes(n: int = 12) -> pd.DataFrame:
    """Expectativas de Selic por reunião do Copom (caminho esperado).
    Sem equivalente no cache bruto — indisponível quando o OData falha."""
    if not _conectar():
        return pd.DataFrame()
    try:
        cutoff = (date.today() - timedelta(days=_CUTOFF_DIAS)).strftime("%Y-%m-%d")
        df = _ep_selic.query().filter(
            _ep_selic.Data >= cutoff,
        ).limit(n).collect()
        return df.sort_values(["Data", "DataReferencia"], ascending=[False, True])
    except Exception:
        return pd.DataFrame()

# ---------------------------------------------------------------------------
# Extração de valores
# ---------------------------------------------------------------------------

def _mediana(df: pd.DataFrame, ano: int) -> float | None:
    """Mediana mais recente para um ano de referência.
    DataReferencia vem como string do OData ("2026", "2027"...).
    baseCalculo=0 = todos os respondentes; =1 = top-5.
    """
    sub = df[df["DataReferencia"] == str(ano)]
    if sub.empty:
        return None
    data_max = sub["Data"].max()
    rows = sub[sub["Data"] == data_max]
    if "baseCalculo" in rows.columns:
        rows = rows[rows["baseCalculo"] == 0]
    if rows.empty:
        return None
    return float(rows["Mediana"].iloc[0])


def _mediana_semana_passada(df: pd.DataFrame, ano: int) -> float | None:
    """Mediana de uma semana atrás para calcular a variação semanal."""
    sub = df[df["DataReferencia"] == str(ano)].copy()
    if sub.empty:
        return None
    data_max = sub["Data"].max()
    limite = data_max - pd.Timedelta(days=5)
    sub_ant = sub[sub["Data"] <= limite]
    if sub_ant.empty:
        return None
    data_ant = sub_ant["Data"].max()
    rows = sub_ant[sub_ant["Data"] == data_ant]
    if "baseCalculo" in rows.columns:
        rows = rows[rows["baseCalculo"] == 0]
    if rows.empty:
        return None
    return float(rows["Mediana"].iloc[0])

# ---------------------------------------------------------------------------
# Formatação
# ---------------------------------------------------------------------------

def _delta(hoje: float | None, ha1: float | None) -> str:
    if hoje is None or ha1 is None:
        return "—"
    d = hoje - ha1
    if abs(d) < 0.005:
        return "→"
    return f"{'↑' if d > 0 else '↓'} {'+' if d >= 0 else ''}{d:.2f}"


def _fmt(v: float | None, unid: str) -> str:
    if v is None:
        return "—"
    return f"R$ {v:.2f}" if "R$" in unid else f"{v:.2f}{unid.split()[0]}"

# ---------------------------------------------------------------------------
# Geração do markdown
# ---------------------------------------------------------------------------

def gerar(destino: Path = _DEST) -> Path:
    hoje_iso = date.today().isoformat()

    linhas: list[str] = [
        f"# Contexto: Focus — {hoje_iso}",
        "",
        "> Gerado automaticamente via python-bcb (OData BCB). "
        "Use como âncora de expectativas de mercado.",
        "",
        "## Expectativas anuais (medianas)",
        "",
        "| Indicador | 2026 | Δ sem. | 2027 | Δ sem. |",
        "|-----------|------|--------|------|--------|",
    ]

    unidades = {
        "IPCA": "%", "PIB Total": "%", "Câmbio": "R$/US$",
        "Selic": "% a.a.", "IGP-M": "%",
    }

    dados: dict[str, dict] = {}

    for ind in _INDICADORES:
        try:
            df_ind = _anual(ind)
        except Exception as e:
            print(f"  Aviso {ind}: {e}")
            df_ind = pd.DataFrame()

        unid = unidades.get(ind, "%")
        row: dict = {}
        for ano in _ANOS:
            row[ano] = {
                "hoje": _mediana(df_ind, ano),
                "ha1":  _mediana_semana_passada(df_ind, ano),
            }
        dados[ind] = row

        v26 = _fmt(row[2026]["hoje"], unid)
        d26 = _delta(row[2026]["hoje"], row[2026]["ha1"])
        v27 = _fmt(row[2027]["hoje"], unid)
        d27 = _delta(row[2027]["hoje"], row[2027]["ha1"])
        linhas.append(f"| {ind} | {v26} | {d26} | {v27} | {d27} |")

    # Caminho da Selic por reunião
    try:
        df_sel = _selic_reunioes()
        if not df_sel.empty and "DataReferencia" in df_sel.columns:
            data_max = df_sel["Data"].max()
            proximas = df_sel[df_sel["Data"] == data_max].head(6)
            if not proximas.empty:
                linhas += ["", "## Caminho esperado da Selic (próximas reuniões)", ""]
                for _, r in proximas.iterrows():
                    med = r.get("Mediana")
                    ref = r.get("DataReferencia", "")
                    if med is not None:
                        linhas.append(f"- {ref}: **{float(med):.2f}% a.a.**")
    except Exception as e:
        print(f"  Aviso Selic reuniões: {e}")

    # Síntese para uso dos agentes
    selic_26  = dados.get("Selic",     {}).get(2026, {}).get("hoje")
    selic_ha1 = dados.get("Selic",     {}).get(2026, {}).get("ha1")
    ipca_26   = dados.get("IPCA",      {}).get(2026, {}).get("hoje")
    cambio_26 = dados.get("Câmbio",    {}).get(2026, {}).get("hoje")
    pib_26    = dados.get("PIB Total", {}).get(2026, {}).get("hoje")

    selic_dir = ""
    if selic_26 is not None and selic_ha1 is not None:
        if selic_26 > selic_ha1 + 0.01:
            selic_dir = " — **revisado para cima esta semana**"
        elif selic_26 < selic_ha1 - 0.01:
            selic_dir = " — **revisado para baixo esta semana**"

    linhas += [
        "",
        "## Para uso dos agentes",
        "",
        (f"- **Selic fim-2026**: {selic_26:.2f}% a.a.{selic_dir}"
         if selic_26 is not None else "- Selic 2026: dado indisponível"),
        (f"- **IPCA 2026**: {ipca_26:.2f}% — "
         f"{'ACIMA' if ipca_26 > 3.5 else 'próximo'} da meta de 3%"
         if ipca_26 is not None else "- IPCA 2026: dado indisponível"),
        (f"- **Câmbio 2026**: R$ {cambio_26:.2f}/US$"
         if cambio_26 is not None else "- Câmbio 2026: dado indisponível"),
        (f"- **PIB 2026**: {pib_26:.2f}%"
         if pib_26 is not None else "- PIB 2026: dado indisponível"),
        "",
        (f"_Fonte: cache do repositório — OData indisponível · Referência: {hoje_iso}_"
         if _usou_cache() else
         f"_Fonte: BCB Focus OData · Referência: {hoje_iso}_"),
    ]

    conteudo = "\n".join(linhas) + "\n"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(conteudo, encoding="utf-8")
    print(f"Gerado: {destino}")

    # Copia para hub-agentes (falha silenciosa em ambientes cloud/CI)
    try:
        _HUB.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destino, _HUB / "contexto-focus.md")
        print(f"Copiado: {_HUB / 'contexto-focus.md'}")
    except Exception as e:
        print(f"Aviso: hub-agentes inacessível ({e}), pulando cópia.")

    return destino


if __name__ == "__main__":
    gerar()
