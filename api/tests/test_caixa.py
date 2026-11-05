"""Visão de caixa (D-27): degraus de fatura, pagamento, faturas abertas.

"Hoje" é 16/10/2026. Cada teste monta só o que precisa; as datas dos cartões
vêm do cadastro (`dia_fechamento`/`dia_vencimento`) ou de um comprovante da
Pluggy montado aqui, como a sync o grava.
"""

from __future__ import annotations

import itertools
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_PAGAMENTO_NA_CONTA, OBS_PAGAMENTO_NO_CARTAO
from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    PluggyPendente,
    Transacao,
)
from app.services.inicio import InicioService

HOJE = date(2026, 10, 16)
OUTUBRO = date(2026, 10, 1)
SETEMBRO = date(2026, 9, 1)
NOVEMBRO = date(2026, 11, 1)

_seq = itertools.count(1)


def _conta(session: Session, nome: str) -> Conta:
    conta = Conta(nome=nome, tipo=TipoConta.CORRENTE)
    session.add(conta)
    session.flush()
    return conta


def _forma(
    session: Session,
    apelido: str,
    tipo: TipoPagamento,
    conta: Conta | None = None,
    *,
    fecha: int | None = None,
    vence: int | None = None,
    ativo: bool = True,
) -> FormaPagamento:
    forma = FormaPagamento(
        apelido=apelido,
        tipo=tipo,
        conta_id=conta.id if conta else None,
        dia_fechamento=fecha,
        dia_vencimento=vence,
        ativo=ativo,
    )
    session.add(forma)
    session.flush()
    return forma


def _gasto(
    session: Session, forma: FormaPagamento, data: date, valor: str, competencia: date
) -> None:
    n = next(_seq)
    session.add(
        Transacao(
            data=data,
            competencia=competencia,
            valor=Decimal(valor),
            tipo=TipoTransacao.DESPESA,
            descricao=f"compra {n}",
            descricao_original=f"COMPRA {n}",
            forma_pagamento_id=forma.id,
        )
    )


def _comprovante(session: Session, respostas: list[dict[str, Any]]) -> None:
    n = next(_seq)
    corpo = {"gerado_em": "2026-10-16T10:00:00Z", "contas": [], "respostas": respostas}
    session.add(
        Importacao(
            arquivo_nome=f"pluggy-{n}.json",
            hash_arquivo=f"hash-{n}",
            arquivo_conteudo=json.dumps(corpo).encode(),
            arquivo_tipo="application/json",
            origem="pluggy",
            status=StatusImportacao.CONCLUIDA,
        )
    )
    session.flush()


def _bills(conta_pluggy: str, *faturas: tuple[str, str, str]) -> dict[str, Any]:
    """Resposta `/bills`: cada fatura é (id, dueDate, billClosingDate), em AAAA-MM-DD."""
    return {
        "metodo": "GET",
        "caminho": "/bills",
        "params": {"accountId": conta_pluggy},
        "status": 200,
        "corpo": {
            "results": [
                {
                    "id": id_,
                    "dueDate": f"{vence}T00:00:00.000Z",
                    "billClosingDate": f"{fecha}T00:00:00.000Z",
                    "totalAmount": 9999.99,
                    "payments": [],
                }
                for id_, vence, fecha in faturas
            ]
        },
    }


def _conta_credito(conta_pluggy: str, fecha: str | None, vence: str | None) -> dict[str, Any]:
    credito: dict[str, str] = {}
    if fecha:
        credito["balanceCloseDate"] = f"{fecha}T00:00:00.000Z"
    if vence:
        credito["balanceDueDate"] = f"{vence}T00:00:00.000Z"
    return {
        "metodo": "GET",
        "caminho": "/accounts",
        "params": {},
        "status": 200,
        "corpo": {"results": [{"id": conta_pluggy, "type": "CREDIT", "creditData": credito}]},
    }


def _liga_pluggy(
    session: Session, forma: FormaPagamento, conta: Conta, account_id: str
) -> ContaPluggy:
    ligacao = ContaPluggy(
        pluggy_item_id="item-1",
        pluggy_account_id=account_id,
        conta_id=conta.id,
        forma_pagamento_id=forma.id,
        sincronizar_desde=date(2026, 1, 1),
    )
    session.add(ligacao)
    session.flush()
    return ligacao


