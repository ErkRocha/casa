"""Agenda da sync: a próxima execução e o laço do agendador, sem banco."""

from datetime import UTC, datetime, time, timedelta

import pytest

from app.config import Settings
from app.services.execucao_sync import SyncOcupada, hora_da_agenda, proxima_execucao
from app.services.sync_pluggy import ResultadoSync
from scripts import agendador

SEIS = time(6, 0)


@pytest.mark.parametrize(
    ("agora_utc", "esperado_local"),
    [
        # 05:00 em São Paulo (08:00 UTC): hoje às 6h.
        (datetime(2026, 11, 2, 8, 0, tzinfo=UTC), datetime(2026, 11, 2, 6, 0)),
        # 06:00 em ponto: já passou, amanhã.
        (datetime(2026, 11, 2, 9, 0, tzinfo=UTC), datetime(2026, 11, 3, 6, 0)),
        # 23:30 em São Paulo (02:30 UTC do dia seguinte): amanhã local.
        (datetime(2026, 11, 3, 2, 30, tzinfo=UTC), datetime(2026, 11, 3, 6, 0)),
    ],
)
def test_proxima_execucao_no_horario_de_sao_paulo(
    agora_utc: datetime, esperado_local: datetime
) -> None:
    proxima = proxima_execucao(agora_utc, SEIS)
    assert proxima.replace(tzinfo=None) == esperado_local
    assert proxima.utcoffset() == timedelta(hours=-3)


@pytest.mark.parametrize(
    ("texto", "hora"),
    [("06:00", SEIS), (" 7:30 ", time(7, 30)), ("", None), (None, None), ("6h", None)],
)
def test_hora_da_agenda(texto: str | None, hora: time | None) -> None:
    assert hora_da_agenda(texto) == hora


class Relogio:
    def __init__(self, inicio: datetime) -> None:
        self.agora = inicio
        self.sonos: list[float] = []

    def __call__(self) -> datetime:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.sonos.append(segundos)
        self.agora += timedelta(seconds=segundos)


def test_laco_dorme_ate_a_hora_e_roda_uma_por_dia() -> None:
    relogio = Relogio(datetime(2026, 11, 2, 8, 0, tzinfo=UTC))  # 05:00 local
    rodadas: list[datetime] = []

    def executor(cfg: Settings) -> ResultadoSync:
        rodadas.append(relogio.agora)
        return ResultadoSync(simulado=False)

    agendador.laco(
        Settings(), SEIS, executor=executor, agora=relogio, dormir=relogio.dormir, vezes=2
    )
    assert rodadas == [
        datetime(2026, 11, 2, 9, 0, tzinfo=UTC),
        datetime(2026, 11, 3, 9, 0, tzinfo=UTC),
    ]
    # Sono em pedaços: o `docker compose stop` não espera um dia.
    assert max(relogio.sonos) <= agendador.PEDACO_DE_SONO_S


@pytest.mark.parametrize(
    ("efeito", "codigo", "trecho"),
    [
        (ResultadoSync(simulado=False, promovidos=3), 0, "ok, 0 novo(s), 3 promovido(s)"),
        (SyncOcupada("x"), 3, "outra sincronização estava rodando"),
        (RuntimeError("Pluggy fora"), 1, "FALHOU, nada gravado: RuntimeError"),
    ],
)
def test_uma_execucao_registra_e_nao_propaga(
    efeito: object, codigo: int, trecho: str, capsys: pytest.CaptureFixture[str]
) -> None:
    def executor(cfg: Settings) -> ResultadoSync:
        if isinstance(efeito, Exception):
            raise efeito
        assert isinstance(efeito, ResultadoSync)
        return efeito

    assert agendador.uma_execucao(Settings(), executor) == codigo
    assert trecho in capsys.readouterr().out
