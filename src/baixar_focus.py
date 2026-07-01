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

# Janela de busca: cobre feriados, atrasos e rotinas que rodam com defasagem
_TENTATIVAS = 14


def ultima_segunda(hoje: date) -> date:
    """Retorna a segunda-feira mais próxima anterior ou igual a `hoje`.

    Diferente da versão anterior, aceita HOJE se for segunda-feira — útil
    quando a rotina roda na própria segunda-feira à tarde (após publicação).
    Para evitar pegar uma edição do mesmo dia antes da publicação, o caller
    pode passar `hoje - timedelta(days=1)` explicitamente.
    """
    dias_atras = hoje.weekday()  # 0 = seg (retorna hoje), 1 = ter (retorna ontem), ...
    return hoje - timedelta(days=dias_atras)


def _arquivo_local(dest: Path, data: date) -> Path | None:
    """Retorna o caminho se já temos o PDF desta data em disco."""
    caminho = dest / f"focus_{data.strftime('%Y-%m-%d')}.pdf"
    return caminho if caminho.exists() else None


def baixar(dest: str | Path, forcar: bool = False) -> tuple[date, Path]:
    """Baixa o PDF Focus mais recente para a pasta `dest`.

    Antes de baixar, verifica se o PDF mais recente já existe no disco
    (evita re-downloads desnecessários e torna a rotina idempotente).

    Parte da última segunda-feira e recua _TENTATIVAS dias (padrão 14),
    cobrindo feriados, atrasos e rotinas que rodam com mais de uma semana
    de defasagem. Valida que o arquivo é PDF pelos bytes iniciais (%PDF).

    Retorna (data_da_publicacao, caminho_do_arquivo).
    Levanta RuntimeError se nenhuma tentativa funcionar.
    """
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    # Ponto de partida: segunda-feira desta semana (ou a anterior se hoje < terça)
    data_inicio = ultima_segunda(date.today())

    # Verifica cache local antes de qualquer download
    if not forcar:
        for d in range(_TENTATIVAS * 7):
            data_check = data_inicio - timedelta(days=d)
            existente = _arquivo_local(dest, data_check)
            if existente:
                return data_check, existente

    # Download: varre _TENTATIVAS dias a partir da segunda mais recente
    data_tentativa = data_inicio
    for _ in range(_TENTATIVAS):
        url = _URL_BASE.format(data=data_tentativa.strftime("%Y%m%d"))

        try:
            resposta = requests.get(url, headers=_HEADERS, timeout=30)
        except requests.RequestException:
            data_tentativa -= timedelta(days=1)
            continue

        if resposta.status_code == 200 and resposta.content[:4] == b"%PDF":
            nome_arquivo = f"focus_{data_tentativa.strftime('%Y-%m-%d')}.pdf"
            caminho = dest / nome_arquivo
            caminho.write_bytes(resposta.content)
            return data_tentativa, caminho

        data_tentativa -= timedelta(days=1)

    raise RuntimeError(
        f"Nenhum PDF do Focus encontrado nas últimas {_TENTATIVAS} tentativas. "
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
