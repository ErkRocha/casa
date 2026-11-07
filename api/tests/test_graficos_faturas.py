"""Gráfico de linhas "Faturas" do Início (D-29): um ciclo de fatura por linha.

"Hoje" é 16/10/2026: a janela começa em 17/09. Cada teste monta só o que
precisa, com as datas vindas de um comprovante da Pluggy ou do cadastro.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_PAGAMENTO_NA_CONTA, OBS_PAGAMENTO_NO_CARTAO
from app.enums import TipoPagamento
from app.services.graficos_inicio import GraficosInicioService
from tests.test_caixa import (
    NOVEMBRO,
    OUTUBRO,
    SETEMBRO,
    _bills,
    _comprovante,
    _conta,
    _forma,
    _gasto,
    _item_staging,
    _liga_pluggy,
    _pagamento,
    _pendente,
)

HOJE = date(2026, 10, 16)
INICIO = date(2026, 9, 17)


def _ciclos(session: Session, hoje: date = HOJE) -> Any:
    session.commit()
    return GraficosInicioService(session, hoje=hoje).faturas_ciclos()


def _por_fechamento(resposta: Any, cartao: str) -> dict[date, Any]:
    return {c.fechamento: c for c in resposta.ciclos if c.cartao == cartao}


def test_ciclo_sobe_fica_reto_e_cai_a_zero_no_pagamento(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=9)
    pix = _forma(session, "Pix Banco", TipoPagamento.PIX, banco)
    _liga_pluggy(session, a, banco, "acc-a")
    _comprovante(
        session,
        [
            _bills(
                "acc-a",
                ("set", "2026-09-09", "2026-09-02"),
                ("out", "2026-10-09", "2026-10-02"),
            )
        ],
    )
    _gasto(session, a, date(2026, 9, 10), "100.00", OUTUBRO)
    _gasto(session, a, date(2026, 9, 25), "50.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 5), "30.00", NOVEMBRO)
    _gasto(session, a, date(2026, 10, 15), "20.00", NOVEMBRO)
    _pagamento(session, pix, date(2026, 10, 8), "150.00", OBS_PAGAMENTO_NA_CONTA)

    r = _ciclos(session)
    assert (r.inicio, r.hoje, r.fim) == (INICIO, HOJE, HOJE)
    ciclos = _por_fechamento(r, "Cartão A")
    # Os ciclos de julho/agosto/setembro não têm compra: ficam de fora.
    assert sorted(ciclos) == [date(2026, 10, 2), date(2026, 11, 2)]

    pago = ciclos[date(2026, 10, 2)]
    assert pago.chave == f"ciclo:{a.id}:2026-10-02"
    assert pago.abertura == date(2026, 9, 3)
    assert pago.origem_abertura == "pluggy_fatura"
    assert (pago.origem_fechamento, pago.origem_vencimento) == ("pluggy_fatura", "pluggy_fatura")
    assert (pago.vencimento, pago.mes_fatura) == (date(2026, 10, 9), date(2026, 10, 1))
    assert (pago.situacao, pago.atual) == ("paga", False)
    assert (pago.pago_em, pago.origem_pagamento) == (date(2026, 10, 8), "identificado")
    assert (pago.valor, pago.pendente) == (Decimal("150.00"), Decimal("0"))

    pontos = [(p.data, p.valor, p.tracejado) for p in pago.pontos]
    assert pontos[0] == (INICIO, Decimal("100.00"), False)  # a compra de 10/09 já conta
    valores = {p.data: p.valor for p in pago.pontos}
    assert valores[date(2026, 9, 24)] == Decimal("100.00")
    assert valores[date(2026, 9, 25)] == Decimal("150.00")
    assert valores[date(2026, 10, 2)] == Decimal("150.00")  # reta depois do fechamento
    assert valores[date(2026, 10, 7)] == Decimal("150.00")
    # No dia do pagamento, dois pontos: o valor antes e zero depois; e a linha acaba ali.
    assert pontos[-2:] == [
        (date(2026, 10, 8), Decimal("150.00"), False),
        (date(2026, 10, 8), Decimal("0"), False),
    ]
    assert len(pontos) == (date(2026, 10, 8) - INICIO).days + 2

    aberto = ciclos[date(2026, 11, 2)]
    assert aberto.abertura == date(2026, 10, 3)
    assert (aberto.situacao, aberto.atual) == ("aberta", True)
    assert (aberto.valor, aberto.pago_em, aberto.origem_pagamento) == (
        Decimal("50.00"),
        None,
        None,
    )
    assert (aberto.origem_fechamento, aberto.origem_vencimento) == ("cadastro", "cadastro")
    assert (aberto.vencimento, aberto.mes_fatura) == (date(2026, 11, 9), date(2026, 11, 1))
    valores = {p.data: p.valor for p in aberto.pontos}
    assert aberto.pontos[0].data == date(2026, 10, 3)
    assert aberto.pontos[-1].data == HOJE  # vence depois da janela: acaba em hoje
    assert valores[date(2026, 10, 4)] == Decimal("0")
    assert valores[date(2026, 10, 5)] == Decimal("30.00")
    assert valores[HOJE] == Decimal("50.00")
    assert not any(p.tracejado for p in aberto.pontos)


def test_dois_cartoes_com_fechamentos_e_vencimentos_diferentes(session: Session) -> None:
    banco = _conta(session, "Banco")
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    _gasto(session, a, date(2026, 10, 5), "10.00", NOVEMBRO)
    _gasto(session, b, date(2026, 10, 8), "40.00", NOVEMBRO)
    _gasto(session, a, date(2026, 9, 20), "7.00", OUTUBRO)

    r = _ciclos(session)
    # Por cartão (apelido) e fechamento.
    assert [(c.cartao, c.fechamento) for c in r.ciclos] == [
        ("Cartão A", date(2026, 10, 2)),
        ("Cartão A", date(2026, 11, 2)),
        ("Cartão B", date(2026, 11, 3)),
    ]
    a_out, a_nov, b_nov = r.ciclos
    assert (a_out.abertura, a_out.vencimento, a_out.valor) == (
        date(2026, 9, 3),
        date(2026, 10, 7),
        Decimal("7.00"),
    )
    assert (a_nov.abertura, a_nov.vencimento, a_nov.valor) == (
        date(2026, 10, 3),
        date(2026, 11, 7),
        Decimal("10.00"),
    )
    assert (b_nov.abertura, b_nov.vencimento, b_nov.valor) == (
        date(2026, 10, 4),
        date(2026, 11, 10),
        Decimal("40.00"),
    )
    assert (a_out.atual, a_nov.atual, b_nov.atual) == (False, True, True)
    # Fechada e não paga, mas vencida: reta até hoje e termina ali.
    assert a_out.situacao == "fechada"
    assert a_out.pontos[-1].data == HOJE
    assert not any(p.tracejado for p in a_out.pontos)


def test_fatura_fechada_sem_pagamento_segue_reta_e_tracejada_ate_o_vencimento(
    session: Session,
) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=10, vence=22)
    _gasto(session, a, date(2026, 9, 20), "100.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 12), "30.00", NOVEMBRO)

    r = _ciclos(session)
    assert r.fim == date(2026, 10, 22)  # vencimento do ciclo fechado, dentro de hoje+15
    ciclos = _por_fechamento(r, "Cartão A")
    fechada, aberta = ciclos[date(2026, 10, 10)], ciclos[date(2026, 11, 10)]
    assert (fechada.situacao, aberta.situacao) == ("fechada", "aberta")
    assert fechada.vencimento == date(2026, 10, 22)

    assert fechada.pontos[0].data == INICIO
    assert fechada.pontos[-1].data == r.fim
    for p in fechada.pontos:
        assert p.tracejado == (p.data > HOJE)
        assert p.valor == Decimal("100.00") or p.data < date(2026, 9, 20)
    assert sum(p.tracejado for p in fechada.pontos) == 6  # 17/10 a 22/10

    # Ciclos sobrepostos: o novo começa no dia seguinte ao fechamento, com o
    # anterior ainda esperando o pagamento.
    assert aberta.abertura == date(2026, 10, 11)
    assert aberta.pontos[0].data == date(2026, 10, 11)
    assert aberta.pontos[-1].data == r.fim  # também vai até o fim da janela
    assert {p.data: p.valor for p in aberta.pontos}[date(2026, 10, 12)] == Decimal("30.00")
    assert fechada.pontos[-1].data >= aberta.pontos[0].data
    assert fechada.atual is False and aberta.atual is True


def test_fatura_antiga_sem_pagamento_identificado_fica_fora(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=10, vence=22)
    # Fecha 10/08, vence 22/08: o prazo (vencimento + folga) acabou antes de
    # 17/09, então foi paga fora do que a sync enxerga e não entra.
    _gasto(session, a, date(2026, 8, 5), "500.00", date(2026, 8, 1))
    # Fecha 10/09, vence 22/09: o prazo ainda alcança a janela e entra.
    _gasto(session, a, date(2026, 9, 1), "80.00", date(2026, 9, 1))

    ciclos = _por_fechamento(_ciclos(session), "Cartão A")
    assert date(2026, 8, 10) not in ciclos
    assert ciclos[date(2026, 9, 10)].valor == Decimal("80.00")


def test_datas_da_pluggy_valem_mais_que_o_cadastro(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=5, vence=12)
    _liga_pluggy(session, a, banco, "acc-a")
    # A Pluggy fechou em 02/10 e vence em 09/10; o cadastro diria 05/10 e 12/10.
    _comprovante(session, [_bills("acc-a", ("out", "2026-10-09", "2026-10-02"))])
    _gasto(session, a, date(2026, 9, 25), "60.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 10), "5.00", NOVEMBRO)

    ciclos = _por_fechamento(_ciclos(session), "Cartão A")
    assert date(2026, 10, 5) not in ciclos
    real = ciclos[date(2026, 10, 2)]
    assert (real.origem_fechamento, real.origem_vencimento) == ("pluggy_fatura", "pluggy_fatura")
    assert real.vencimento == date(2026, 10, 9)
    assert real.valor == Decimal("60.00")
    # O ciclo seguinte (cadastro: 05/11) abre no dia seguinte ao fechamento real.
    aberto = ciclos[date(2026, 11, 5)]
    assert aberto.abertura == date(2026, 10, 3)
    assert aberto.origem_abertura == "pluggy_fatura"
    assert aberto.origem_fechamento == "cadastro"
    assert aberto.valor == Decimal("5.00")


def test_sem_a_fatura_na_pluggy_vale_o_cadastro_com_a_origem(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=9)
    _liga_pluggy(session, a, banco, "acc-a")
    # A Pluggy só listou até setembro: a de outubro (fechou em 02/10) ainda não saiu.
    _comprovante(session, [_bills("acc-a", ("set", "2026-09-09", "2026-09-02"))])
    _gasto(session, a, date(2026, 9, 20), "10.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 10), "25.00", NOVEMBRO)

    ciclos = _por_fechamento(_ciclos(session), "Cartão A")
    # Setembro é o da Pluggy; 02/09 do cadastro não duplica.
    assert ciclos[date(2026, 10, 2)].origem_fechamento == "cadastro"
    assert ciclos[date(2026, 10, 2)].origem_vencimento == "cadastro"
    assert ciclos[date(2026, 10, 2)].vencimento == date(2026, 10, 9)
    assert ciclos[date(2026, 10, 2)].abertura == date(2026, 9, 3)
    assert ciclos[date(2026, 10, 2)].valor == Decimal("10.00")
    assert ciclos[date(2026, 11, 2)].valor == Decimal("25.00")
    assert len([c for c in ciclos if date(2026, 8, 27) <= c <= date(2026, 9, 8)]) <= 1


def test_pendente_que_virou_lancada_nao_duplica_no_ciclo(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=9)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 10, 14), "20.00", OUTUBRO)  # a p1 já lançada
    item = _item_staging(session, "p1", date(2026, 10, 14), "20.00")
    _pendente(session, ligacao, "p1", date(2026, 10, 14), "20.00", NOVEMBRO)
    _pendente(session, ligacao, "p2", date(2026, 10, 15), "5.00", NOVEMBRO)

    aberto = _por_fechamento(_ciclos(session), "Cartão A")[date(2026, 11, 2)]
    assert (aberto.valor, aberto.pendente) == (Decimal("25.00"), Decimal("5.00"))
    assert {p.data: p.valor for p in aberto.pontos}[HOJE] == Decimal("25.00")

    item.deleted_em = datetime.now(UTC)
    aberto = _por_fechamento(_ciclos(session), "Cartão A")[date(2026, 11, 2)]
    assert (aberto.valor, aberto.pendente) == (Decimal("45.00"), Decimal("25.00"))


def test_pagamento_pela_janela_do_ciclo_e_lado_da_conta_primeiro(
    session: Session,
) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    pix = _forma(session, "Pix Banco", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 8, 20), "80.00", SETEMBRO)
    _gasto(session, a, date(2026, 9, 20), "90.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 5), "10.00", NOVEMBRO)
    # 07/10 está na janela do ciclo de 02/10 (03/10 a 17/10); o lado do cartão
    # (08/10) perde para o da conta (06/10).
    _pagamento(session, pix, date(2026, 10, 6), "90.00", OBS_PAGAMENTO_NA_CONTA)
    _pagamento(session, a, date(2026, 10, 8), "90.00", OBS_PAGAMENTO_NO_CARTAO)

    ciclos = _por_fechamento(_ciclos(session), "Cartão A")
    assert ciclos[date(2026, 10, 2)].pago_em == date(2026, 10, 6)
    assert ciclos[date(2026, 9, 2)].pago_em is None  # fora da janela do pagamento
    assert ciclos[date(2026, 11, 2)].pago_em is None


def test_cartao_sem_nenhuma_fonte_de_datas_fica_fora(session: Session) -> None:
    banco = _conta(session, "Banco")
    sem = _forma(session, "Sem datas", TipoPagamento.CREDITO, banco)
    com = _forma(session, "Com datas", TipoPagamento.CREDITO, banco, fecha=2, vence=9)
    _gasto(session, sem, date(2026, 10, 5), "10.00", NOVEMBRO)
    _gasto(session, com, date(2026, 10, 5), "10.00", NOVEMBRO)

    r = _ciclos(session)
    assert {c.cartao for c in r.ciclos} == {"Com datas"}


def test_sem_cartao_volta_vazio_e_fim_e_hoje(session: Session) -> None:
    r = _ciclos(session)
    assert r.ciclos == []
    assert (r.inicio, r.hoje, r.fim) == (INICIO, HOJE, HOJE)


def test_cor_do_ciclo_e_a_mesma_do_grafico_de_gastos(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=9)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    _liga_pluggy(session, b, banco, "acc-b")  # com Pluggy, ganha a primeira cor
    _gasto(session, a, date(2026, 10, 5), "10.00", NOVEMBRO)
    _gasto(session, b, date(2026, 10, 6), "20.00", NOVEMBRO)
    session.commit()

    servico = GraficosInicioService(session, hoje=HOJE)
    cores_ciclos = {c.cartao: c.cor for c in servico.faturas_ciclos().ciclos}
    cores_gastos = {s.rotulo: s.cor for s in servico.gastos_30_dias().series}
    assert cores_ciclos == cores_gastos
    assert cores_ciclos["Cartão B"] == "serie-1"
    assert cores_ciclos["Cartão A"] == "serie-2"


def test_rota_devolve_a_janela(client: TestClient) -> None:
    resposta = client.get("/analytics/inicio/faturas-ciclos")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert set(corpo) == {"inicio", "hoje", "fim", "ciclos"}
