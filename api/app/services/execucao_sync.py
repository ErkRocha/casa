"""Como a sync da Pluggy roda: pelo CLI, pelo agendador e pelo botão do painel.

Os três caminhos passam por `executar`, que segura uma trava do Postgres
(`pg_try_advisory_lock`) enquanto roda. Duas execuções nunca se sobrepõem,
mesmo vindas de processos diferentes: a agendada das 6h e um "Atualizar
agora" no mesmo minuto. A segunda desiste com `SyncOcupada`, sem esperar.

A trava não precisa de superusuário (D-26) e some sozinha se o processo
morrer: ela é da conexão.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.conversao_pluggy import FUSO
from app.services.sync_pluggy import LeitorPluggy, ResultadoSync, SyncPluggyService

#: Chave da trava: "SYNC" em ASCII. Única no banco; ninguém mais usa
#: advisory lock neste projeto.
CHAVE_TRAVA = 0x53594E43


class SyncOcupada(Exception):
    """Outra sincronização está rodando agora."""


class SyncDesligada(Exception):
    """Sem as credenciais da Pluggy, não há o que sincronizar."""


@contextmanager
def trava_da_sync() -> Iterator[None]:
    """Segura a trava numa conexão própria até o fim do bloco."""
    from app.db import engine

    with engine.connect() as conexao:
        livre = conexao.execute(select(func.pg_try_advisory_lock(CHAVE_TRAVA))).scalar()
        if not livre:
            raise SyncOcupada("Outra sincronização está rodando agora.")
        try:
            yield
        finally:
            conexao.execute(select(func.pg_advisory_unlock(CHAVE_TRAVA)))
            conexao.commit()


class FabricaDeLeitor(Protocol):
    def __call__(
        self, cfg: Settings, ao_responder: Callable[[Any], None]
    ) -> Any:  # um context manager que entrega o LeitorPluggy
        ...


def _leitor_pluggy(cfg: Settings, ao_responder: Callable[[Any], None]) -> Any:
    from app.pluggy import PluggyCliente

    assert cfg.pluggy_client_id is not None and cfg.pluggy_client_secret is not None
    return PluggyCliente(cfg.pluggy_client_id, cfg.pluggy_client_secret, ao_responder=ao_responder)


def executar(
    cfg: Settings,
    *,
    simular: bool = False,
    ao_terminar: Callable[[ResultadoSync, Session], None] | None = None,
    fabrica_de_leitor: FabricaDeLeitor = _leitor_pluggy,
    hoje: date | None = None,
) -> ResultadoSync:
    """Uma sincronização inteira, com a trava. Grava numa transação só.

    `ao_terminar` recebe o resultado e a sessão ainda aberta, depois do
    commit (ou do rollback, na simulação): o CLI imprime por ele. Erro
    durante a gravação desfaz tudo e sobe a exceção.
    """
    if not cfg.pluggy_habilitada:
        raise SyncDesligada("PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET não estão definidos.")
    from app.db import SessionLocal

    respostas: list[Any] = []
    with (
        trava_da_sync(),
        fabrica_de_leitor(cfg, respostas.append) as leitor,
        SessionLocal() as session,
    ):
        servico = SyncPluggyService(
            session,
            leitor,
            hoje=hoje or datetime.now(FUSO).date(),
            respostas_brutas=lambda: respostas,
        )
        try:
            resultado = servico.sincronizar(simular=simular)
        except Exception:
            session.rollback()
            raise
        if simular:
            session.rollback()
        else:
            session.commit()
        if ao_terminar is not None:
            ao_terminar(resultado, session)
        return resultado


# --- próxima execução ---------------------------------------------------------


def hora_da_agenda(texto: str | None) -> time | None:
    """ "06:00" -> 06:00; vazio ou inválido -> sem agenda."""
    if not texto:
        return None
    try:
        horas, minutos = (int(p) for p in texto.strip().split(":"))
        return time(horas, minutos)
    except ValueError:
        return None


def proxima_execucao(agora: datetime, hora: time) -> datetime:
    """A próxima vez em que o relógio de São Paulo marca `hora`, depois de `agora`."""
    local = agora.astimezone(FUSO)
    candidata = datetime.combine(local.date(), hora, tzinfo=FUSO)
    if candidata <= local:
        candidata = datetime.combine(local.date() + timedelta(days=1), hora, tzinfo=FUSO)
    return candidata


# --- em segundo plano, para o botão do painel ----------------------------------

Situacao = Literal["nunca", "rodando", "ok", "erro", "ocupada"]


@dataclass(frozen=True, slots=True)
class Execucao:
    """A execução disparada pelo painel neste processo da API.

    Em memória: reiniciar a API volta a "nunca". O histórico de verdade é o
    das importações, no banco.
    """

    situacao: Situacao = "nunca"
    iniciada_em: datetime | None = None
    terminada_em: datetime | None = None
    itens_novos: int = 0
    promovidos: int = 0
    na_revisao: int = 0
    #: Compras pendentes do cartão só para exibição (D-28).
    pendentes: int = 0
    importacao_id: int | None = None
    erro: str | None = None


Executor = Callable[[Settings], ResultadoSync]


def _executor_padrao(cfg: Settings) -> ResultadoSync:
    return executar(cfg)


class EmSegundoPlano:
    """Dispara a sync numa thread e guarda o estado para o painel consultar.

    A requisição volta na hora; o painel pergunta o estado até terminar.
    Pedir de novo enquanto roda devolve a execução em curso, sem abrir outra.
    """

    def __init__(self, executor: Executor = _executor_padrao) -> None:
        self.executor = executor
        self._lock = threading.Lock()
        self._estado = Execucao()
        self._thread: threading.Thread | None = None

    def estado(self) -> Execucao:
        with self._lock:
            return self._estado

    def iniciar(self, cfg: Settings) -> Execucao:
        if not cfg.pluggy_habilitada:
            raise SyncDesligada("A sincronização está desligada: faltam as credenciais da Pluggy.")
        with self._lock:
            if self._estado.situacao == "rodando":
                return self._estado
            self._estado = Execucao(situacao="rodando", iniciada_em=datetime.now(FUSO))
            self._thread = threading.Thread(
                target=self._rodar, args=(cfg,), name="sync-pluggy", daemon=True
            )
            self._thread.start()
            return self._estado

    def aguardar(self, segundos: float | None = None) -> None:
        """Para teste e desligamento: espera a thread em curso."""
        thread = self._thread
        if thread is not None:
            thread.join(segundos)

    def _rodar(self, cfg: Settings) -> None:
        try:
            r = self.executor(cfg)
            final = replace(
                self._estado,
                situacao="ok",
                itens_novos=r.itens_novos,
                promovidos=r.promovidos,
                na_revisao=sum(r.na_revisao.values()),
                pendentes=r.pendentes_exibicao,
                importacao_id=r.importacao_id,
                erro="; ".join(f"{c.rotulo}: {c.erro}" for c in r.contas if c.erro) or None,
            )
        except SyncOcupada as exc:
            final = replace(self._estado, situacao="ocupada", erro=str(exc))
        except Exception as exc:
            final = replace(self._estado, situacao="erro", erro=f"{type(exc).__name__}: {exc}")
        with self._lock:
            self._estado = replace(final, terminada_em=datetime.now(FUSO))


#: A instância da API. Uma por processo, como a sync tem que ser.
em_segundo_plano = EmSegundoPlano()


__all__ = [
    "CHAVE_TRAVA",
    "EmSegundoPlano",
    "Execucao",
    "LeitorPluggy",
    "SyncDesligada",
    "SyncOcupada",
    "em_segundo_plano",
    "executar",
    "hora_da_agenda",
    "proxima_execucao",
    "trava_da_sync",
]
