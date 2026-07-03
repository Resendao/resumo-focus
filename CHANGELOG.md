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

---

## [0.4.0] — 2026-07-03

Cobertura ampliada 48 → 80 atas (reuniões 200–279, jul/2016 → jun/2026) —
todo o período do formato atual das atas (reforma Goldfajn). Coleta e
extração 100% via script (zero tokens de LLM); Claude usado apenas no
scoring das 32 atas novas (4 lotes com textos pré-extraídos).

### Adicionado
- `baixar_atas.py`: fallback de PDF para a era 200–231 (textoAta vem vazio
  da API; o conteúdo está em urlPdfAta) — pdfplumber com segundo motor
  pypdf para os PDFs malformados de 2018 (reuniões 217/219/220)
- `coletar_selic.py::_janelas` — SGS 432 buscado em fatias ≤ 9 anos
  (a API retorna HTTP 406 para janelas > 10 anos)
- Backfill automático nos caches de Selic (→ 2015-06) e Focus OData
  (→ 2016-01) quando o início requerido antecede o cache
- Metas CMN 2016–2019 (4,50/4,50/4,50/4,25) em `meta_inflacao`
- Dependências: pdfplumber 0.11.4, pypdf 6.14.2

### Alterado
- `atualizar_tom.py`: cobertura oficial passa a REUNIAO_INICIAL = 200
- score_claude: 80 atas (32 novas pontuadas por Claude via Claude Code,
  mesma rubrica dos lotes de 0.3.0)
- Calibração com n = 79: claude β = 0,302 (p < 0,001), **R² = 0,579**
  (era 0,367 com n = 47); léxico R² = 0,493; walk-forward com 59 previsões
  — claude tem o menor RMSE (0,436). Gemini segue congelado em n = 47.
- Focus: 90.747 obs. brutas (jan/2016 → jun/2026)

---

## [0.3.0] — 2026-07-02

Claude vira o scorer oficial do Índice de Tom; Gemini congelado como
baseline histórico de comparação (sem novas chamadas em nenhum ambiente).

### Adicionado
- `score_claude` completo para as 48 atas (232–279), pontuado por
  **Claude (claude-fable-5) via Claude Code** com a mesma rubrica
  INSTRUCOES_SISTEMA — 8 lotes independentes de 6 atas. **Nota
  metodológica**: difere do desenho original (haiku-4.5 via API); o modelo
  e o mecanismo devem ser citados no paper. Correlação com o Gemini: 0,96.
- Calibração Claude: β = 0,334 (p < 0,001), R² = 0,367, n = 47; multivariado
  tom + desvio_meta sobe para R² = 0,425 com ambos os regressores
  significativos (p_score < 0,001; p_desvio = 0,030)
- `.claude/commands/pontuar-atas.md` — comando para pontuar atas pendentes
  com o Claude (local via Claude Code ou no CI via claude-code-action)
- `copom-tom.yml`: scoring no CI via `anthropics/claude-code-action@v1`,
  autenticado por CLAUDE_CODE_OAUTH_TOKEN (assinatura, `claude setup-token`)
  ou ANTHROPIC_API_KEY; sem secret, a pendência é registrada e o job segue
- `scripts/atualizar_tom.py --detectar` — lista atas sem score Claude
  (usado pelo CI para decidir se chama o claude-code-action)

### Alterado
- **Índice oficial** (contexto do hub, headline e tabela): score_claude,
  com fallback para score_medio quando ausente
- `montar_tabela`: default `provedores=()` — nenhuma chamada de API de LLM
  sem pedido explícito; consolidação é 100% cache
- Gemini: coluna score_gemini congelada como baseline de comparação no
  paper; nenhuma chamada nova ao Gemini em pipeline algum

### Adicionado (automação — antes em Não lançado)
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
