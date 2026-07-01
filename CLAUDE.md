# Índice de Tom das Atas do Copom

## Objetivo

Construir um **Índice de Tom** (escala −3 a +3, hawkish → dovish) das atas do
Copom, calibrado na variação efetiva da Selic, usando três LLMs em paralelo
(Gemini, Claude, OpenAI) e um baseline léxico. Resultado entregue como paper
reproduzível em Quarto.

## Fontes

- **Atas do Copom:** API pública do BCB — `https://www.bcb.gov.br/api/servico/sitebcb/atascopom`
- **Selic meta:** SGS 432 via `from bcb import sgs`
- **Chaves de API:** carregadas de `.env.*` (nunca hardcoded)

## Metodologia — CRISP-DM

| Fase | Descrição |
|------|-----------|
| 1. Entendimento do negócio | Mapear como tom linguístico antecipa decisão de política monetária |
| 2. Entendimento dos dados | Baixar atas e Selic; inspecionar cobertura e formato |
| 3. Preparação dos dados | Limpeza de HTML/PDF, chunking por parágrafo, tokenização |
| 4. Modelagem | Score léxico (baseline) + scoring via 3 LLMs com prompt zero-shot |
| 5. Avaliação | Correlação com Δ Selic; concordância entre LLMs (Krippendorff α) |
| 6. Deploy | Paper Quarto auto-contido (HTML + PDF) com todos os gráficos inline |

## Convenções

- `data/raw/` — atas brutas (HTML ou PDF, nomeadas `copom_AAAA-MM-DD.*`)
- `data/processed/` — texto limpo, uma linha por ata
- `output/scores/` — CSVs com colunas `data, reuniao, score_lexico, score_claude, score_gemini, score_openai, score_medio, delta_selic`
- `output/paper/` — arquivos gerados pelo Quarto
- `src/` — módulos Python (download, limpeza, scoring, gráficos)
- `notebooks/` — exploração; NÃO são fonte de dados para o paper

## Regra de Ouro

**Nunca inventar número.** Todo valor citado no paper vem de uma célula Python
que roda. Se um valor não puder ser calculado, a célula exibe
`"dado indisponível"` — nunca NaN, nunca placeholder.

## Regras adicionais

- Falha por ata, não global: se uma ata falhar o scoring, registra em `logs/erros.md` e segue.
- Reproducibilidade: `quarto render paper.qmd` deve funcionar do zero em qualquer máquina com `.env.*` preenchido.
- LLMs custam dinheiro: cache os scores em `output/scores/` antes de re-renderizar.
