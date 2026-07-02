"""
src/calibrar.py

Calibração OLS por modelo e testes de comparação entre modelos.

Equação estimada por modelo
----------------------------
    delta_selic(t) = alpha + beta * score_X(t) + eps(t)

    X ∈ {lexico, gemini, claude, openai}

Erros-padrão
------------
    HC3 (MacKinnon & White 1985, correção Long & Ervin 2000).
    HC3 é mais conservador que HC0/HC1 e recomendado para n < 250.

Tabela 1 — coeficientes por modelo
    alpha, beta, SE(beta), t, p, IC95(beta), R², R²_adj, AIC, n

Tabela 2 — comparação entre pares de modelos
    Diebold-Mariano (1995) com correção Harvey-Leybourne-Newbold (1997).
    H₀: os dois modelos têm MSE in-sample igual.
    Estatística: DM_HLN ~ t(n-1) sob H₀.

Quando afirmar robustez
-----------------------
A diferença entre dois modelos é estatisticamente robusta quando:
    • p_DM < 0.05 (dois lados): rejeita H₀ de igual precisão preditiva;
    • E os ICs 95% de beta dos dois modelos não se sobrepõem.

Referências
-----------
Diebold & Mariano (1995) — JBES 13(3)
Harvey, Leybourne & Newbold (1997) — IJF 13(2)
Long & Ervin (2000) — Am. Statistician 54(3)
"""

import logging
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats

log = logging.getLogger(__name__)

_CSV_CONSOLIDADO = Path("output/scores/scores_consolidado.csv")

# Mapeamento nome → coluna no CSV
MODELOS: dict[str, str] = {
    "lexico": "score_lexico",
    "gemini": "score_gemini",
    "claude": "score_claude",
    "openai": "score_openai",
}

# Mínimo de observações para estimar OLS de forma significativa
_MIN_OBS = 5


# ---------------------------------------------------------------------------
# OLS por modelo
# ---------------------------------------------------------------------------

def _ols(y: np.ndarray, x: np.ndarray, nome: str) -> dict:
    """
    OLS simples com erros-padrão HC3.

    HC3 é preferível a HC0 para amostras pequenas: divide os resíduos
    por (1 - h_ii)² em vez de (1 - h_ii), penalizando pontos influentes.
    Em amostras grandes converge para HC0.
    """
    X = sm.add_constant(x, has_constant="add")
    resultado = sm.OLS(y, X).fit(cov_type="HC3")
    ci = resultado.conf_int(alpha=0.05)

    return {
        # identificação
        "modelo":  nome,
        "n":       int(resultado.nobs),
        # parâmetros
        "alpha":   resultado.params[0],
        "beta":    resultado.params[1],
        "se_beta": resultado.bse[1],
        "t":       resultado.tvalues[1],
        "p":       resultado.pvalues[1],
        "ci95_lo": ci[1, 0],
        "ci95_hi": ci[1, 1],
        # ajuste
        "r2":      resultado.rsquared,
        "r2_adj":  resultado.rsquared_adj,
        "aic":     resultado.aic,
        # para DM
        "_resid":  resultado.resid,
        "_index":  np.arange(len(y)),   # índice na sub-amostra sem NaN
    }


def calibrar_um(
    df: pd.DataFrame,
    col_score: str,
    nome: str,
) -> dict | None:
    """
    Calibra OLS para um único modelo. Retorna None se n < _MIN_OBS.
    """
    sub = df[["delta_selic", col_score]].dropna()
    if len(sub) < _MIN_OBS:
        log.warning("Modelo %s: apenas %d obs (mínimo %d). Pulando.", nome, len(sub), _MIN_OBS)
        return None
    return _ols(sub["delta_selic"].values, sub[col_score].values, nome)


# ---------------------------------------------------------------------------
# Diebold-Mariano (HLN) — comparação entre pares
# ---------------------------------------------------------------------------

