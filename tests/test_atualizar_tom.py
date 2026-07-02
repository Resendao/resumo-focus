"""Testes para scripts/atualizar_tom.py — lógica de decisão, sem rede."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from atualizar_tom import atas_pendentes, escolher_provedores


class _Doc:
    def __init__(self, nro):
        self.metadata = {"nro_reuniao": nro, "data": "2026-01-01"}


def test_atas_pendentes_identifica_apenas_novas():
    docs = [_Doc(278), _Doc(279), _Doc(280)]
    assert atas_pendentes(docs, {278, 279}) == [280]


def test_atas_pendentes_vazio_quando_tudo_cacheado():
    docs = [_Doc(278), _Doc(279)]
    assert atas_pendentes(docs, {278, 279}) == []


def test_escolher_provedores_com_pendencia_e_chave():
    assert escolher_provedores(pendentes=[280], tem_chave=True) == ("gemini",)


def test_escolher_provedores_sem_pendencia_nao_chama_api():
    # Nada novo → nem com chave disponível deve tocar a API
    assert escolher_provedores(pendentes=[], tem_chave=True) == ()


def test_escolher_provedores_pendencia_sem_chave():
    # Ata nova mas sem GOOGLE_API_KEY (ex.: secret ausente no CI) → só cache
    assert escolher_provedores(pendentes=[280], tem_chave=False) == ()