def _pagamento(
    session: Session, forma_sugerida: FormaPagamento, data: date, valor: str, obs: str
) -> None:
    importacao = Importacao(
        arquivo_nome=f"sync-{next(_seq)}",
        hash_arquivo=f"hash-sync-{next(_seq)}",
        status=StatusImportacao.CONCLUIDA,
    )
    session.add(importacao)
    session.flush()
    session.add(
        ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta="pagamento de fatura",
            data=data,
            valor=Decimal(valor),
            forma_pagamento_sugerida_id=forma_sugerida.id,
            status=StatusItem.REJEITADO,
            observacao=obs,
        )
    )
    session.flush()


def _resumo(session: Session, competencia: date = OUTUBRO) -> Any:
    return InicioService(session, hoje=HOJE).resumo(competencia)


def test_dois_cartoes_com_datas_diferentes(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 9, 25), "100.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 12), "50.00", OUTUBRO)
    _gasto(session, b, date(2026, 9, 28), "200.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 15), "30.00", OUTUBRO)
    session.commit()

    r = _resumo(session)
    assert [(f.cartao, f.dia, f.valor, f.situacao, f.origem_vencimento) for f in r.faturas] == [
        ("Cartão A", 7, Decimal("150.00"), "a_pagar", "cadastro"),
        ("Cartão B", 10, Decimal("200.00"), "a_pagar", "cadastro"),
    ]
    assert r.faturas[0].vencimento == date(2026, 10, 7)
    assert r.faturas[0].pago_em is None
    acumulado = {p.dia: p.acumulado for p in r.serie}
    com_a_pagar = {p.dia: p.com_a_pagar for p in r.serie}
    assert com_a_pagar[6] == Decimal("0")
    assert com_a_pagar[7] == Decimal("150.00")
    assert com_a_pagar[10] == Decimal("350.00")
    assert acumulado[10] == Decimal("0")  # a fatura ainda não saiu da conta
    assert acumulado[15] == Decimal("30.00")
    assert com_a_pagar[15] == Decimal("380.00")
    assert com_a_pagar[31] == Decimal("380.00")


def test_vencimento_real_da_pluggy_vale_mais_que_o_cadastro(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    c = _forma(session, "Cartão C", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    _liga_pluggy(session, a, banco, "acc-a")
    _liga_pluggy(session, b, banco, "acc-b")
    _liga_pluggy(session, c, banco, "acc-c")
    for forma in (a, b, c):
        _gasto(session, forma, date(2026, 10, 4), "80.00", OUTUBRO)
    # Comprovante antigo diz 09/10; o mais recente corrige para 11/10.
    _comprovante(session, [_bills("acc-a", ("bill-a", "2026-10-09", "2026-10-01"))])
    _comprovante(
        session,
        [
            _bills("acc-a", ("bill-a", "2026-10-11", "2026-10-02")),
            # B: fatura de setembro e a conta de crédito já com as datas de outubro.
            _bills("acc-b", ("bill-b-set", "2026-09-12", "2026-09-04")),
            _conta_credito("acc-b", "2026-10-05", "2026-10-14"),
            # C: o vencimento da conta de crédito (03/10) é anterior ao último
            # fechamento conhecido (04/10): não vale, e o cadastro (dia 10) assume.
            _bills("acc-c", ("bill-c-nov", "2026-11-10", "2026-10-04")),
            _conta_credito("acc-c", "2026-10-04", "2026-10-03"),
        ],
    )
    session.commit()

    por_cartao = {f.cartao: f for f in _resumo(session).faturas}
    assert por_cartao["Cartão A"].vencimento == date(2026, 10, 11)
    assert por_cartao["Cartão A"].dia == 11
    assert por_cartao["Cartão A"].origem_vencimento == "pluggy_fatura"
    # O valor é a soma das compras, não o totalAmount (9999,99) da Pluggy.
    assert por_cartao["Cartão A"].valor == Decimal("80.00")
    assert por_cartao["Cartão B"].vencimento == date(2026, 10, 14)
    assert por_cartao["Cartão B"].origem_vencimento == "pluggy_conta"
    assert por_cartao["Cartão C"].vencimento == date(2026, 10, 10)
    assert por_cartao["Cartão C"].origem_vencimento == "cadastro"


def test_pagamento_identificado_define_o_dia_da_saida(session: Session) -> None:
    banco, banco2 = _conta(session, "Banco"), _conta(session, "Banco 2")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco2, fecha=3, vence=10)
    c = _forma(session, "Cartão C", TipoPagamento.CREDITO, banco2, fecha=3, vence=12)
    pix = _forma(session, "Pix Banco", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 9, 25), "150.00", OUTUBRO)
    _gasto(session, b, date(2026, 9, 28), "200.00", OUTUBRO)
    _gasto(session, c, date(2026, 9, 28), "90.00", OUTUBRO)
    # A: lado da conta (06/10) ganha do lado do cartão (07/10), mesmo com valor exato.
    _pagamento(session, pix, date(2026, 10, 6), "148.00", OBS_PAGAMENTO_NA_CONTA)
    _pagamento(session, a, date(2026, 10, 7), "150.00", OBS_PAGAMENTO_NO_CARTAO)
    # B: sem lado da conta (nada saiu do Banco 2), vale o lado do cartão.
    _pagamento(session, b, date(2026, 10, 8), "200.00", OBS_PAGAMENTO_NO_CARTAO)
    # C: pagamento fora da janela (antes do fechamento) não conta.
    _pagamento(session, c, date(2026, 10, 2), "90.00", OBS_PAGAMENTO_NO_CARTAO)
    session.commit()

    r = _resumo(session)
    por_cartao = {f.cartao: f for f in r.faturas}
    assert (por_cartao["Cartão A"].situacao, por_cartao["Cartão A"].dia) == ("paga", 6)
    assert por_cartao["Cartão A"].pago_em == date(2026, 10, 6)
    assert (por_cartao["Cartão B"].situacao, por_cartao["Cartão B"].dia) == ("paga", 8)
    assert (por_cartao["Cartão C"].situacao, por_cartao["Cartão C"].dia) == ("a_pagar", 12)
    acumulado = {p.dia: p.acumulado for p in r.serie}
    assert acumulado[5] == Decimal("0")
    assert acumulado[6] == Decimal("150.00")
    assert acumulado[8] == Decimal("350.00")
    assert {p.dia: p.com_a_pagar for p in r.serie}[12] == Decimal("440.00")


def test_fatura_aberta_soma_pela_data_da_compra(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    sem_datas = _forma(session, "Sem datas", TipoPagamento.CREDITO, banco)
    inativo = _forma(
        session, "Inativo", TipoPagamento.CREDITO, banco, fecha=2, vence=7, ativo=False
    )
    parado = _forma(session, "Parado", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    _liga_pluggy(session, b, banco, "acc-b")
    _gasto(session, a, date(2026, 9, 30), "100.00", OUTUBRO)  # antes de `desde`: fora
    _gasto(session, a, date(2026, 10, 5), "40.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 5), "10.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 10), "25.00", OUTUBRO)
    _gasto(session, b, date(2026, 10, 8), "60.00", OUTUBRO)
    _gasto(session, sem_datas, date(2026, 10, 8), "70.00", OUTUBRO)
    _gasto(session, inativo, date(2026, 10, 8), "70.00", OUTUBRO)
    _gasto(session, parado, date(2026, 6, 8), "70.00", date(2026, 6, 1))  # há mais de 90 dias
    _comprovante(
        session,
        [
            _bills("acc-b", ("bill-b", "2026-10-10", "2026-10-03")),
            _conta_credito("acc-b", "2026-11-03", "2026-11-10"),
        ],
    )
    session.commit()

    abertas = {f.cartao: f for f in _resumo(session).faturas_abertas}
    assert set(abertas) == {"Cartão A", "Cartão B"}

    a_aberta = abertas["Cartão A"]
    assert (a_aberta.desde, a_aberta.fecha, a_aberta.vence) == (
        date(2026, 10, 2),
        date(2026, 11, 2),
        date(2026, 11, 7),
    )
    assert a_aberta.origem_datas == "cadastro"
    assert a_aberta.valor == Decimal("75.00")
    evolucao = {p.data: p.acumulado for p in a_aberta.evolucao}
    assert min(evolucao) == date(2026, 10, 3) and max(evolucao) == HOJE
    assert len(evolucao) == 14
    assert evolucao[date(2026, 10, 4)] == Decimal("0")
    assert evolucao[date(2026, 10, 5)] == Decimal("50.00")
    assert evolucao[date(2026, 10, 9)] == Decimal("50.00")
    assert evolucao[date(2026, 10, 10)] == Decimal("75.00")
    assert evolucao[HOJE] == Decimal("75.00")

    b_aberta = abertas["Cartão B"]
    assert (b_aberta.desde, b_aberta.fecha, b_aberta.vence) == (
        date(2026, 10, 3),
        date(2026, 11, 3),
        date(2026, 11, 10),
    )
    assert b_aberta.origem_datas == "pluggy_conta"
    assert b_aberta.valor == Decimal("60.00")

    # O bloco não depende do mês pedido.
    assert len(_resumo(session, SETEMBRO).faturas_abertas) == 2


def test_total_do_mes_fecha_com_o_da_competencia(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    sem_datas = _forma(session, "Sem datas", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 8, 28), "300.00", SETEMBRO)
    _gasto(session, a, date(2026, 9, 3), "45.50", SETEMBRO)
    _gasto(session, sem_datas, date(2026, 9, 20), "70.25", SETEMBRO)
    _gasto(session, pix, date(2026, 9, 12), "10.10", SETEMBRO)
    _gasto(session, pix, date(2026, 9, 30), "5.00", SETEMBRO)
    session.commit()

    r = _resumo(session, SETEMBRO)
    assert r.situacao == "passado"
    assert len(r.serie) == 30
    total = Decimal("430.85")
    assert r.gasto == total
    assert r.serie[-1].com_a_pagar == total
    # A fatura do Cartão A (345,50) segue a pagar: não saiu da conta.
    assert r.serie[-1].acumulado == total - Decimal("345.50")
    com_a_pagar = {p.dia: p.com_a_pagar for p in r.serie}
    acumulado = {p.dia: p.acumulado for p in r.serie}
    # Cartão sem datas mantém a compra no dia dela (20/09).
    assert com_a_pagar[19] == Decimal("355.60")  # fatura (dia 7) + Pix do dia 12
    assert com_a_pagar[20] == Decimal("425.85")
    assert acumulado[19] == Decimal("10.10")
    assert acumulado[20] == Decimal("80.35")
    assert [f.cartao for f in r.faturas] == ["Cartão A"]


def test_previsao_com_fatura_a_pagar(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=5, vence=28)
    sem_datas = _forma(session, "Sem datas", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 9, 25), "200.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 10), "100.00", OUTUBRO)
    _gasto(session, sem_datas, date(2026, 9, 25), "100.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 5), "50.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 10), "30.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 20), "40.00", OUTUBRO)
    session.commit()

    r = _resumo(session)
    assert [(f.dia, f.valor, f.situacao) for f in r.faturas] == [(28, Decimal("300.00"), "a_pagar")]
    assert r.previsao is not None
    # Fatura 300 + "antes" do cartão sem datas 100 + ritmo (50 + 30) / 16 * 31.
    assert r.previsao.comprometido == Decimal("400.00")
    assert r.previsao.valor == Decimal("555.00")
    assert r.previsao.diferenca_orcamento is None
    # O fim da curva é o total da competência: 300 + 100 + 120.
    assert r.serie[-1].com_a_pagar == Decimal("520.00")
    assert r.serie[-1].acumulado == Decimal("180.00")  # só o que saiu até hoje


def test_fatura_aberta_nunca_fecha_antes_de_hoje(session: Session) -> None:
    banco = _conta(session, "Banco")
    # Pluggy ainda não listou a fatura nova (último fechamento 02/09, dentro dos
    # 45 dias); o cadastro (dia 10) é mais recente e vale.
    velha = _forma(session, "Cadastro mais novo", TipoPagamento.CREDITO, banco, fecha=10, vence=15)
    # Só a Pluggy, com o último fechamento em 05/09: a cadência mensal avança até
    # passar de hoje (desde 05/10, fecha 05/11).
    so_pluggy = _forma(session, "So Pluggy", TipoPagamento.CREDITO, banco)
    # Só a Pluggy, último fechamento 20/09: já fecha depois de hoje.
    recente = _forma(session, "Pluggy recente", TipoPagamento.CREDITO, banco)
    _liga_pluggy(session, velha, banco, "acc-1")
    _liga_pluggy(session, so_pluggy, banco, "acc-2")
    _liga_pluggy(session, recente, banco, "acc-3")
    for forma in (velha, so_pluggy, recente):
        _gasto(session, forma, date(2026, 10, 14), "10.00", OUTUBRO)
    _comprovante(
        session,
        [
            _bills("acc-1", ("b1", "2026-09-09", "2026-09-02")),
            _bills("acc-2", ("b2", "2026-09-12", "2026-09-05")),
            _bills("acc-3", ("b3", "2026-09-27", "2026-09-20")),
        ],
    )
    session.commit()

    abertas = {f.cartao: f for f in _resumo(session).faturas_abertas}
    assert all(f.fecha > HOJE for f in abertas.values())

    a = abertas["Cadastro mais novo"]
    assert (a.desde, a.fecha, a.vence, a.origem_datas) == (
        date(2026, 10, 10),
        date(2026, 11, 10),
        date(2026, 11, 15),
        "cadastro",
    )
    b = abertas["So Pluggy"]
    assert (b.desde, b.fecha, b.vence, b.origem_datas) == (
        date(2026, 10, 5),
        date(2026, 11, 5),
        date(2026, 11, 12),
        "pluggy_fatura",
    )
    c = abertas["Pluggy recente"]
    assert (c.desde, c.fecha, c.vence) == (
        date(2026, 9, 20),
        date(2026, 10, 20),
        date(2026, 10, 27),
    )


def _pendente(
    session: Session,
    ligacao: ContaPluggy,
    id_externo: str,
    data: date,
    valor: str,
    fatura_prevista: date | None = None,
) -> None:
    session.add(
        PluggyPendente(
            id_externo=id_externo,
            conta_pluggy_id=ligacao.id,
            forma_pagamento_id=ligacao.forma_pagamento_id,
            data=data,
            valor=Decimal(valor),
            descricao=f"pendente {id_externo}",
            fatura_prevista=fatura_prevista,
        )
    )
    session.flush()


def _item_staging(session: Session, id_externo: str, data: date, valor: str) -> ImportacaoItem:
    importacao = Importacao(
        arquivo_nome=f"sync-{next(_seq)}",
        hash_arquivo=f"hash-sync-{next(_seq)}",
        status=StatusImportacao.CONCLUIDA,
    )
    session.add(importacao)
    session.flush()
    item = ImportacaoItem(
        importacao_id=importacao.id,
        linha_bruta="compra",
        data=data,
        valor=Decimal(valor),
        status=StatusItem.REJEITADO,
        id_externo=id_externo,
    )
    session.add(item)
    session.flush()
    return item


def _em(session: Session, hoje: date, competencia: date | None = None) -> Any:
    return InicioService(session, hoje=hoje).resumo(competencia or date(hoje.year, hoje.month, 1))


def test_janela_nao_soma_o_pagamento_da_fatura(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 10, 10), "100.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 12), "30.00", OUTUBRO)
    _pagamento(session, pix, date(2026, 10, 8), "500.00", OBS_PAGAMENTO_NA_CONTA)
    # O lado do cartão é o mesmo pagamento visto de lá: não aparece.
    _pagamento(session, a, date(2026, 10, 8), "500.00", OBS_PAGAMENTO_NO_CARTAO)
    session.commit()

    j = _resumo(session).janela
    assert (j.cartao, j.conta, j.total) == (Decimal("100.00"), Decimal("30.00"), Decimal("130.00"))
    assert sum(d.total for d in j.dias) == Decimal("130.00")
    assert [(p.data, p.valor, p.cartao, p.forma_pagamento_id) for p in j.pagamentos] == [
        (date(2026, 10, 8), Decimal("500.00"), "Cartão A", a.id)
    ]


def test_pendente_que_virou_lancada_nao_conta_duas_vezes(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 10, 14), "20.00", OUTUBRO)  # a p1 já lançada
    item = _item_staging(session, "p1", date(2026, 10, 14), "20.00")
    _pendente(session, ligacao, "p1", date(2026, 10, 14), "20.00", NOVEMBRO)
    _pendente(session, ligacao, "p2", date(2026, 10, 15), "5.00", NOVEMBRO)
    session.commit()

    r = _resumo(session)
    assert (r.janela.cartao_pendente, r.janela.cartao) == (Decimal("5.00"), Decimal("25.00"))
    aberta = r.faturas_abertas[0]
    assert (aberta.valor, aberta.pendente) == (Decimal("25.00"), Decimal("5.00"))

    item.deleted_em = datetime.now(UTC)
    session.commit()
    r = _resumo(session)
    assert (r.janela.cartao_pendente, r.janela.cartao) == (Decimal("25.00"), Decimal("45.00"))
    aberta = r.faturas_abertas[0]
    assert (aberta.valor, aberta.pendente) == (Decimal("45.00"), Decimal("25.00"))
    assert r.gasto == Decimal("20.00")  # pendente nunca entra no gasto


def test_janela_de_30_dias_atravessa_a_virada_do_mes(session: Session) -> None:
    banco = _conta(session, "Banco")
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, pix, date(2026, 10, 6), "1.00", OUTUBRO)  # um dia antes: fora
    _gasto(session, pix, date(2026, 10, 7), "10.00", OUTUBRO)
    _gasto(session, pix, date(2026, 11, 5), "100.00", NOVEMBRO)
    session.commit()

    j = _em(session, date(2026, 11, 5)).janela
    assert j.inicio == date(2026, 10, 7) and j.hoje == date(2026, 11, 5)
    assert j.fim == j.hoje and not j.vencimentos
    assert len(j.dias) == 30 and not any(d.a_pagar for d in j.dias)
    assert (j.dias[0].data, j.dias[0].conta) == (date(2026, 10, 7), Decimal("10.00"))
    assert (j.dias[-1].data, j.dias[-1].conta) == (date(2026, 11, 5), Decimal("100.00"))
    assert j.total == j.conta == Decimal("110.00")


