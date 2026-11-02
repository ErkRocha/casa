"""Sync com trava, em segundo plano e pelo botão do painel (fase 5b, passo 10)."""

import threading
from collections.abc import Iterator
from contextlib import nullcontext
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.db import engine
from app.services import execucao_sync
from app.services.execucao_sync import (
    CHAVE_TRAVA,
    EmSegundoPlano,
    SyncDesligada,
    SyncOcupada,
    executar,
)
from app.services.sync_pluggy import ResultadoSync
from tests.test_sync_pluggy import LeitorFalso


def _cfg() -> Settings:
    return Settings(pluggy_client_id="id", pluggy_client_secret=SecretStr("segredo"))


def _leitor(cfg: Settings, ao_responder: Any) -> Any:
    return nullcontext(LeitorFalso())


@pytest.fixture
def segundo_plano(monkeypatch: pytest.MonkeyPatch) -> EmSegundoPlano:
    """Uma instância limpa por teste, no lugar da da API."""
    instancia = EmSegundoPlano()
    monkeypatch.setattr(execucao_sync, "em_segundo_plano", instancia)
    return instancia


@pytest.fixture
def sem_pluggy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    """No modo local as credenciais reais estão no ambiente: tira."""
    cfg = get_settings()
    monkeypatch.setattr(cfg, "pluggy_client_id", None)
    monkeypatch.setattr(cfg, "pluggy_client_secret", None)
    yield cfg


@pytest.fixture
def com_pluggy(monkeypatch: pytest.MonkeyPatch) -> Iterator[Settings]:
    cfg = get_settings()
    monkeypatch.setattr(cfg, "pluggy_client_id", "id")
    monkeypatch.setattr(cfg, "pluggy_client_secret", SecretStr("segredo"))
    yield cfg


# --- trava ---------------------------------------------------------------------


def test_executar_sem_mapeamento_nao_cria_nada_e_solta_a_trava() -> None:
    r = executar(_cfg(), fabrica_de_leitor=_leitor)
    assert (r.itens_novos, r.importacao_id) == (0, None)
    # A trava foi devolvida: outra conexão consegue pegá-la.
    with engine.connect() as c:
        assert c.execute(select(func.pg_try_advisory_lock(CHAVE_TRAVA))).scalar()
        c.execute(select(func.pg_advisory_unlock(CHAVE_TRAVA)))


def test_duas_syncs_ao_mesmo_tempo_a_segunda_desiste() -> None:
    with engine.connect() as outra:
        assert outra.execute(select(func.pg_try_advisory_lock(CHAVE_TRAVA))).scalar()
        try:
            with pytest.raises(SyncOcupada):
                executar(_cfg(), fabrica_de_leitor=_leitor)
        finally:
            outra.execute(select(func.pg_advisory_unlock(CHAVE_TRAVA)))
    executar(_cfg(), fabrica_de_leitor=_leitor)  # livre de novo


def test_sem_credenciais_nao_roda() -> None:
    with pytest.raises(SyncDesligada):
        executar(Settings(pluggy_client_id=None, pluggy_client_secret=None))


# --- em segundo plano ----------------------------------------------------------


class ExecutorPreso:
    """Fica rodando até o teste soltar."""

    def __init__(self, resultado: ResultadoSync | Exception) -> None:
        self.comecou = threading.Event()
        self.solta = threading.Event()
        self.resultado = resultado
        self.chamadas = 0

    def __call__(self, cfg: Settings) -> ResultadoSync:
        self.chamadas += 1
        self.comecou.set()
        self.solta.wait(10)
        if isinstance(self.resultado, Exception):
            raise self.resultado
        return self.resultado


def test_iniciar_volta_na_hora_e_nao_abre_outra_enquanto_roda() -> None:
    resultado = ResultadoSync(simulado=False, promovidos=4, importacao_id=9)
    executor = ExecutorPreso(resultado)
    fundo = EmSegundoPlano(executor)

    primeiro = fundo.iniciar(_cfg())
    assert primeiro.situacao == "rodando"
    assert executor.comecou.wait(5)
    segundo = fundo.iniciar(_cfg())
    assert segundo.iniciada_em == primeiro.iniciada_em
    assert executor.chamadas == 1

    executor.solta.set()
    fundo.aguardar(5)
    final = fundo.estado()
    assert final.situacao == "ok"
    assert (final.promovidos, final.importacao_id, final.erro) == (4, 9, None)
    assert final.terminada_em is not None


@pytest.mark.parametrize(
    ("erro", "situacao"),
    [(SyncOcupada("outra"), "ocupada"), (RuntimeError("Pluggy fora"), "erro")],
)
def test_falha_vira_estado_e_nao_excecao(erro: Exception, situacao: str) -> None:
    executor = ExecutorPreso(erro)
    executor.solta.set()
    fundo = EmSegundoPlano(executor)
    fundo.iniciar(_cfg())
    fundo.aguardar(5)
    assert fundo.estado().situacao == situacao
    assert fundo.estado().erro


def test_iniciar_sem_credenciais_e_recusado() -> None:
    with pytest.raises(SyncDesligada):
        EmSegundoPlano().iniciar(Settings(pluggy_client_id=None, pluggy_client_secret=None))


# --- API -----------------------------------------------------------------------


@pytest.mark.usefixtures("sem_pluggy")
def test_botao_sem_credenciais_e_409(client: TestClient, segundo_plano: EmSegundoPlano) -> None:
    resposta = client.post("/sincronizacao/atualizar")
    assert resposta.status_code == 409
    assert client.get("/sincronizacao/estado").json()["pode_atualizar"] is False


@pytest.mark.usefixtures("com_pluggy")
def test_botao_dispara_e_o_estado_acompanha(
    client: TestClient, segundo_plano: EmSegundoPlano
) -> None:
    executor = ExecutorPreso(ResultadoSync(simulado=False, promovidos=2))
    segundo_plano.executor = executor

    resposta = client.post("/sincronizacao/atualizar")
    assert resposta.status_code == 202
    assert resposta.json()["execucao"]["situacao"] == "rodando"
    assert resposta.json()["pode_atualizar"] is True
    assert executor.comecou.wait(5)

    executor.solta.set()
    segundo_plano.aguardar(5)
    estado = client.get("/sincronizacao/estado").json()
    assert estado["execucao"]["situacao"] == "ok"
    assert estado["execucao"]["promovidos"] == 2


def test_proxima_execucao_com_agenda(
    client: TestClient, segundo_plano: EmSegundoPlano, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "sync_agenda", "06:00")
    estado = client.get("/sincronizacao/estado").json()
    assert estado["automatica"] is True
    proxima = datetime.fromisoformat(estado["proxima_execucao"])
    assert proxima > datetime.now(UTC)
    assert (proxima.hour, proxima.minute) == (6, 0)
    assert estado["execucao"] is None
