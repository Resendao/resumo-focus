"""
scripts/snapshot.py

Cria um snapshot imutável da release atual em versions/vX.Y.Z_AAAA-MM-DD/.

Uso
---
    python scripts/snapshot.py            # detecta versão do CHANGELOG.md
    python scripts/snapshot.py 0.2.0      # força versão específica

O que é copiado
---------------
    paper_content.qmd     fonte compartilhada
    paper_base.qmd        wrapper base
    paper_publico.qmd     wrapper público
    scores_consolidado.csv dados do momento
    paper_base.pdf        (se existir)
    paper_publico.pdf     (se existir)
    SNAPSHOT.md           descrição gerada automaticamente

O que NÃO é copiado
-------------------
    logs/, atas_cache.json, selic_cache.json — grandes demais ou regeneráveis
    .env.* — credenciais nunca versionadas

Regra de imutabilidade
-----------------------
    Se o diretório de snapshot já existir, o script recusa sobrescrever.
    Use --force apenas em caso de engano — e documente no CHANGELOG.
"""

import sys
import re
import shutil
import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent


def _versao_do_changelog() -> str:
    """Extrai a versão mais recente do CHANGELOG.md (primeira seção [X.Y.Z])."""
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        raise FileNotFoundError("CHANGELOG.md não encontrado.")
    texto = changelog.read_text(encoding="utf-8")
    m = re.search(r"## \[(\d+\.\d+\.\d+)\]", texto)
    if not m:
        raise ValueError("Nenhuma versão [X.Y.Z] encontrada no CHANGELOG.md.")
    return m.group(1)


def _resumo_do_changelog(versao: str) -> str:
    """Extrai o bloco da versão especificada do CHANGELOG.md."""
    texto = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    padrao = rf"## \[{re.escape(versao)}\][^\n]*\n(.*?)(?=\n## \[|\Z)"
    m = re.search(padrao, texto, re.DOTALL)
    return m.group(1).strip() if m else "(sem descrição)"


def snapshot(versao: str | None = None, force: bool = False) -> Path:
    if versao is None:
        versao = _versao_do_changelog()

    hoje = datetime.date.today().isoformat()
    nome = f"v{versao}_{hoje}"
    destino = ROOT / "versions" / nome

    if destino.exists() and not force:
        raise FileExistsError(
            f"{destino} já existe. Use --force para sobrescrever "
            f"(documente o motivo no CHANGELOG)."
        )

    destino.mkdir(parents=True, exist_ok=True)

    # Arquivos a copiar
    FONTES = [
        "paper_content.qmd",
        "paper_base.qmd",
        "paper_publico.qmd",
        "referencias.bib",
        "titlepage.tex",
        "output/scores/scores_consolidado.csv",
        "paper_base.pdf",
        "paper_publico.pdf",
    ]

    copiados = []
    ausentes = []
    for nome_arq in FONTES:
        src = ROOT / nome_arq
        if src.exists():
            shutil.copy2(src, destino / src.name)
            copiados.append(src.name)
        else:
            ausentes.append(src.name)

    # Gera SNAPSHOT.md
    resumo = _resumo_do_changelog(versao)
    snap_md = f"""# Snapshot v{versao} — {hoje}

## Versão
`{versao}` — gerado em {hoje}

## O que mudou (do CHANGELOG)
{resumo}

## Arquivos incluídos
{chr(10).join(f"- {f}" for f in copiados)}

## Arquivos ausentes no momento do snapshot
{chr(10).join(f"- {f}" for f in ausentes) if ausentes else "— nenhum"}

## Reprodução
Para regenerar os PDFs a partir deste snapshot:
```bash
cp versions/{destino.name}/paper_content.qmd .
cp versions/{destino.name}/paper_base.qmd .
cp versions/{destino.name}/paper_publico.qmd .
quarto render paper_base.qmd --to pdf
quarto render paper_publico.qmd --to pdf
```
"""
    (destino / "SNAPSHOT.md").write_text(snap_md, encoding="utf-8")
    copiados.append("SNAPSHOT.md")

    print(f"OK Snapshot criado: {destino.relative_to(ROOT)}")
    print(f"   Arquivos: {', '.join(copiados)}")
    if ausentes:
        print(f"   Ausentes: {', '.join(ausentes)}")

    return destino


if __name__ == "__main__":
    args       = [a for a in sys.argv[1:] if not a.startswith("--")]
    force_arg  = "--force" in sys.argv
    versao_arg = args[0] if args else None
    try:
        snapshot(versao_arg, force=force_arg)
    except FileExistsError as e:
        print(f"ERRO: {e}")
        sys.exit(1)