def test_vencimentos_na_faixa_a_pagar(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=10, vence=20)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=12, vence=25)
    e = _forma(session, "Cartão E", TipoPagamento.CREDITO, banco, fecha=20, vence=1)
    g = _forma(session, "Cartão G", TipoPagamento.CREDITO, banco, fecha=5, vence=18)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 10, 5), "100.00", OUTUBRO)
    _gasto(session, b, date(2026, 10, 6), "200.00", OUTUBRO)
    _gasto(session, e, date(2026, 10, 10), "70.00", NOVEMBRO)  # vence 01/11 = hoje + 16
    _gasto(session, g, date(2026, 10, 7), "50.00", OUTUBRO)
    _pagamento(session, g, date(2026, 10, 12), "50.00", OBS_PAGAMENTO_NO_CARTAO)  # já paga
    _pendente(session, ligacao, "pa1", date(2026, 10, 14), "15.00", OUTUBRO)
    _pendente(session, ligacao, "pa2", date(2026, 10, 15), "9.00", NOVEMBRO)  # outra fatura
    session.commit()

    j = _resumo(session).janela
    assert [(v.data, v.cartao, v.valor, v.pendente) for v in j.vencimentos] == [
        (date(2026, 10, 20), "Cartão A", Decimal("100.00"), Decimal("15.00")),
        (date(2026, 10, 25), "Cartão B", Decimal("200.00"), Decimal("0")),
    ]
    assert j.vencimentos[0].origem_vencimento == "cadastro"
    assert j.fim == date(2026, 10, 25)
    assert len(j.dias) == 30 + 9
    assert [d.a_pagar for d in j.dias].count(True) == 9
    assert all(d.total == 0 for d in j.dias if d.a_pagar)


