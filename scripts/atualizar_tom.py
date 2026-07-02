"""
scripts/atualizar_tom.py

Orquestrador do Índice de Tom — pensado para rodar sem supervisão
(GitHub Actions, terças após a publicação de ata) e também localmente.

Encadeia o pipeline completo de forma idempotente:

    1. coletar(232)            — baixa ata nova se houver (cache: nunca re-baixa)
    2. montar_tabela(...)      — pontua SÓ atas fora do cache Gemini; sem
                                 chave de API, recompõe a tabela a partir
                                 do cache (nunca falha por falta de secret)
    3. coletar_expectativas    — OData com fallback para o cache versionado
    4. calibração completa     — OLS, DM, holdout, walk-forward, multivariada
    5. gerar_contexto_tom      — data/contexto-tom.md (cópia p/ hub se local)

Se nada mudou, os arquivos gerados ficam idênticos e o commit do CI é
pulado pelo `git diff --cached --quiet`.

Uso:
    python scripts/atualizar_tom.py
"""

import logging
import os
import sys
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_RAIZ / "src"))

log = logging.getLogger("atualizar_tom")


# ---------------------------------------------------------------------------
# Decisões puras (testáveis sem rede)
# ---------------------------------------------------------------------------

def atas_pendentes(docs: list, cache_nros: set[int]) -> list[int]:
    """Números de reunião presentes em docs mas ausentes do cache de scores."""
    return sorted(
        int(d.metadata["nro_reuniao"])
        for d in docs
        if int(d.metadata["nro_reuniao"]) not in cache_nros
    )


def escolher_provedores(pendentes: list[int], tem_chave: bool) -> tuple[str, ...]:
    """
    Habilita a API do Gemini apenas quando há ata nova E chave disponível.
    Sem pendência não há motivo para tocar a API; sem chave (ex.: secret
    GOOGLE_API_KEY ausente no CI) recompõe do cache e registra o aviso.
    """
    if pendentes and tem_chave:
        return ("gemini",)
    return ()


def _tem_chave_gemini() -> bool:
    """Chave via variável de ambiente (CI) ou .env.gemini (local)."""
    if os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"):
        return True
    env = _RAIZ / ".env.gemini"
    if env.exists():
        conteudo = env.read_text(encoding="utf-8")
        return "GOOGLE_API_KEY" in conteudo or "GEMINI_API_KEY" in conteudo
    return False


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def main() -> int:
    os.chdir(_RAIZ)   # todos os módulos usam caminhos relativos à raiz

    import pandas as pd
    from baixar_atas import coletar
    from scoring import _CACHE_GEMINI, _carregar_cache_csv, montar_tabela
    from calibrar import calibrar, calibrar_multivariado, holdout, walk_forward
    import coletar_expectativas
    import gerar_contexto_tom

    # 1. Atas (cache em 2 níveis; baixa só o que não existe)
    docs = coletar(reuniao_inicial=232)
    if not docs:
        log.error("Nenhuma ata obtida — verifique logs/erros.md.")
        return 1

    # 2. Scores — API só para atas novas com chave disponível
    cache_nros = set(_carregar_cache_csv(_CACHE_GEMINI).keys())
    pendentes = atas_pendentes(docs, cache_nros)
    tem_chave = _tem_chave_gemini()
    provedores = escolher_provedores(pendentes, tem_chave)

    if pendentes and not tem_chave:
        msg = (
            f"Atas {pendentes} sem score Gemini e sem GOOGLE_API_KEY no ambiente "
            "— tabela recomposta do cache; configure o secret para pontuar."
        )
        log.warning(msg)
        Path("logs").mkdir(exist_ok=True)
        from datetime import datetime
        with open("logs/erros.md", "a", encoding="utf-8") as f:
            f.write(f"\n## atualizar_tom — {datetime.now():%Y-%m-%d %H:%M}\n- {msg}\n")

    log.info(
        "Atas: %d | pendentes de score: %s | provedores: %s",
        len(docs), pendentes or "nenhuma", provedores or "nenhum (só cache)",
    )
    montar_tabela(docs, provedores=provedores, pausa=4.0)

    # 3. Expectativas Focus (OData; cai para o cache versionado se bloqueado)
    coletar_expectativas.gerar()

    # 4. Calibração completa
    tab_c, tab_dm = calibrar()
    tab_h = holdout()
    tab_wf = walk_forward()
    tab_mv = calibrar_multivariado()

    out = Path("output/scores")
    out.mkdir(parents=True, exist_ok=True)
    tab_c.round(6).to_csv(out / "calibracao_coefs.csv", index=False)
    tab_dm.to_csv(out / "calibracao_dm.csv", index=False)
    tab_h.to_csv(out / "calibracao_holdout.csv", index=False)
    tab_wf.to_csv(out / "calibracao_walkforward.csv", index=False)
    tab_mv.round(6).to_csv(out / "calibracao_multivariada.csv", index=False)

    # 5. Contexto para o hub-agentes
    gerar_contexto_tom.gerar()

    novas = len(pendentes) if provedores else 0
    print(
        f"\natualizar_tom: {len(docs)} atas | {novas} pontuada(s) nesta execução | "
        f"calibração n={int(tab_c['n'].max())} | contexto-tom.md atualizado."
    )
    return 0


if __name__ == "__main__":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(main())
