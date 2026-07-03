"""Testes para a escolha de fonte do texto da ata (HTML da API vs PDF)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from baixar_atas import _extrair_fontes


def test_ata_moderna_usa_texto_html():
    item = {"textoAta": "<div>A) Atualização...</div>", "urlPdfAta": "https://x/a.pdf"}
    html, pdf = _extrair_fontes(item)
    assert html == "<div>A) Atualização...</div>"


def test_ata_era_pdf_texto_vazio_devolve_url():
    # Reuniões 200–231: textoAta vem None/vazio e o conteúdo está no PDF
    item = {"textoAta": None, "urlPdfAta": "https://www.bcb.gov.br/content/copom/atascopom/COPOM200.PDF"}
    html, pdf = _extrair_fontes(item)
    assert html is None
    assert pdf.endswith("COPOM200.PDF")


def test_texto_so_de_espacos_conta_como_vazio():
    item = {"textoAta": "   \n ", "urlPdfAta": "https://x/a.pdf"}
    html, pdf = _extrair_fontes(item)
    assert html is None
    assert pdf == "https://x/a.pdf"


def test_janelas_sgs_divide_ranges_longos():
    # A API SGS recusa (HTTP 406) janelas > 10 anos — dividir em fatias
    from coletar_selic import _janelas
    j = _janelas("2015-06-01", "2026-07-03", anos=9)
    assert j[0][0] == "2015-06-01"
    assert j[-1][1] == "2026-07-03"
    assert len(j) == 2
    # fatias contíguas, sem buraco
    assert j[0][1] >= j[1][0]


def test_janelas_sgs_range_curto_uma_fatia():
    from coletar_selic import _janelas
    assert _janelas("2024-01-01", "2026-07-03", anos=9) == [("2024-01-01", "2026-07-03")]