def test_vencimentos_atravessam_o_mes(session: Session) -> None:
    banco = _conta(session, "Banco")
    x = _forma(session, "Cartão X", TipoPagamento.CREDITO, banco, fecha=20, vence=3)
    _gasto(session, x, date(2026, 10, 22), "80.00", NOVEMBRO)
    session.commit()

    j = _em(session, date(2026, 10, 25), OUTUBRO).janela
    assert [(v.data, v.cartao, v.valor) for v in j.vencimentos] == [
        (date(2026, 11, 3), "Cartão X", Decimal("80.00"))
    ]
    assert j.fim == date(2026, 11, 3)


def test_fatura_aberta_com_pendentes(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    la = _liga_pluggy(session, a, banco, "acc-a")
    lb = _liga_pluggy(session, b, banco, "acc-b")
    _gasto(session, a, date(2026, 10, 5), "40.00", OUTUBRO)
    _gasto(session, a, date(2026, 10, 10), "25.00", OUTUBRO)
    _pendente(session, la, "pa-dentro", date(2026, 10, 12), "30.00", NOVEMBRO)
    _pendente(session, la, "pa-antes", date(2026, 10, 1), "99.00", OUTUBRO)  # antes de `desde`
    _pendente(session, lb, "pb", date(2026, 10, 10), "12.00", NOVEMBRO)  # só pendente
    session.commit()

    abertas = {f.cartao: f for f in _resumo(session).faturas_abertas}
    assert set(abertas) == {"Cartão A", "Cartão B"}
    a_aberta = abertas["Cartão A"]
    assert (a_aberta.valor, a_aberta.pendente) == (Decimal("95.00"), Decimal("30.00"))
    evolucao = {p.data: p.acumulado for p in a_aberta.evolucao}
    assert evolucao[date(2026, 10, 11)] == Decimal("65.00")
    assert evolucao[date(2026, 10, 12)] == Decimal("95.00")
    assert evolucao[HOJE] == Decimal("95.00")
    assert (abertas["Cartão B"].valor, abertas["Cartão B"].pendente) == (
        Decimal("12.00"),
        Decimal("12.00"),
    )


def test_gasto_pela_data_da_compra_difere_do_da_competencia(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=20, vence=10)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    hoje = date(2026, 11, 5)
    _gasto(session, a, date(2026, 10, 28), "40.00", NOVEMBRO)  # compra de out., competência nov.
    _gasto(session, pix, date(2026, 10, 4), "7.00", OUTUBRO)
    _gasto(session, pix, date(2026, 10, 10), "20.00", OUTUBRO)
    _gasto(session, pix, date(2026, 11, 3), "10.00", NOVEMBRO)
    _pendente(session, ligacao, "p", date(2026, 11, 2), "99.00", NOVEMBRO)
    session.commit()

    nov = _em(session, hoje, NOVEMBRO)
    assert nov.gasto == Decimal("50.00")  # fatura 40 + Pix 10
    assert nov.gasto_compra == Decimal("10.00")
    assert nov.gasto_compra_mes_anterior == Decimal("7.00")  # outubro até o dia 5
    assert nov.diferenca_compra_mes_anterior == Decimal("3.00")
    assert nov.saiu_da_conta == {p.dia: p.acumulado for p in nov.serie}[5] == Decimal("10.00")
    assert (
        nov.a_pagar_mes
        == Decimal("40.00")
        == sum(f.valor for f in nov.faturas if f.situacao == "a_pagar")
    )

    out = _em(session, hoje, OUTUBRO)
    assert out.gasto == Decimal("27.00")
    assert out.gasto_compra == Decimal("67.00")
    assert out.gasto_compra_mes_anterior == Decimal("0")

    fut = _em(session, hoje, date(2026, 12, 1))
    assert (fut.gasto_compra, fut.saiu_da_conta) == (Decimal("0"), Decimal("0"))
