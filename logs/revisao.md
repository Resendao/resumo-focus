ok

Revisão concluída em 2026-05-26. Boletim aprovado para publicação.

---

## Checklist de Verificação

### 1. Números x resumo.csv

| Indicador | Campo       | CSV           | Boletim (inline R)       | Status |
|-----------|-------------|---------------|--------------------------|--------|
| IPCA      | valor_atual | 0.6700        | `fmt(ipca_val)`          | OK     |
| IPCA      | var_mes     | -0.2100       | `fmt(abs(ipca_mes))`     | OK     |
| IPCA      | var_ano     | 2.6043        | `fmt(ipca_ano)`          | OK     |
| IPCA      | var_12m     | 4.3917        | `fmt(ipca_12m)`          | OK     |
| Câmbio    | valor_atual | 4.9886        | `fmt(cambio_val)`        | OK     |
| Câmbio    | var_mes     | -0.2308       | `fmt(abs(cambio_mes))`   | OK     |
| Câmbio    | var_12m     | -0.6722       | `fmt(abs(cambio_12m))`   | OK     |
| Selic     | valor_atual | 14.4000       | `fmt(selic_val)`         | OK     |
| Selic     | var_mes     | -0.2400       | `fmt(selic_mes)`         | OK     |
| Selic     | var_ano     | -0.5000       | `fmt(selic_ano)`         | OK     |
| Selic     | var_12m     | -0.1500       | `fmt(selic_12m)`         | OK     |
| IBC-Br    | valor_atual | 1143880.5000  | `fmt(ibc_val, digits=1)` | OK     |
| IBC-Br    | var_mes     | -1.2709       | `fmt(ibc_mes_sa)`        | OK     |
| IBC-Br    | var_ano     | 5.5729        | `fmt(ibc_ano)`           | OK     |
| IBC-Br    | var_12m     | 5.2069        | `fmt(ibc_12m)`           | OK     |

### 2. Unidades

- Selic expressa em p.p. (pontos percentuais), não em pontos-base: OK
- IPCA em % a.m.: OK
- Câmbio em R$/US$: OK
- IBC-Br como índice: OK

### 3. IBC-Br — identificação das séries

- Variação mensal atribuída explicitamente à série com ajuste sazonal (BCB/SGS cód. 24364): OK
- Variação em 12 meses atribuída explicitamente à série original sem ajuste (BCB/SGS cód. 24363): OK
- Convenção alinhada ao CLAUDE.md: OK

### 4. Tratamento de NA

- Função `fmt()` retorna "indicador indisponível nesta semana" quando x é NA: OK
- Sem ocorrências de NA nos dados correntes: OK

### 5. Coerência interna

- Variação mensal IBC-Br negativa (-1.27%) descrita como "recuo pontual": coerente
- Variação em 12 meses IBC-Br positiva (+5.21%) descrita como "trajetória expansionista robusta": coerente
- Parágrafo de reconciliação entre as duas leituras presente e logicamente consistente: OK
- Câmbio: var_mes e var_12m negativos → texto usa "recuo" e "valorização do real": coerente
- IPCA: var_mes negativa → texto usa "recuo de": coerente
- Selic 14.40% descrita como "patamar contracionista": coerente com nível elevado

### 6. Estilo (CLAUDE.md)

- Sem linguagem preditiva ou de recomendação: OK
- Tom técnico-descritivo mantido ao longo de todas as seções: OK
- Texto de contextualização não extrapola os dados (sem previsões de taxa ou inflação futura): OK

### 7. Estrutura do boletim

- YAML front matter válido para Quarto (title, subtitle, date, format/html, lang): OK
- Quatro seções presentes: IPCA, Câmbio e Juros / Câmbio USD/BRL, Selic, IBC-Br: OK
- Tabela-resumo presente (Quadro-Resumo dos Indicadores): OK
- Nota de referência temporal presente: OK
- Rodapé com fonte e data de referência presente: OK
- Nenhum dado inventado ou inconsistente identificado: OK
