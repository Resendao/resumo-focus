"""Testes para scripts/atualizar_tom.py — lógica de decisão, sem rede."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from atualizar_tom import atas_pendentes, formatar_pendentes


class _Doc:
    def __init__(self, nro):
        self.metadata = {"nro_reuniao": nro, "data": "2026-01-01"}


def test_atas_pendentes_identifica_apenas_novas():
    docs = [_Doc(278), _Doc(279), _Doc(280)]
    assert atas_pendentes(docs, {278, 279}) == [280]


def test_atas_pendentes_vazio_quando_tudo_cacheado():
    docs = [_Doc(278), _Doc(279)]
    assert atas_pendentes(docs, {278, 279}) == []


def test_formatar_pendentes_para_github_output():
    # Saída do modo --detectar: números separados por espaço, vazio se nada
    assert formatar_pendentes([280, 281]) == "280 281"
    assert formatar_pendentes([]) == ""
