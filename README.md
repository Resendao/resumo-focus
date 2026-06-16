# Focus BCB — Pipeline de Download e Resumo

Pipeline semanal que baixa o Boletim Focus do Banco Central do Brasil,
extrai o texto do PDF e — numa automação agendada — aciona um agente de IA
que lê o texto, identifica as principais revisões da semana e deixa um
resumo executivo como rascunho de e-mail no Gmail para revisão humana antes
do envio.

> **Importante:** os scripts Python fazem apenas download e extração de
> texto. O resumo executivo é escrito por um agente (LLM) que lê o `.txt`
> gerado e sintetiza as informações relevantes. Nenhum número é inventado —
> toda mediana citada no resumo deve estar no texto original.

---

## Estrutura de pastas

```
.
├── src/
│   ├── baixar_focus.py      # baixa o PDF do BCB
│   └── extrair_texto.py     # extrai texto do PDF → .txt e .html
├── tests/
│   └── test_baixar_focus.py # testes unitários e de integração
├── data/                    # PDFs e textos baixados (gerado em runtime)
├── output/
│   └── focus/               # resumos em markdown (versionado)
├── .github/
│   └── workflows/
│       └── focus-download.yml
├── demo.py                  # roda o pipeline localmente
├── requirements.txt
├── pytest.ini
└── CLAUDE.md
```

---

## Rodando localmente

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Baixar o Focus mais recente e abrir no browser
python demo.py --abrir

# Ou rodar cada etapa separadamente:
python src/baixar_focus.py          # baixa o PDF para data/
python src/extrair_texto.py         # extrai o texto do PDF mais recente
python src/extrair_texto.py --pdf data/focus_2026-06-05.pdf  # PDF específico
```

---

## Testes

```bash
# Testes offline (sem rede) — rápidos, rodam sempre
pytest -m "not network" -v

# Testes com download real (requerem conexão com o BCB)
pytest -m network -v

# Todos os testes
pytest -v
```
