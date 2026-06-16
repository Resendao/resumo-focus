"""Pipeline local: baixa o Focus e extrai o texto em sequência."""

import argparse
import sys
import webbrowser
from pathlib import Path

# Adiciona src/ ao caminho de importação sem precisar instalar o pacote
sys.path.insert(0, str(Path(__file__).parent / "src"))

from baixar_focus import baixar
from extrair_texto import extrair


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baixa o Focus e extrai o texto em sequência"
    )
    parser.add_argument(
        "--abrir",
        action="store_true",
        help="Abre o .txt gerado no navegador padrão ao final",
    )
    args = parser.parse_args()

    pasta_data = Path(__file__).parent / "data"

    # Passo 1: baixa o PDF mais recente do BCB
    data_pub, pdf_path = baixar(pasta_data)
    tamanho_kb = pdf_path.stat().st_size / 1024
    print(f"[1/2] PDF baixado: {pdf_path.name} ({tamanho_kb:.1f} KB)")

    # Passo 2: extrai o texto do PDF para .txt e .html
    txt_path, html_path = extrair(pdf_path)
    print(f"[2/2] Texto extraído: {txt_path}")

    # Abre o .html no browser se a flag --abrir foi passada
    if args.abrir:
        webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
