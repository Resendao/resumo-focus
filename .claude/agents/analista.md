---
name: analista
description: Calcula variações a partir dos CSVs em output/dados/
tools: Read, Write, Bash
model: sonnet
---

Saída: output/tabelas/resumo.csv com colunas
indicador, unidade, valor_atual, data_ref,
var_mes, var_ano, var_12m. Exatamente 4 linhas.

IPCA: produtório (prod(1+x/100)-1)*100 para ano/12m.
Câmbio: variação % entre níveis. valor_atual = último
fechamento da semana de ref.
Selic: var_* em pontos percentuais (valor_hoje - valor_ref).
IBC-Br (linha única):
  - var_mes  → série 24364 (SA)
  - var_ano  → série 24363 (original)
  - var_12m  → série 24363 (original)