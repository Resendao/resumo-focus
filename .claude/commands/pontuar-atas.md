---
description: Pontua com o Claude as atas do Copom que ainda não têm score no cache oficial
---

Você é o **scorer oficial do Índice de Tom** — o mesmo Claude que pontuou as
48 atas históricas (232–279) em 2026-07-02. Sua tarefa é pontuar APENAS as
atas pendentes e atualizar o cache, mantendo consistência com a série existente.

## Passo 1 — Detectar pendências

```
python scripts/atualizar_tom.py --detectar
```

Saída vazia = nada a fazer; diga isso e pare. Caso contrário, a saída lista
os números das reuniões pendentes (ex.: `280 281`).

## Passo 2 — Ler os textos

Para cada reunião pendente, leia `atas_cache.json` e extraia o campo
`texto_ab` da chave correspondente (seções A — conjuntura — e B — riscos).
Se a chave não existir, rode antes `python src/baixar_atas.py`.

## Passo 3 — Pontuar cada ata de forma INDEPENDENTE

Escala contínua de −3.0 a +3.0, precisão de 0.25:

- **−3.0 FORTEMENTE DOVISH**: linguagem explicitamente afrouxadora; projeções muito abaixo da meta; riscos baixistas dominantes; menção a recessão/deflação; guidance de cortes iminentes ou ciclo longo de reduções.
- **−2.0 DOVISH**: viés de afrouxamento claro; inflação convergindo para abaixo da meta; balanço inclinado para baixo; atividade fraca explícita e recorrente; expectativas ancoradas ou abaixo da meta.
- **−1.0 LEVEMENTE DOVISH**: inclinação cautelosa para afrouxamento; inflação na meta com riscos baixistas; mais preocupação com atividade que inflação; guidance suave ("monitorar", "acompanhar com atenção").
- **0.0 NEUTRO / DATA-DEPENDENT**: balanço equilibrado; sem viés direcional; linguagem condicional; inflação na meta com expectativas ancoradas.
- **+1.0 LEVEMENTE HAWKISH**: vigilância inflacionária sem comprometimento explícito; inflação acima da meta ou riscos altistas emergentes; desancoragem incipiente; "cautela", "atenção especial" aos preços.
- **+2.0 HAWKISH**: viés de aperto claro; inflação persistentemente acima da meta; balanço inclinado para cima; desancoragem explícita; guidance de altas ou manutenção elevada por longo período.
- **+3.0 FORTEMENTE HAWKISH**: combate ativo e urgente à inflação; aperto agressivo sinalizado ou em curso; inflação muito acima da meta com persistência; expectativas muito desancoradas; comprometimento com ciclo longo de altas.

Regras obrigatórias:
1. Avalie APENAS o tom do diagnóstico e do balanço de riscos — NÃO se baseie na decisão de taxa já anunciada.
2. Foque em: perspectivas de inflação; ancoragem de expectativas; simetria do balanço de riscos; forward guidance implícito ("prudência", "tempestividade", "vigilância").
3. Linguagem similar → scores próximos, independentemente da decisão de taxa.
4. Riscos altistas e baixistas equivalentes → score próximo de 0.0.

## Passo 4 — Atualizar o cache

Acrescente as linhas novas em `output/scores/scores_claude_cache.csv`
(colunas `nro_reuniao,data,score`; a data vem de `atas_cache.json`; formato
de score com 2 decimais; mantenha ordenado por nro_reuniao; NÃO altere
linhas existentes).

## Passo 5 — Consolidar

```
python scripts/atualizar_tom.py
```

Confirme na saída que não há mais pendências e que o `contexto-tom.md` foi
regenerado. Se estiver num repositório com mudanças a commitar, commite com
mensagem `Tom Copom: score Claude da(s) ata(s) <números>`.
