# Changelog

Todas as mudanças notáveis deste projeto estão documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
O projeto adere a [Versionamento Semântico](https://semver.org/lang/pt-BR/).

---

## Convenção de versão

| Tipo  | Quando usar |
|-------|-------------|
| MAJOR | Nova rodada metodológica — mudança de prompt sistêmica, troca de equação estimada, incorporação de nova série de dados como regressando |
| MINOR | Novos achados com dados reais, extensão de Próximos Passos, adição de LLM, ampliação de cobertura temporal (≥ 20 atas novas) |
| PATCH | Correções de prosa, tipografia, metadados, ajustes cosméticos sem impacto nos números |

**Snapshots** são armazenados em `versions/vX.Y.Z_AAAA-MM-DD/` e contêm:
- `paper_content.qmd` — fonte do conteúdo naquele momento
- `paper_base.qmd` e `paper_publico.qmd` — wrappers
- `scores_consolidado.csv` — estado dos dados
- `SNAPSHOT.md` — descrição do que mudou

---

## [Não lançado]

### Adicionado
- `.github/workflows/copom-tom.yml` — automação semanal do Índice de Tom
  (terças 9h BRT, dia de publicação de ata): `scripts/atualizar_tom.py`
  coleta ata nova, pontua só o que falta (Gemini via secret GOOGLE_API_KEY;
  sem o secret, recompõe do cache e registra aviso), recalibra e regenera
  `data/contexto-tom.md`. Idempotente: semana sem ata nova = zero API,
  zero commit.
- `focus-download.yml` estendido: atualiza `data/focus_expectativas_raw.csv`
  e `output/focus/expectativas_reunioes.csv` toda segunda; passo do
  contexto-focus tolera o 403 do olinda sem derrubar o job; workflows
  compartilham grupo de concorrência para não empurrarem em paralelo.

### Planejado
- Recarregar créditos Claude e OpenAI; popular colunas score_claude, score_openai
  (basta rodar `montar_tabela(docs)` — o cache incremental preenche só o que falta)
- Índice composto ponderado por RMSE walk-forward
- Inclusão do Relatório de Inflação trimestral

---

## [0.2.0] — 2026-07-02

Cobertura completa 232–279 (48 atas) e quantificação do Boletim Focus via
OData, alinhada às reuniões do Copom — base de robustez estatística para o
pipeline de previsão do hub-agentes.

### Adicionado
- `src/coletar_expectativas.py` — série histórica de expectativas Focus
  (IPCA, Selic, Câmbio, PIB anuais + IPCA 12m suavizada) via OData, cache
  incremental em `data/focus_expectativas_raw.csv`; alinhamento pela regra
  da véspera (última pesquisa com Data ≤ reunião − 1 dia) →
  `output/focus/expectativas_reunioes.csv`; metas CMN 2020–2024 + meta
  contínua de 3% a partir de 2025 → coluna `desvio_meta`
- `src/calibrar.py::calibrar_multivariado` — ΔSelic ~ tom + desvio_meta
  (HC3), comparando com as especificações univariadas →
  `output/scores/calibracao_multivariada.csv`
- `src/gerar_contexto_tom.py` — `data/contexto-tom.md` para o hub-agentes:
  tom atual, média móvel 3, ΔSelic implícita da calibração, desancoragem
  Focus e série das últimas 8 reuniões
- `src/scoring.py` — `montar_tabela(docs, provedores=..., pausa=...)`:
  provedor sem crédito só lê cache (sem rajada de erros de billing);
  pausa entre chamadas novas protege o rate limit do free tier
- Testes: `test_expectativas.py`, `test_calibrar_multivariado.py`,
  `test_contexto_tom.py`, `test_scoring_cache.py` (TDD, sem rede)

### Alterado
- Cobertura de scores: 3 → 48 atas (reuniões 232–279, ago/2020–jun/2026);
  Gemini Flash Lite pontuou as 45 novas; léxico recalculado para todas
- `atas_cache.json`: 3 → 48 entradas (A+B extraído de data/raw/)
- Calibração OLS reativada (antes suspensa por n = 2 < 5)
- `tests/test_baixar_focus.py`: dois testes de `ultima_segunda` atualizados
  para o comportamento documentado (aceita a própria segunda-feira)

### Dados desta versão
- Atas: 48 (232–279) · Scores LLM: Gemini completo; Claude/OpenAI aguardando
  crédito (testado em 2026-07-02: ambas as chaves sem saldo)
- Focus: 63.667 observações brutas (jan/2020–jun/2026), 5 séries

---

## [0.1.0] — 2026-06-23

Versão inaugural. Pipeline completo operacional; dados limitados a 3 atas
recentes (reuniões 277–279) enquanto a cobertura histórica é expandida.

### Adicionado
- `src/baixar_atas.py` — coleta e cache de 3 níveis (JSON → raw txt → API BCB)
- `src/coletar_selic.py` — SGS 432 com cache incremental; `alinhar_selic()`
- `src/lexico.py` — dicionário hawkish/dovish (31+32 termos); score `(nₕ−nᵈ)/(nₕ+nᵈ)×3`
- `src/scoring.py` — três scorers LLM via `with_structured_output(TomAta)`;
  `montar_tabela()` com join léxico + LLMs + Selic
- `src/calibrar.py` — OLS com HC3, Diebold-Mariano (HLN), holdout, walk-forward
- `src/graficos.py` — dois gráficos plotnine (paleta Análise Macro)
- `paper_content.qmd` — fonte de conteúdo compartilhada entre as duas edições
- `paper_base.qmd` — edição auditável (`echo: true`)
- `paper_publico.qmd` — edição do leitor (`echo: false`)
- Diff entre edições: **exatamente 2 linhas** (`x-edition` e `echo`)
- `referencias.bib` — 16 entradas (Apel-Grimaldi, Loughran-McDonald, Diebold-Mariano, etc.)
- `titlepage.tex` — capa com `\IfFileExists` para logo opcional
- `CHANGELOG.md` — este arquivo
- `scripts/snapshot.py` — helper para criar snapshots de release

### Dados disponíveis nesta versão
- Atas: reuniões 277, 278, 279 (2026-03-18 a 2026-06-17)
- Scores: apenas Gemini Flash Lite (Claude e OpenAI: crédito insuficiente)
- Calibração OLS: suspensa (`n = 2 < mínimo 5`); tabelas mostram "dado indisponível"

### Infraestrutura
- TinyTeX instalado via `quarto install tinytex`
- Pacotes LaTeX: booktabs, threeparttable, float, caption, microtype, fancyhdr, xcolor
- Python 3.13; todas as dependências em `requirements.txt`
