"""O "hoje" do cardápio, em São Paulo, e o que depende dele.

`hoje()` é a única fonte da data: os testes a trocam
(`monkeypatch.setattr("compras.tempo.hoje", ...)`) para montar semanas
passadas e fixas. Quem usa chama `tempo.hoje()`, nunca importa a função por
nome, ou a troca não alcança.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    return datetime.now(FUSO).date()


def passou(inicio: date) -> bool:
    """A semana que começa em `inicio` já acabou: o domingo dela é antes de hoje (D-30)."""
    return inicio + timedelta(days=6) < hoje()


def fim_do_domingo(inicio: date) -> datetime:
    """O instante em que a semana acaba: domingo 23:59:59, São Paulo."""
    return datetime.combine(inicio + timedelta(days=6), time(23, 59, 59), tzinfo=FUSO)
