"""Testes para src/baixar_focus.py."""

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

# Adiciona src/ ao caminho de importação, igual ao demo.py
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from baixar_focus import baixar, ultima_segunda


# ---------------------------------------------------------------------------
# Testes puros (sem rede) — função ultima_segunda
# ---------------------------------------------------------------------------

def test_ultima_segunda_quinta():
    # Quinta-feira → segunda da mesma semana
    quinta = date(2026, 6, 11)          # quinta
    assert ultima_segunda(quinta) == date(2026, 6, 8)


def test_ultima_segunda_terca():
    # Terça-feira → segunda da mesma semana
    terca = date(2026, 6, 9)            # terça
    assert ultima_segunda(terca) == date(2026, 6, 8)


def test_ultima_segunda_quando_hoje_e_segunda():
    # Segunda-feira → retorna a própria data (comportamento documentado:
    # a rotina pode rodar na segunda à tarde, após a publicação do Focus)
    segunda = date(2026, 6, 8)          # segunda
    resultado = ultima_segunda(segunda)
    assert resultado == segunda


def test_ultima_segunda_domingo():
    # Domingo → segunda da mesma semana (6 dias antes)
    domingo = date(2026, 6, 14)         # domingo
    assert ultima_segunda(domingo) == date(2026, 6, 8)


def test_ultima_segunda_sempre_anterior_e_segunda():
    # Varredura de 60 dias: o retorno deve ser sempre segunda E ≤ data dada
    # (igual apenas quando a própria data é segunda-feira)
    inicio = date(2026, 4, 1)
    for i in range(60):
        dia = inicio + timedelta(days=i)
        resultado = ultima_segunda(dia)
        assert resultado.weekday() == 0, (
            f"{dia} retornou {resultado} que não é segunda-feira"
        )
        assert resultado <= dia, (
            f"{dia} retornou {resultado} que é posterior à data dada"
        )
        if dia.weekday() != 0:
            assert resultado < dia


# ---------------------------------------------------------------------------
# Teste com rede real — função baixar
# ---------------------------------------------------------------------------

@pytest.mark.network
def test_baixar_pdf_real(tmp_path):
    data_pub, caminho = baixar(tmp_path)

    # Arquivo criado
    assert caminho.exists(), "Arquivo PDF não foi criado"

    # Começa com os bytes mágicos do PDF
    assert caminho.read_bytes()[:4] == b"%PDF", "Arquivo não é um PDF válido"

    # Tamanho mínimo (Focus tem várias páginas)
    assert caminho.stat().st_size > 50 * 1024, "PDF menor que 50 KB"

    # Nome bate com a data retornada
    nome_esperado = f"focus_{data_pub.strftime('%Y-%m-%d')}.pdf"
    assert caminho.name == nome_esperado, (
        f"Nome do arquivo '{caminho.name}' não bate com a data '{nome_esperado}'"
    )

    # Data dentro da janela esperada (não no futuro, não mais de 14 dias atrás)
    hoje = date.today()
    assert data_pub <= hoje, "Data de publicação está no futuro"
    assert (hoje - data_pub).days <= 14, (
        f"Data de publicação ({data_pub}) está muito no passado"
    )