def _dm_test(
    df: pd.DataFrame,
    col1: str,
    col2: str,
    nome1: str,
    nome2: str,
) -> dict:
    """
    Diebold-Mariano com correção Harvey-Leybourne-Newbold.

    Para garantir que os resíduos são comparáveis, os dois modelos são
    RE-estimados na interseção de observações onde AMBOS têm score não-NaN
    e delta_selic não-NaN. Isso evita viés de comparação entre amostras
    de tamanhos diferentes.

    H₀: E[d_t] = 0, onde d_t = e1_t² − e2_t² (loss diferencial MSE).
    H₁: diferente de zero (two-sided).

    Estatística: DM_HLN = DM * sqrt((n−1)/n) ~ t(n−1) sob H₀.

    Nota sobre interpretação com n pequeno
    ----------------------------------------
    Com n < 20, o teste tem baixo poder — NÃO rejeitar H₀ não implica que
    os modelos são iguais; apenas que a amostra é insuficiente para detectar
    a diferença. Reportar MSE de cada modelo dá contexto adicional.
    """
    mask = (
        df["delta_selic"].notna()
        & df[col1].notna()
        & df[col2].notna()
    )
    sub = df.loc[mask, ["delta_selic", col1, col2]]
    n = len(sub)

    if n < _MIN_OBS:
        return {
            "par": f"{nome1} vs {nome2}", "n_comum": n,
            "mse_1": np.nan, "mse_2": np.nan,
            "dm_hln": np.nan, "p": np.nan, "sig": "—",
            "melhor": "n.d. (n insuf.)",
        }

    y  = sub["delta_selic"].values
    x1 = sub[col1].values
    x2 = sub[col2].values

    # Re-estima ambos na interseção
    res1 = sm.OLS(y, sm.add_constant(x1)).fit()
    res2 = sm.OLS(y, sm.add_constant(x2)).fit()

    e1 = res1.resid
    e2 = res2.resid

    # Loss diferencial
    d = e1 ** 2 - e2 ** 2
    d_bar = d.mean()
    s2_d  = d.var(ddof=1)

    if s2_d <= 1e-14:
        return {
            "par": f"{nome1} vs {nome2}", "n_comum": n,
            "mse_1": round(float((e1**2).mean()), 6),
            "mse_2": round(float((e2**2).mean()), 6),
            "dm_hln": 0.0, "p": 1.0, "sig": "",
            "melhor": "igual",
        }

    dm     = d_bar / np.sqrt(s2_d / n)
    # HLN: ajuste para horizonte h=1 e n finito
    dm_hln = dm * np.sqrt((n - 1) / n)
    p_val  = float(2 * (1 - stats.t.cdf(abs(dm_hln), df=n - 1)))

    sig = "***" if p_val < 0.01 else ("**" if p_val < 0.05 else ("*" if p_val < 0.10 else ""))

    # dm_hln < 0 → d_bar < 0 → e1² < e2² → modelo 1 tem menor MSE
    melhor = nome1 if dm_hln < 0 else (nome2 if dm_hln > 0 else "igual")

    return {
        "par":     f"{nome1} vs {nome2}",
        "n_comum": n,
        "mse_1":   round(float((e1**2).mean()), 6),
        "mse_2":   round(float((e2**2).mean()), 6),
        "dm_hln":  round(float(dm_hln), 3),
        "p":       round(p_val, 4),
        "sig":     sig,
        "melhor":  melhor,
    }


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def calibrar(
    df: pd.DataFrame | None = None,
    csv_path: Path = _CSV_CONSOLIDADO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Calibra OLS para os 4 modelos e calcula DM pairwise.

    Parâmetros
    ----------
    df       : DataFrame já carregado (opcional — lê csv_path se None)
    csv_path : caminho para scores_consolidado.csv

    Retorna
    -------
    tab_coefs : DataFrame  [modelo, n, alpha, beta, se_beta, t, p,
                             ci95_lo, ci95_hi, r2, r2_adj, aic]
    tab_dm    : DataFrame  [par, n_comum, mse_1, mse_2, dm_hln, p, sig, melhor]
    """
    if df is None:
        if not csv_path.exists():
            raise FileNotFoundError(
                f"{csv_path} não encontrado. Rode montar_tabela() primeiro."
            )
        df = pd.read_csv(csv_path)

    df["delta_selic"] = pd.to_numeric(df["delta_selic"], errors="coerce")

    # ── Calibra cada modelo ────────────────────────────────────────────────────
    resultados: dict[str, dict] = {}
    for nome, col in MODELOS.items():
        if col not in df.columns:
            log.info("Coluna %s ausente — modelo %s ignorado.", col, nome)
            continue
        r = calibrar_um(df, col, nome)
        if r is not None:
            resultados[nome] = r

    if not resultados:
        raise ValueError("Nenhum modelo com observações suficientes.")

    # ── Tabela 1: coeficientes ─────────────────────────────────────────────────
    cols_tab = [
        "modelo", "n",
        "alpha", "beta", "se_beta", "t", "p",
        "ci95_lo", "ci95_hi",
        "r2", "r2_adj", "aic",
    ]
    tab_coefs = pd.DataFrame([
        {k: v for k, v in r.items() if k in cols_tab}
        for r in resultados.values()
    ])

    # ── Tabela 2: DM pairwise ─────────────────────────────────────────────────
    nomes_disponiveis = list(resultados.keys())
    dm_rows = []
    for n1, n2 in combinations(nomes_disponiveis, 2):
        dm_rows.append(_dm_test(df, MODELOS[n1], MODELOS[n2], n1, n2))
    tab_dm = pd.DataFrame(dm_rows) if dm_rows else pd.DataFrame()

    return tab_coefs, tab_dm


# ---------------------------------------------------------------------------
# Impressão formatada
# ---------------------------------------------------------------------------

def _estrelas(p: float) -> str:
    if np.isnan(p):
        return "    "
    return "*** " if p < 0.01 else ("**  " if p < 0.05 else ("*   " if p < 0.10 else "    "))


def imprimir(tab_coefs: pd.DataFrame, tab_dm: pd.DataFrame) -> None:
    """Imprime as duas tabelas no terminal com formatação legível."""
    sep90 = "═" * 96
    sep70 = "═" * 74

    # ── Tabela 1 ───────────────────────────────────────────────────────────────
    print(f"\n{sep90}")
    print("TABELA 1 — OLS: delta_selic(t) = α + β·score(t) + ε   [erros HC3]")
    print(sep90)
    print(f"  {'Modelo':<10} {'n':>4}  "
          f"{'α̂':>9}  {'β̂':>9}  {'SE(β̂)':>8}  {'t':>7}  "
          f"{'p':>8}  {'IC 95% de β̂':^22}  "
          f"{'R²':>7}  {'R²adj':>7}  {'AIC':>8}")
    print("─" * 96)

    for _, row in tab_coefs.iterrows():
        stars = _estrelas(row["p"])
        ci    = f"[{row['ci95_lo']:+.3f}, {row['ci95_hi']:+.3f}]"
        r2a   = f"{row['r2_adj']:.4f}" if row["r2_adj"] >= 0 else f"{row['r2_adj']:.4f}"
        print(
            f"  {row['modelo']:<10} {int(row['n']):>4}  "
            f"{row['alpha']:>+9.4f}  {row['beta']:>+9.4f}  {row['se_beta']:>8.4f}  "
            f"{row['t']:>+7.3f}  {row['p']:>7.4f}{stars}  {ci:^22}  "
            f"{row['r2']:>7.4f}  {r2a:>7}  {row['aic']:>8.2f}"
        )

    print(f"\n  {'Sigla':10}  α = intercepto  β = inclinação (sinal correto se β > 0)")
    print(f"  {'HC3':10}  erros-padrão robustos [Long & Ervin 2000]")
    print(f"  {'Sig.':10}  *** p<0.01  ** p<0.05  * p<0.10")

    # ── Tabela 2 ───────────────────────────────────────────────────────────────
    print(f"\n{sep70}")
    print("TABELA 2 — Diebold-Mariano (HLN): H₀: MSE₁ = MSE₂  [t(n−1)]")
    print(sep70)
    print(f"  {'Par':<22}  {'n':>4}  {'MSE₁':>9}  {'MSE₂':>9}  "
          f"{'DM_HLN':>8}  {'p':>8}  {'Sig':>4}  {'Melhor':<12}")
    print("─" * 74)

    if tab_dm.empty:
        print("  (sem pares disponíveis)")
    else:
        for _, row in tab_dm.iterrows():
            dm_str  = f"{row['dm_hln']:>+8.3f}" if not np.isnan(row["dm_hln"]) else f"{'n.d.':>8}"
            p_str   = f"{row['p']:>8.4f}" if not np.isnan(row["p"]) else f"{'n.d.':>8}"
            mse1_s  = f"{row['mse_1']:>9.6f}" if not np.isnan(row["mse_1"]) else f"{'n.d.':>9}"
            mse2_s  = f"{row['mse_2']:>9.6f}" if not np.isnan(row["mse_2"]) else f"{'n.d.':>9}"
            print(
                f"  {row['par']:<22}  {int(row['n_comum']):>4}  "
                f"{mse1_s}  {mse2_s}  "
                f"{dm_str}  {p_str}  {row['sig']:>4}  {row['melhor']:<12}"
            )

    print(f"\n  DM_HLN < 0 → MSE₁ < MSE₂ → modelo 1 é mais preciso")
    print(f"  Harvey, Leybourne & Newbold (1997): DM_HLN = DM × √((n−1)/n) ~ t(n−1)")
    print(f"\n  {'Quando afirmar robustez':}")
    print(f"    Condição forte (conjunta): p_DM < 0.05  E  ICs 95% de β não se sobrepõem.")
    print(f"    Condição fraca (sugestiva): apenas um dos dois critérios satisfeito.")


# ---------------------------------------------------------------------------
# Exercício 2 — Holdout
# ---------------------------------------------------------------------------

def holdout(
    df: pd.DataFrame | None = None,
    n_test: int = 6,
    csv_path: Path = _CSV_CONSOLIDADO,
) -> pd.DataFrame:
    """
    Divide a amostra em treino/teste preservando ordem temporal.

        Treino : todas as reuniões exceto as últimas n_test
        Teste  : últimas n_test reuniões (fora da amostra de estimação)

    Para cada modelo, ajusta OLS no treino e mede RMSE/MAE no teste.
    Não embaralha os dados — a ordem temporal é sagrada em séries macro.

    Colunas: modelo, n_train, n_test, rmse_treino, rmse_teste, mae_teste
    """
    if df is None:
        if not csv_path.exists():
            raise FileNotFoundError(f"{csv_path} não encontrado. Rode montar_tabela() primeiro.")
        df = pd.read_csv(csv_path)

    df = df.copy()
    df["delta_selic"] = pd.to_numeric(df["delta_selic"], errors="coerce")
    df = df.sort_values("data").reset_index(drop=True)

    rows = []
    for nome, col in MODELOS.items():
        if col not in df.columns:
            continue

        sub = df[["delta_selic", col]].dropna().reset_index(drop=True)
        T   = len(sub)

        if T <= n_test + _MIN_OBS:
            log.warning(
                "Modelo %s: %d obs — insuficiente para holdout "
                "(mínimo %d treino + %d teste). Pulando.",
                nome, T, _MIN_OBS, n_test,
            )
            continue

        train = sub.iloc[: T - n_test]
        test  = sub.iloc[T - n_test :]

        X_tr = sm.add_constant(train[col].values, has_constant="add")
        res  = sm.OLS(train["delta_selic"].values, X_tr).fit()

        rmse_treino = float(np.sqrt((res.resid ** 2).mean()))

        X_te  = sm.add_constant(test[col].values, has_constant="add")
        e_oos = test["delta_selic"].values - res.predict(X_te)

        rows.append({
            "modelo":      nome,
            "n_train":     len(train),
            "n_test":      len(test),
            "rmse_treino": round(rmse_treino,                      5),
            "rmse_teste":  round(float(np.sqrt((e_oos**2).mean())), 5),
            "mae_teste":   round(float(np.abs(e_oos).mean()),       5),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Exercício 3 — Walk-forward (janela expansiva)
# ---------------------------------------------------------------------------

def walk_forward(
    df: pd.DataFrame | None = None,
    n_min_treino: int = 20,
    csv_path: Path = _CSV_CONSOLIDADO,
) -> pd.DataFrame:
    """
    Para cada ata t ∈ [n_min_treino, T−1]:
        treino     = atas[0 .. t−1]   (janela expande a cada passo)
        previsão   = ata[t]           (nunca vista durante o treino)

    Varre toda a amostra: n_pred = T − n_min_treino previsões.
    Erros acumulados produzem RMSE e MAE médios.

    Colunas: modelo, n_pred, rmse_wf, mae_wf
    """
    if df is None:
        if not csv_path.exists():
            raise FileNotFoundError(f"{csv_path} não encontrado. Rode montar_tabela() primeiro.")
        df = pd.read_csv(csv_path)

    df = df.copy()
    df["delta_selic"] = pd.to_numeric(df["delta_selic"], errors="coerce")
    df = df.sort_values("data").reset_index(drop=True)

    rows = []
    for nome, col in MODELOS.items():
        if col not in df.columns:
            continue

        sub = df[["delta_selic", col]].dropna().reset_index(drop=True)
        T   = len(sub)

        if T <= n_min_treino:
            log.warning(
                "Modelo %s: %d obs ≤ n_min_treino=%d. Walk-forward pulado.",
                nome, T, n_min_treino,
            )
            continue

        erros: list[float] = []
        for t in range(n_min_treino, T):
            train    = sub.iloc[:t]
            row_test = sub.iloc[t]

            X_tr = sm.add_constant(train[col].values, has_constant="add")
            try:
                res   = sm.OLS(train["delta_selic"].values, X_tr).fit(disp=0)
                x_new = np.array([[1.0, float(row_test[col])]])
                y_hat = float(res.predict(x_new)[0])
                erros.append(float(row_test["delta_selic"]) - y_hat)
            except Exception as exc:
                log.debug("Walk-forward t=%d modelo=%s: %s", t, nome, exc)

        if not erros:
            continue

        e = np.asarray(erros)
        rows.append({
            "modelo":  nome,
            "n_pred":  len(e),
            "rmse_wf": round(float(np.sqrt((e ** 2).mean())), 5),
            "mae_wf":  round(float(np.abs(e).mean()),         5),
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Exercício 4 — Modelo multivariado: tom + expectativas do Focus
# ---------------------------------------------------------------------------

_CSV_EXPECTATIVAS = Path("output/focus/expectativas_reunioes.csv")


def calibrar_multivariado(
    df_scores: pd.DataFrame | None = None,
    df_exp: pd.DataFrame | None = None,
    csv_scores: Path = _CSV_CONSOLIDADO,
    csv_exp: Path = _CSV_EXPECTATIVAS,
) -> pd.DataFrame:
    """
    Compara três especificações com erros-padrão HC3:

        tom                : ΔSelic = α + β₁·score_medio
        desvio_meta        : ΔSelic = α + β₂·desvio_meta
        tom + desvio_meta  : ΔSelic = α + β₁·score_medio + β₂·desvio_meta

    desvio_meta = E[IPCA ano seguinte] − meta CMN (Focus, véspera da reunião)
    — proxy de desancoragem no horizonte relevante. Se o tom da ata carrega
    informação além do que o Focus já precifica, β₁ segue significativo na
    especificação conjunta.

    Colunas: modelo, n, alpha, beta_score, p_score, beta_desvio, p_desvio,
             r2, r2_adj, aic
    """
    if df_scores is None:
        df_scores = pd.read_csv(csv_scores)
    if df_exp is None:
        df_exp = pd.read_csv(csv_exp)

    df = df_scores.merge(
        df_exp[["nro_reuniao", "desvio_meta"]], on="nro_reuniao", how="left"
    )
    df["delta_selic"] = pd.to_numeric(df["delta_selic"], errors="coerce")

    especificacoes = {
        "tom":               ["score_medio"],
        "desvio_meta":       ["desvio_meta"],
        "tom + desvio_meta": ["score_medio", "desvio_meta"],
    }

    rows = []
    for nome, regs in especificacoes.items():
        sub = df[["delta_selic", *regs]].dropna()
        if len(sub) < _MIN_OBS + len(regs) - 1:
            log.warning("Modelo %s: %d obs — insuficiente. Pulando.", nome, len(sub))
            continue

        X = sm.add_constant(sub[regs].values, has_constant="add")
        res = sm.OLS(sub["delta_selic"].values, X).fit(cov_type="HC3")

        idx = {r: i + 1 for i, r in enumerate(regs)}
        rows.append({
            "modelo":      nome,
            "n":           int(res.nobs),
            "alpha":       res.params[0],
            "beta_score":  res.params[idx["score_medio"]] if "score_medio" in idx else np.nan,
            "p_score":     res.pvalues[idx["score_medio"]] if "score_medio" in idx else np.nan,
            "beta_desvio": res.params[idx["desvio_meta"]] if "desvio_meta" in idx else np.nan,
            "p_desvio":    res.pvalues[idx["desvio_meta"]] if "desvio_meta" in idx else np.nan,
            "r2":          res.rsquared,
            "r2_adj":      res.rsquared_adj,
            "aic":         res.aic,
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Impressão formatada — robustez (exercícios 2 e 3)
# ---------------------------------------------------------------------------

def imprimir_robustez(tab_h: pd.DataFrame, tab_wf: pd.DataFrame) -> None:
    """Imprime tabelas do holdout e do walk-forward com nota metodológica."""
    sep74 = "═" * 74

    # ── Exercício 2: Holdout ───────────────────────────────────────────────
    n_test_str = str(int(tab_h["n_test"].iloc[0])) if not tab_h.empty else "6"
    print(f"\n{sep74}")
    print(f"EXERCÍCIO 2 — HOLDOUT  (últimas {n_test_str} reuniões fora da amostra)")
    print(sep74)
    print(f"  {'Modelo':<10}  {'n_train':>7}  {'n_test':>6}  "
          f"{'RMSE treino':>11}  {'RMSE teste':>10}  {'MAE teste':>9}")
    print("─" * 74)

    if tab_h.empty:
        print("  (nenhum modelo com observações suficientes para holdout)")
    else:
        for _, r in tab_h.iterrows():
            flag = "  ▲ overfit" if r["rmse_teste"] > 1.5 * r["rmse_treino"] else ""
            print(
                f"  {r['modelo']:<10}  {int(r['n_train']):>7}  {int(r['n_test']):>6}  "
                f"{r['rmse_treino']:>11.5f}  {r['rmse_teste']:>10.5f}  {r['mae_teste']:>9.5f}"
                f"{flag}"
            )
    print(f"\n  ▲ overfit = RMSE_teste > 1.5 × RMSE_treino (degradação expressiva fora da amostra)")

    # ── Exercício 3: Walk-forward ──────────────────────────────────────────
    print(f"\n{sep74}")
    print("EXERCÍCIO 3 — WALK-FORWARD (janela expansiva, treino mínimo 20 atas)")
    print(sep74)
    print(f"  {'Modelo':<10}  {'n_pred':>6}  {'RMSE_wf':>9}  {'MAE_wf':>9}")
    print("─" * 74)

    if tab_wf.empty:
        print("  (nenhum modelo com observações suficientes para walk-forward)")
    else:
        for _, r in tab_wf.iterrows():
            print(
                f"  {r['modelo']:<10}  {int(r['n_pred']):>6}  "
                f"{r['rmse_wf']:>9.5f}  {r['mae_wf']:>9.5f}"
            )

    # ── Nota metodológica ─────────────────────────────────────────────────
    n_test_val = int(tab_h["n_test"].iloc[0]) if not tab_h.empty else 6
    print(f"""
  NOTA — Viés de janela calma (quiet-window bias)
  ─────────────────────────────────────────────────
  O holdout fixa uma única janela de teste (últimas {n_test_val} reuniões).
  Se esse período for atipicamente estável — por exemplo, Selic inalterada
  em 5 de {n_test_val} reuniões — qualquer modelo com β̂ ≈ 0 parece preciso
  por acidente: errar 0,00 p.p. quando a resposta correta é 0,00 p.p.
  não exige qualidade preditiva real.

  O walk-forward elimina esse viés porque:
    1. Força previsão em TODOS os períodos t > n_min_treino, com peso
       uniforme. Nenhum período calmo pode dominar o RMSE médio.
    2. Detecta deriva temporal: um modelo calibrado em 2019-2021 que passa
       a errar em 2022 (mudança de regime pós-COVID) acumula erros maiores
       ao longo do walk-forward — o holdout fixo pode mascarar essa ruptura.
    3. Sem viés de seleção: a janela de teste não é escolhida pelo analista;
       é determinada mecanicamente pela data mínima de treino.

  Regra: use holdout para entender o comportamento num ciclo específico;
  use walk-forward para afirmar robustez geral da ordenação entre modelos.
""")


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, io, logging
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING)
    sys.path.insert(0, str(Path(__file__).parent))

    tab_c, tab_dm = calibrar()
    tab_h  = holdout()
    tab_wf = walk_forward()

    imprimir(tab_c, tab_dm)
    imprimir_robustez(tab_h, tab_wf)

    # Persiste as tabelas
    out = Path("output/scores")
    out.mkdir(parents=True, exist_ok=True)
    tab_c.round(6).to_csv(out / "calibracao_coefs.csv",       index=False)
    tab_dm.to_csv(         out / "calibracao_dm.csv",          index=False)
    tab_h.to_csv(          out / "calibracao_holdout.csv",     index=False)
    tab_wf.to_csv(         out / "calibracao_walkforward.csv", index=False)
    print(f"→ output/scores/calibracao_coefs.csv       ({len(tab_c)} modelos)")
    print(f"→ output/scores/calibracao_dm.csv          ({len(tab_dm)} pares)")
    print(f"→ output/scores/calibracao_holdout.csv     ({len(tab_h)} modelos)")
    print(f"→ output/scores/calibracao_walkforward.csv ({len(tab_wf)} modelos)")
