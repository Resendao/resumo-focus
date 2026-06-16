"""Baixa o PDF mais recente do Boletim Focus do Banco Central do Brasil."""

import sys
from datetime import date, timedelta
from pathlib import Path

import requests

# URL base do Focus no site do BCB
_URL_BASE = "https://www.bcb.gov.br/content/focus/focus/R{data}.pdf"

# Cabeçalho que simula um navegador comum para evitar bloqueios
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}


def ultima_segunda(hoje: date) -> date:
    """Retorna a segunda-feira estritamente anterior a `hoje`.

    Se hoje já é segunda-feira, retrocede para a semana passada.
    """
    # Dias até a segunda anterior: weekday() → 0=seg, 6=dom
    dias_atras = hoje.weekday() + 7 if hoje.weekday() == 0 else hoje.weekday()
    return hoje - timedelta(days=dias_atras)


def baixar(dest: str | Path) -> tuple[date, Path]:
    """Baixa o PDF Focus mais recente para a pasta `dest`.

    Parte da última segunda-feira e recua dia a dia até 7 tentativas
    (cobre feriados e datas sem publicação). Valida que o arquivo é PDF
    verificando os bytes iniciais (%PDF). Salva como focus_AAAA-MM-DD.pdf.

    Retorna (data_da_publicacao, caminho_do_arquivo).
    Levanta RuntimeError se nenhuma tentativa funcionar.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    data_tentativa = ultima_segunda(date.today())

    for tentativa in range(7):
        url = _URL_BASE.format(data=data_tentativa.strftime("%Y%m%d"))

        try:
            resposta = requests.get(url, headers=_HEADERS, timeout=30)
        except requests.RequestException:
            # Erro de rede: tenta o dia anterior
            data_tentativa -= timedelta(days=1)
            continue

        # Aceita apenas HTTP 200 com conteúdo PDF válido
        if resposta.status_code == 200 and resposta.content[:4] == b"%PDF":
            nome_arquivo = f"focus_{data_tentativa.strftime('%Y-%m-%d')}.pdf"
            caminho = dest / nome_arquivo
            caminho.write_bytes(resposta.content)
            return data_tentativa, caminho

        # PDF não encontrado nesta data: recua um dia
        data_tentativa -= timedelta(days=1)

    raise RuntimeError(
        "Nenhum PDF do Focus encontrado nas últimas 7 tentativas. "
        "Verifique a conexão ou se houve mudança na URL do BCB."
    )


def main() -> None:
    """Baixa o Focus para data/ e imprime caminho e tamanho."""
    pasta = Path(__file__).parent.parent / "data"

    try:
        data_pub, caminho = baixar(pasta)
    except RuntimeError as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        sys.exit(1)

    tamanho_kb = caminho.stat().st_size / 1024
    print(f"Publicação: {data_pub.strftime('%d/%m/%Y')}")
    print(f"Arquivo:    {caminho}")
    print(f"Tamanho:    {tamanho_kb:.1f} KB")


if __name__ == "__main__":
    main()
