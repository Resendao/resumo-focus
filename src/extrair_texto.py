"""Extrai o texto de um PDF do Focus e salva como .txt."""

import argparse
import sys
from pathlib import Path

import pdfplumber


def extrair(pdf_path: str | Path) -> tuple[Path, Path]:
    """Extrai o texto de todas as páginas do PDF e salva em .txt e .html.

    Ambos os arquivos ficam no mesmo diretório do PDF, com o mesmo nome
    e extensões .txt e .html respectivamente.
    Retorna (caminho_txt, caminho_html).
    """
    pdf_path = Path(pdf_path)
    txt_path = pdf_path.with_suffix(".txt")
    html_path = pdf_path.with_suffix(".html")

    paginas = []
    with pdfplumber.open(pdf_path) as pdf:
        for pagina in pdf.pages:
            texto = pagina.extract_text() or ""
            paginas.append(texto)

    # Texto plano — páginas separadas por linha em branco
    conteudo = "\n\n".join(paginas)
    txt_path.write_text(conteudo, encoding="utf-8")

    # HTML — envolve em <pre> para preservar espaçamento e abrir no browser
    titulo = pdf_path.stem.replace("_", " ").title()
    html = (
        "<!DOCTYPE html>\n"
        "<html lang='pt-BR'>\n"
        "<head>\n"
        "  <meta charset='UTF-8'>\n"
        f"  <title>{titulo}</title>\n"
        "  <style>\n"
        "    body { font-family: monospace; font-size: 13px; margin: 2rem; "
        "background: #fafafa; color: #222; }\n"
        "    pre { white-space: pre-wrap; word-break: break-word; "
        "background: #fff; padding: 1.5rem; border: 1px solid #ddd; "
        "border-radius: 6px; }\n"
        "  </style>\n"
        "</head>\n"
        "<body>\n"
        f"<pre>{conteudo}</pre>\n"
        "</body>\n"
        "</html>\n"
    )
    html_path.write_text(html, encoding="utf-8")

    return txt_path, html_path


def _pdf_mais_recente(pasta: Path) -> Path | None:
    """Retorna o focus_*.pdf mais recente em `pasta`, ou None se não houver."""
    candidatos = sorted(pasta.glob("focus_*.pdf"))
    return candidatos[-1] if candidatos else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrai texto de um PDF do Focus e salva como .txt"
    )
    parser.add_argument(
        "--pdf",
        metavar="CAMINHO",
        help="Caminho do PDF a processar (padrão: mais recente em data/)",
    )
    args = parser.parse_args()

    if args.pdf:
        pdf_path = Path(args.pdf)
        if not pdf_path.exists():
            print(f"Erro: arquivo não encontrado: {pdf_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # Procura o PDF mais recente na pasta data/
        pasta_data = Path(__file__).parent.parent / "data"
        pdf_path = _pdf_mais_recente(pasta_data)
        if pdf_path is None:
            print(
                "Nenhum PDF encontrado em data/. "
                "Execute primeiro: python src/baixar_focus.py",
                file=sys.stderr,
            )
            sys.exit(1)

    txt_path, html_path = extrair(pdf_path)
    print(f"Texto extraído: {txt_path}")
    print(f"HTML gerado:    {html_path}")
    print(f"Tamanho:        {txt_path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
