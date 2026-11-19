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
        Settings(),
        SEIS,
        executor=executor,
        agora=relogio,
        dormir=relogio.dormir,
        ultima_sync=lambda: relogio.agora,  # em dia: sem recuperação
        vezes=2,
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


def _laco_com_recuperacao(
    ultima: datetime | None, efeito: Exception | None = None
) -> tuple[list[datetime], Relogio]:
    relogio = Relogio(datetime(2026, 11, 17, 15, 0, tzinfo=UTC))  # 12:00 local
    rodadas: list[datetime] = []

    def executor(cfg: Settings) -> ResultadoSync:
        rodadas.append(relogio.agora)
        if efeito:
            raise efeito
        return ResultadoSync(simulado=False)

    agendador.laco(
        Settings(),
        SEIS,
        executor=executor,
        agora=relogio,
        dormir=relogio.dormir,
        ultima_sync=lambda: ultima,
        vezes=1,
    )
    return rodadas, relogio


def test_recupera_no_boot_quando_a_ultima_tem_mais_de_20_h(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ultima = datetime(2026, 11, 8, 9, 0, tzinfo=UTC)
    rodadas, _ = _laco_com_recuperacao(ultima)
    saida = capsys.readouterr().out
    assert "última sync bem-sucedida há 222 h (08/11 06:00); rodando a de recuperação" in saida
    # A de recuperação (12:00 local) e depois a das 6h do dia seguinte.
    assert rodadas == [
        datetime(2026, 11, 17, 15, 0, tzinfo=UTC),
        datetime(2026, 11, 18, 9, 0, tzinfo=UTC),
    ]


def test_recupera_no_boot_quando_nunca_houve_sync(capsys: pytest.CaptureFixture[str]) -> None:
    rodadas, _ = _laco_com_recuperacao(None)
    assert "nenhuma sync registrada" in capsys.readouterr().out
    assert len(rodadas) == 2


def test_nao_recupera_quando_a_ultima_tem_menos_de_20_h() -> None:
    ultima = datetime(2026, 11, 16, 20, 0, tzinfo=UTC)  # 19 h antes
    rodadas, relogio = _laco_com_recuperacao(ultima)
    assert rodadas == [datetime(2026, 11, 18, 9, 0, tzinfo=UTC)]
    assert relogio.sonos  # dormiu até as 6h


def test_recuperacao_ocupada_vira_log_e_o_laco_segue(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rodadas, relogio = _laco_com_recuperacao(None, SyncOcupada("x"))
    assert "outra sincronização estava rodando" in capsys.readouterr().out
    assert len(rodadas) == 2  # tentou a de recuperação e a das 6h
    assert max(relogio.sonos) <= agendador.PEDACO_DE_SONO_S
    assert relogio.agora == datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
