# Boletim Macro Semanal

## Objetivo

Toda semana, baixar as séries macroeconômicas do BCB via python-bcb,
calcular variações e gerar um boletim executivo em HTML com os principais
indicadores da conjuntura brasileira.

## Fonte

- API: Banco Central do Brasil — Sistema Gerenciador de Séries Temporais (SGS)
- Biblioteca Python: `from bcb import sgs`
- Séries utilizadas:
  - IPCA mensal: SGS 433
  - Câmbio R$/US$: SGS 1
  - Selic meta: SGS 432
  - IBC-Br original: SGS 24363
  - IBC-Br com ajuste sazonal: SGS 24364

## Convenções

- `output/dados/` guarda os CSVs baixados por série
- `output/tabelas/resumo.csv` tem exatamente 4 linhas (uma por indicador)
- Colunas do resumo: `indicador, unidade, valor_atual, data_ref, var_mes, var_ano, var_12m`
- IBC-Br: `var_mes` vem da série SA (24364); `var_ano` e `var_12m` da série original (24363)
- `logs/revisao.md` começa com "ok" ou "revisar"

## Regras

- Nunca inventar número. Todo valor citado deve vir do resumo.csv.
- Falha por série, não global: se uma série falhar, registra em `logs/erros.md` e segue.
- NA → exibir "indicador indisponível nesta semana", nunca imprimir NaN no HTML.
- Publicador só roda com `logs/revisao.md` começando com "ok".
