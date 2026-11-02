"""Roda a sync da Pluggy todo dia na hora da agenda (fase 5b, passo 10).

    python -m scripts.agendador               # hora de SYNC_AGENDA, padrão 06:00
    python -m scripts.agendador --uma-vez     # roda agora, uma vez, e sai

É o serviço `agendador` do compose. No modo local, quem agenda é a tarefa do
Windows (`scripts/local/agendar.sh`), que chama o `pluggy_sync` direto.

* **Sem sobrepor execuções.** Uma de cada vez neste laço, e a trava do
  Postgres (`execucao_sync`) recusa a sync se o "Atualizar agora" do painel
  ou um `make sync` estiver rodando: esta desiste e registra, sem esperar.
* **Falha vira log, não retentativa infinita** (roadmap): uma tentativa por
  dia; a seguinte é amanhã, na mesma hora.
* **Log** numa linha por execução, na saída padrão (`docker compose logs
  agendador`), com o que entrou, o que foi para a revisão e os erros.
"""

from __future__ import annotations

import argparse
import sys
import time as relogio
from collections.abc import Callable
from datetime import UTC, datetime, time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings
from app.conversao_pluggy import FUSO
from app.services.execucao_sync import (
    SyncDesligada,
    SyncOcupada,
    executar,
    hora_da_agenda,
    proxima_execucao,
)
from app.services.sync_pluggy import ResultadoSync

HORA_PADRAO = time(6, 0)
#: O sono é em pedaços: o `docker compose stop` não espera um dia inteiro.
PEDACO_DE_SONO_S = 60.0


def log(mensagem: str) -> None:
    print(f"{datetime.now(FUSO):%d/%m/%Y %H:%M:%S} {mensagem}", flush=True)


def uma_execucao(cfg: Settings, executor: Callable[[Settings], ResultadoSync] = executar) -> int:
    """Roda uma sync e registra. Devolve o código: 0 ok, 1 erro, 3 ocupada."""
    log("sync: começando")
    try:
        r = executor(cfg)
    except SyncOcupada:
        log("sync: outra sincronização estava rodando; nada feito, a próxima é amanhã")
        return 3
    except SyncDesligada as exc:
        log(f"sync: desligada ({exc})")
        return 1
    except Exception as exc:
        log(f"sync: FALHOU, nada gravado: {type(exc).__name__}: {exc}")
        return 1
    erros = [f"{c.rotulo}: {c.erro}" for c in r.contas if c.erro]
    log(
        f"sync: ok, {r.itens_novos} novo(s), {r.promovidos} promovido(s), "
        f"{sum(r.na_revisao.values())} na revisão, importação "
        f"{'#' + str(r.importacao_id) if r.importacao_id else 'nenhuma'}"
        + (f"; erros: {'; '.join(erros)}" if erros else "")
    )
    return 1 if erros else 0


def dormir_ate(
    alvo: datetime,
    agora: Callable[[], datetime] = lambda: datetime.now(UTC),
    dormir: Callable[[float], None] = relogio.sleep,
) -> None:
    while (falta := (alvo - agora()).total_seconds()) > 0:
        dormir(min(falta, PEDACO_DE_SONO_S))


def laco(
    cfg: Settings,
    hora: time,
    *,
    executor: Callable[[Settings], ResultadoSync] = executar,
    agora: Callable[[], datetime] = lambda: datetime.now(UTC),
    dormir: Callable[[float], None] = relogio.sleep,
    vezes: int | None = None,
) -> None:
    """Dorme até a próxima `hora`, roda, repete. `vezes` limita (teste)."""
    feitas = 0
    while vezes is None or feitas < vezes:
        alvo = proxima_execucao(agora(), hora)
        log(f"agendador: próxima sync em {alvo:%d/%m/%Y %H:%M}")
        dormir_ate(alvo, agora, dormir)
        uma_execucao(cfg, executor)
        feitas += 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--uma-vez", action="store_true", help="roda agora, uma vez, e sai")
    args = parser.parse_args(argv)
    cfg = Settings()
    if args.uma_vez:
        return uma_execucao(cfg)
    hora = hora_da_agenda(cfg.sync_agenda) or HORA_PADRAO
    if not cfg.pluggy_habilitada:
        log("agendador: sem as credenciais da Pluggy; as execuções vão registrar 'desligada'")
    laco(cfg, hora)
    return 0


if __name__ == "__main__":
    sys.exit(main())
