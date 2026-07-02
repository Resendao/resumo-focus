# Design: Cobertura completa das atas + série histórica do Focus

**Data:** 2026-07-02
**Status:** aprovado por defaults (usuário AFK; escolhas alinhadas ao plano do CHANGELOG "Não lançado")

## Objetivo

Expandir o Índice de Tom de 3 → 48 atas (reuniões 232–279) e adicionar a série
histórica de expectativas do Focus alinhada às reuniões do Copom, para dar
robustez estatística ao pipeline de previsão consumido pelo hub-agentes.

## Decisões (com alternativas consideradas)

1. **Cobertura das atas: 232–279 (48 atas).**
   Já baixadas em `data/raw/`, formato homogêneo (seções A/B pós-reforma 2016),
   n=47 para ΔSelic — suficiente para OLS HC3, DM e walk-forward (mín. 20 treino).
   *Alternativas:* desde a 200 (~2016, exige validação de formato) ou todas as
   259 da API (formatos incompatíveis pré-2016). Ficam como extensão futura.

2. **Scoring LLM: só Gemini agora.**
   Testado em 2026-07-02: chaves Claude e OpenAI seguem sem crédito (billing).
   O cache incremental (`scores_*_cache.csv`) preenche as colunas faltantes
   automaticamente quando os créditos forem recarregados — basta rodar
   `montar_tabela()` de novo.
   *Alternativa descartada sem aprovação explícita:* pontuar score_claude via
   subagentes do Claude Code (modelo ≠ haiku-4.5 API; implicação metodológica).

3. **Focus: série OData histórica, não tone-scoring de PDFs.**
   O Focus já é numérico. Quantificação = expectativas (medianas, baseCalculo=0)
   alinhadas à véspera de cada reunião do Copom. Vira regressor no modelo
   multivariado e alimenta o hub. Testado: olinda.bcb.gov.br responde 200
   localmente (o 403 de 01/07 era do ambiente cloud da rotina).

## Componentes

### A. `src/scoring.py` (modificação pequena)
- `montar_tabela(docs, provedores=("gemini","claude","openai"), pausa=0.0)` —
  provedores fora da lista só leem o cache CSV (não chamam API, não geram
  erro de billing em loop); `pausa` = segundos entre chamadas LLM novas
  (rate limit do free tier Gemini ~15 RPM → pausa 4s).

### B. Expansão dos scores (execução, sem código novo)
- `coletar(232)` extrai A+B das 45 atas raw restantes → `atas_cache.json`.
- `montar_tabela(docs, provedores=("gemini",), pausa=4.0)` →
  `output/scores/scores_consolidado.csv` com 48 linhas
  (score_claude/score_openai ficam vazios, colunas preservadas).

### C. `src/coletar_expectativas.py` (novo módulo)
- Baixa via `python-bcb` (`Expectativas`):
  - `ExpectativasMercadoAnuais`: IPCA, Selic, PIB Total, Câmbio (Data ≥ 2020-01-01)
  - `ExpectativasMercadoInflacao12Meses`: IPCA suavizada 12m
- Cache incremental bruto em `data/focus_expectativas_raw.csv`
  (re-download só de `Data > max(cache)`).
- Alinhamento: para cada reunião, última pesquisa com `Data ≤ data_reuniao − 1`
  (véspera — expectativa formada antes da decisão).
- Metas de inflação (CMN): 2020: 4,00 · 2021: 3,75 · 2022: 3,50 · 2023: 3,25 ·
  2024+: 3,00 (meta contínua de 3% a partir de 2025).
- Saída `output/focus/expectativas_reunioes.csv`:
  `nro_reuniao, data, data_focus, ipca_12m, ipca_ano_corrente, ipca_ano_seguinte,
   meta_ano_seguinte, desvio_meta, selic_fim_ano, cambio_fim_ano, pib_ano_corrente`
  - `desvio_meta = ipca_ano_seguinte − meta_ano_seguinte` (proxy de desancoragem)
- Funções puras testáveis: `ultima_pesquisa_ate(df, cutoff)`, `meta_inflacao(ano)`,
  `alinhar_reunioes(df_raw, reunioes)`.

### D. `src/calibrar.py` (extensão)
- `calibrar_multivariado(csv_scores, csv_expectativas)`:
  ΔSelic(t) = α + β₁·score_médio(t) + β₂·desvio_meta(t) + ε, HC3.
  Compara AIC/R²adj com univariados; salva `output/scores/calibracao_multivariada.csv`.

### E. `src/gerar_contexto_tom.py` (novo)
- Lê `scores_consolidado.csv` + `calibracao_coefs.csv` + `expectativas_reunioes.csv`.
- Gera `data/contexto-tom.md`: último score, média móvel 3 reuniões, β/R² por
  modelo, ΔSelic implícita do tom atual, tabela das últimas 8 reuniões.
- Copia para `C:/Users/Andre/OneDrive/Desktop/hub-agentes/context/` (mesmo padrão
  de `gerar_contexto_focus.py`; falha silenciosa em cloud).
- Regra de ouro: valor incalculável → "dado indisponível", nunca NaN.

## Fluxo de dados

```
data/raw/*.txt ──extrair_ab──> atas_cache.json ──lexico+gemini──> scores_consolidado.csv
olinda OData ──cache──> focus_expectativas_raw.csv ──véspera──> expectativas_reunioes.csv
scores + expectativas ──calibrar/calibrar_multivariado──> calibracao_*.csv
scores + calibração ──gerar_contexto_tom──> data/contexto-tom.md ──> hub-agentes/context/
```

## Tratamento de erros
- Mantém a regra "falha por ata/série, não global" → `logs/erros.md`.
- Gemini 429 de rate-limit: mitigado por `pausa`; ata que falhar fica fora do
  cache e é re-pontuada na próxima execução.
- OData indisponível: `expectativas_reunioes.csv` não é sobrescrito; contexto
  usa o último CSV válido.

## Testes
- `tests/test_expectativas.py`: funções puras (véspera, meta, alinhamento) com
  DataFrames sintéticos — sem rede.
- Testes de rede marcados `@pytest.mark.network` (convenção do pytest.ini).

## Fora de escopo (nesta rodada)
- Re-render completo do paper PDF (células Python são validadas; render fica
  para quando score_claude/openai estiverem populados).
- Índice composto ponderado por RMSE walk-forward (item do CHANGELOG, próxima rodada).
- Download dos ~300 PDFs históricos do Focus (sem valor para o modelo).
