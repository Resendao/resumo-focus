---
description: Roda o time completo para gerar o boletim macro
---

Coordene o time para gerar o Boletim Macro Semanal com
data de referência `$ARGUMENTS` (use hoje se vazio).

1. Invoque pesquisador-dados — confira CSVs em output/dados/
2. Invoque analista — confira resumo.csv com 4 linhas
3. Invoque redator passando a data $ARGUMENTS
4. Invoque revisor — leia logs/revisao.md
5. Se "ok" → invoque publicador
   Se não → volte ao redator com correções (máx 2 ciclos)
6. Mostre boletim.html, hash do commit e revisao.md final

Pare em qualquer falha. Nunca publique sem "ok".