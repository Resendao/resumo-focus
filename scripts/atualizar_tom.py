"""
scripts/atualizar_tom.py

Orquestrador do Índice de Tom — roda sem supervisão (GitHub Actions,
terças após a publicação de ata) e também localmente.

O scorer oficial do índice é o CLAUDE, executado FORA deste script
(via Claude Code: comando /pontuar-atas localmente, ou claude-code-action
no CI). Este script nunca chama API de LLM — ele:

    1. coletar(232)            — baixa ata nova se houver (cache: nunca re-baixa)
    2. detecta pendências      — atas sem score no cache do Claude
    3. montar_tabela(...)      — consolida APENAS dos caches (provedores=())
    4. coletar_expectativas    — OData com fallback para o cache versionado
    5. calibração completa     — OLS, DM, holdout, walk-forward, multivariada
    6. gerar_contexto_tom      — data/contexto-tom.md (cópia p/ hub se local)

Se nada mudou, os arquivos ficam idênticos e o commit do CI é pulado.

Uso:
    python scripts/atualizar_tom.py             # pipeline completo
    python scripts/atualizar_tom.py --detectar  # só imprime atas pendentes
                                                # de score Claude (p/ CI decidir
                                                # se chama o claude-code-action)
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


def formatar_pendentes(pendentes: list[int]) -> str:
    """Formato do --detectar: números separados por espaço ('' se nada)."""
    return " ".join(str(n) for n in pendentes)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def _pendentes_claude(docs) -> list[int]:
    from scoring import _CACHE_CLAUDE, _carregar_cache_csv

    cache_nros = set(_carregar_cache_csv(_CACHE_CLAUDE).keys())
    return atas_pendentes(docs, cache_nros)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    os.chdir(_RAIZ)   # todos os módulos usam caminhos relativos à raiz

    from baixar_atas import coletar
    from scoring import montar_tabela
    from calibrar import calibrar, calibrar_multivariado, holdout, walk_forward
    import coletar_expectativas
    import gerar_contexto_tom

    # 1. Atas (cache em 2 níveis; baixa só o que não existe)
    docs = coletar(reuniao_inicial=232)
    if not docs:
        log.error("Nenhuma ata obtida — verifique logs/erros.md.")
        return 1

    # 2. Pendências de score Claude (o scorer oficial roda via Claude Code)
    pendentes = _pendentes_claude(docs)

    if "--detectar" in argv:
        print(formatar_pendentes(pendentes))
        return 0

    if pendentes:
        msg = (
            f"Atas {pendentes} sem score Claude — pontue via /pontuar-atas "
            "(Claude Code local) ou aguarde o passo claude-code-action do CI."
        )
        log.warning(msg)
        Path("logs").mkdir(exist_ok=True)
        from datetime import datetime
        with open("logs/erros.md", "a", encoding="utf-8") as f:
            f.write(f"\n## atualizar_tom — {datetime.now():%Y-%m-%d %H:%M}\n- {msg}\n")

    # 3. Consolidação SÓ dos caches — nenhuma API de LLM é chamada aqui
    log.info("Atas: %d | pendentes de score Claude: %s", len(docs), pendentes or "nenhuma")
    montar_tabela(docs, provedores=())

    # 4. Expectativas Focus (OData; cai para o cache versionado se bloqueado)
    coletar_expectativas.gerar()

    # 5. Calibração completa
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

    # 6. Contexto para o hub-agentes
    gerar_contexto_tom.gerar()

    print(
        f"\natualizar_tom: {len(docs)} atas | pendentes de score Claude: "
        f"{formatar_pendentes(pendentes) or 'nenhuma'} | "
        f"calibração n={int(tab_c['n'].max())} | contexto-tom.md atualizado."
    )
    return 0


if __name__ == "__main__":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(main())
