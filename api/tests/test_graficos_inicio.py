"""Gráfico de linhas "Gastos nos últimos 30 dias" do Início (D-28).

"Hoje" é 16/10/2026: a janela vai de 17/09 a 16/10 (30 dias). Cada teste monta
só o que precisa.
"""

from __future__ import annotations

import itertools
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    PluggyPendente,
    Transacao,
)
from app.services.graficos_inicio import GraficosInicioService

HOJE = date(2026, 10, 16)
INICIO = date(2026, 9, 17)
OUTUBRO = date(2026, 10, 1)
NOVEMBRO = date(2026, 11, 1)

_seq = itertools.count(1)


def _pessoa(session: Session, nome: str) -> Pessoa:
    pessoa = Pessoa(nome=nome)
    session.add(pessoa)
    session.flush()
    return pessoa


def _conta(session: Session, nome: str, titular: Pessoa | None = None) -> Conta:
    conta = Conta(nome=nome, tipo=TipoConta.CORRENTE, titular_id=titular.id if titular else None)
    session.add(conta)
    session.flush()
    return conta


def _forma(
    session: Session,
    apelido: str,
    tipo: TipoPagamento,
    conta: Conta | None = None,
) -> FormaPagamento:
    forma = FormaPagamento(apelido=apelido, tipo=tipo, conta_id=conta.id if conta else None)
    session.add(forma)
    session.flush()
    return forma


def _gasto(
    session: Session,
    forma: FormaPagamento | None,
    data: date,
    valor: str,
    *,
    tipo: TipoTransacao = TipoTransacao.DESPESA,
    contas: tuple[Conta, Conta] | None = None,
) -> None:
    n = next(_seq)
    session.add(
        Transacao(
            data=data,
            competencia=date(data.year, data.month, 1),
            valor=Decimal(valor),
            tipo=tipo,
            descricao=f"compra {n}",
            descricao_original=f"COMPRA {n}",
            forma_pagamento_id=forma.id if forma else None,
            conta_origem_id=contas[0].id if contas else None,
            conta_destino_id=contas[1].id if contas else None,
        )
    )
    session.flush()


def _liga_pluggy(
    session: Session, forma: FormaPagamento, conta: Conta, account_id: str, *, ativo: bool = True
) -> ContaPluggy:
    ligacao = ContaPluggy(
        pluggy_item_id="item-1",
        pluggy_account_id=account_id,
        conta_id=conta.id,
        forma_pagamento_id=forma.id,
        sincronizar_desde=date(2026, 1, 1),
        ativo=ativo,
    )
    session.add(ligacao)
    session.flush()
    return ligacao


def _pendente(
    session: Session,
    ligacao: ContaPluggy,
    id_externo: str,
    data: date,
    valor: str,
    fatura_prevista: date | None = NOVEMBRO,
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


def _item_staging(
    session: Session,
    id_externo: str | None,
    data: date,
    valor: str,
    *,
    forma: FormaPagamento | None = None,
    observacao: str | None = None,
) -> ImportacaoItem:
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
        forma_pagamento_sugerida_id=forma.id if forma else None,
        observacao=observacao,
    )
    session.add(item)
    session.flush()
    return item


def _gastos(
    session: Session,
    hoje: date = HOJE,
    *,
    pessoa_id: int | None = None,
    series: list[str] | None = None,
    somar: bool = False,
) -> Any:
    session.commit()
    return GraficosInicioService(session, hoje=hoje).gastos_30_dias(pessoa_id, series, somar)


def _acumulados(serie: Any) -> dict[date, Decimal]:
    return {p.data: p.acumulado for p in serie.pontos}


def _por_chave(resposta: Any) -> dict[str, Any]:
    return {s.chave: s for s in resposta.series}


def test_acumulado_por_serie_dia_a_dia(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    debito = _forma(session, "Débito", TipoPagamento.DEBITO, banco)
    _gasto(session, a, date(2026, 9, 18), "10.00")
    _gasto(session, a, date(2026, 9, 18), "2.50")
    _gasto(session, a, date(2026, 9, 25), "5.50")
    _gasto(session, a, HOJE, "1.00")
    _gasto(session, pix, INICIO, "20.00")  # no primeiro dia da janela
    _gasto(session, pix, date(2026, 9, 20), "3.00")
    _gasto(session, debito, date(2026, 10, 1), "7.00")
    _gasto(session, a, date(2026, 9, 16), "999.00")  # um dia antes: fora

    r = _gastos(session)
    assert (r.inicio, r.hoje) == (INICIO, HOJE)
    assert [s.chave for s in r.series] == [f"cartao:{a.id}", "pix", "debito"]
    assert [(s.rotulo, s.tipo) for s in r.series] == [
        ("Cartão A", "cartao"),
        ("Pix", "pix"),
        ("Débito", "debito"),
    ]
    assert r.series[0].forma_pagamento_id == a.id and r.series[1].forma_pagamento_id is None
    por = _por_chave(r)

    for serie in r.series:
        assert len(serie.pontos) == 30
        assert serie.pontos[0].data == INICIO and serie.pontos[-1].data == HOJE
        valores = [p.acumulado for p in serie.pontos]
        assert valores == sorted(valores)  # nunca desce

    cartao = _acumulados(por[f"cartao:{a.id}"])
    assert cartao[INICIO] == Decimal("0")  # zero antes da primeira compra
    assert cartao[date(2026, 9, 17)] == Decimal("0")
    assert cartao[date(2026, 9, 18)] == Decimal("12.50")
    assert cartao[date(2026, 9, 24)] == Decimal("12.50")
    assert cartao[date(2026, 9, 25)] == Decimal("18.00")
    assert cartao[date(2026, 10, 15)] == Decimal("18.00")
    assert cartao[HOJE] == Decimal("19.00")
    assert por[f"cartao:{a.id}"].total == Decimal("19.00")

    pix_ac = _acumulados(por["pix"])
    assert pix_ac[INICIO] == Decimal("20.00")  # começa no valor do 1º dia
    assert pix_ac[date(2026, 9, 19)] == Decimal("20.00")
    assert pix_ac[date(2026, 9, 20)] == Decimal("23.00")
    assert pix_ac[HOJE] == Decimal("23.00")

    deb = _acumulados(por["debito"])
    assert deb[date(2026, 9, 30)] == Decimal("0")
    assert deb[date(2026, 10, 1)] == Decimal("7.00")
    assert deb[HOJE] == Decimal("7.00")

    assert all(s.visivel and s.pendente == 0 for s in r.series)
    assert r.total == Decimal("49.00") and r.pendente == Decimal("0")
    assert r.soma is None and r.pessoa_id is None


def test_ordem_e_agrupamento_das_series(session: Session) -> None:
    banco = _conta(session, "Banco")
    zeta = _forma(session, "Zeta", TipoPagamento.CREDITO, banco)
    alfa = _forma(session, "Alfa", TipoPagamento.CREDITO, banco)
    _forma(session, "Cartão sem gasto", TipoPagamento.CREDITO, banco)
    pix1 = _forma(session, "Pix 1", TipoPagamento.PIX, banco)
    pix2 = _forma(session, "Pix 2", TipoPagamento.PIX, banco)
    boleto = _forma(session, "Boleto", TipoPagamento.BOLETO, banco)
    dinheiro = _forma(session, "Dinheiro", TipoPagamento.DINHEIRO)
    transf = _forma(session, "TED", TipoPagamento.TRANSFERENCIA, banco)
    for forma in (boleto, dinheiro, transf, pix1, pix2, zeta, alfa):
        _gasto(session, forma, date(2026, 10, 2), "10.00")
    _gasto(session, None, date(2026, 10, 3), "5.00")  # despesa sem forma

    r = _gastos(session)
    assert [s.rotulo for s in r.series] == ["Alfa", "Zeta", "Pix", "Boleto", "Outros"]
    por = _por_chave(r)
    assert por["pix"].total == Decimal("20.00")  # soma de todas as formas pix
    assert por["outros"].total == Decimal("25.00")  # dinheiro + TED + sem forma


def test_soma_de_todas_e_de_series_escolhidas(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 9, 20), "10.00")
    _gasto(session, a, date(2026, 10, 10), "4.00")
    _gasto(session, b, date(2026, 9, 22), "100.00")
    _gasto(session, pix, date(2026, 9, 20), "1.00")
    _gasto(session, pix, date(2026, 10, 12), "2.00")
    _pendente(session, ligacao, "p1", date(2026, 10, 12), "6.00")

    sem_soma = _gastos(session)
    assert sem_soma.soma is None

    todas = _gastos(session, somar=True)
    assert todas.soma is not None
    assert todas.soma.chave == "soma" and todas.soma.cor == "serie-soma"
    assert todas.soma.rotulo == "Soma das selecionadas"
    assert len(todas.soma.pontos) == 30
    for i, ponto in enumerate(todas.soma.pontos):
        assert ponto.acumulado == sum((s.pontos[i].acumulado for s in todas.series), Decimal(0))
        assert ponto.pendente_acumulado == sum(
            (s.pontos[i].pendente_acumulado for s in todas.series), Decimal(0)
        )
    assert todas.soma.pontos[-1].acumulado == todas.total == Decimal("123.00")
    assert todas.soma.total == Decimal("123.00") and todas.pendente == Decimal("6.00")

    escolhidas = [f"cartao:{a.id}", "pix"]
    r = _gastos(session, series=escolhidas, somar=True)
    por = _por_chave(r)
    assert {c: s.visivel for c, s in por.items()} == {
        f"cartao:{a.id}": True,
        f"cartao:{b.id}": False,
        "pix": True,
    }
    assert len(r.series) == 3  # todas seguem na resposta
    assert r.soma is not None
    visiveis = [s for s in r.series if s.visivel]
    for i, ponto in enumerate(r.soma.pontos):
        assert ponto.acumulado == sum((s.pontos[i].acumulado for s in visiveis), Decimal(0))
    soma = _acumulados(r.soma)
    assert soma[date(2026, 9, 20)] == Decimal("11.00")
    assert soma[date(2026, 10, 12)] == Decimal("23.00")  # 10 + 4 + 6 pendente + 1 + 2
    # Total e pendente só das visíveis: o cartão B (100) fica de fora.
    assert r.total == Decimal("23.00") == r.soma.total == soma[HOJE]
    assert r.pendente == Decimal("6.00")

    # Só o cartão B: o pendente do A não conta.
    so_b = _gastos(session, series=[f"cartao:{b.id}"], somar=True)
    assert (so_b.total, so_b.pendente) == (Decimal("100.00"), Decimal("0"))

    # Nenhuma visível (chave inexistente): sem soma e total zero.
    nenhuma = _gastos(session, series=["cartao:0"], somar=True)
    assert nenhuma.soma is None and nenhuma.total == 0 and nenhuma.pendente == 0
    assert not any(s.visivel for s in nenhuma.series)


def test_pendente_que_virou_item_de_staging_nao_duplica(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 10, 14), "20.00")  # a p1 já lançada
    item = _item_staging(session, "p1", date(2026, 10, 14), "20.00")
    _pendente(session, ligacao, "p1", date(2026, 10, 14), "20.00")
    _pendente(session, ligacao, "p2", date(2026, 10, 15), "5.00")

    r = _gastos(session)
    cartao = _por_chave(r)[f"cartao:{a.id}"]
    assert (cartao.total, cartao.pendente) == (Decimal("25.00"), Decimal("5.00"))
    assert _acumulados(cartao)[date(2026, 10, 14)] == Decimal("20.00")

    item.deleted_em = datetime.now(UTC)  # sem o staging, a p1 volta a valer
    r = _gastos(session)
    cartao = _por_chave(r)[f"cartao:{a.id}"]
    assert (cartao.total, cartao.pendente) == (Decimal("45.00"), Decimal("25.00"))


def test_pendente_marca_o_dia_e_soma_no_pendente(session: Session) -> None:
    banco = _conta(session, "Banco")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    ligacao = _liga_pluggy(session, a, banco, "acc-a")
    _gasto(session, a, date(2026, 10, 10), "40.00")
    _gasto(session, pix, date(2026, 10, 11), "9.00")
    _pendente(session, ligacao, "p1", date(2026, 10, 12), "30.00")
    _pendente(session, ligacao, "p2", date(2026, 10, 12), "2.00")
    _pendente(session, ligacao, "p3", date(2026, 10, 15), "8.00")
    _pendente(session, ligacao, "fora", date(2026, 9, 16), "500.00")  # antes da janela

    r = _gastos(session)
    cartao = _por_chave(r)[f"cartao:{a.id}"]
    pontos = {p.data: p for p in cartao.pontos}
    assert pontos[date(2026, 10, 11)].acumulado == Decimal("40.00")
    assert not pontos[date(2026, 10, 11)].tem_pendente
    assert pontos[date(2026, 10, 11)].pendente_acumulado == Decimal("0")
    assert pontos[date(2026, 10, 12)].acumulado == Decimal("72.00")
    assert pontos[date(2026, 10, 12)].pendente_acumulado == Decimal("32.00")
    assert pontos[date(2026, 10, 12)].tem_pendente
    assert not pontos[date(2026, 10, 13)].tem_pendente
    assert pontos[date(2026, 10, 13)].pendente_acumulado == Decimal("32.00")
    assert pontos[date(2026, 10, 15)].tem_pendente
    assert (cartao.total, cartao.pendente) == (Decimal("80.00"), Decimal("40.00"))
    assert not any(p.tem_pendente for p in _por_chave(r)["pix"].pontos)
    assert (r.total, r.pendente) == (Decimal("89.00"), Decimal("40.00"))

    com_soma = _gastos(session, somar=True)
    assert com_soma.soma is not None
    assert {p.data for p in com_soma.soma.pontos if p.tem_pendente} == {
        date(2026, 10, 12),
        date(2026, 10, 15),
    }


def test_receita_transferencia_e_pagamento_de_fatura_ficam_fora(session: Session) -> None:
    banco, banco2 = _conta(session, "Banco"), _conta(session, "Banco 2")
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, a, date(2026, 10, 5), "10.00")
    _gasto(session, pix, date(2026, 10, 6), "3.00")
    _gasto(session, pix, date(2026, 10, 7), "1000.00", tipo=TipoTransacao.RECEITA)
    _gasto(
        session,
        pix,
        date(2026, 10, 8),
        "700.00",
        tipo=TipoTransacao.TRANSFERENCIA,
        contas=(banco, banco2),
    )
    # Pagamento de fatura: item rejeitado (lado da conta e lado do cartão).
    _item_staging(session, None, date(2026, 10, 9), "500.00", forma=pix, observacao="pagamento")
    _item_staging(session, None, date(2026, 10, 9), "500.00", forma=a, observacao="pagamento")

    r = _gastos(session)
    por = _por_chave(r)
    assert por["pix"].total == Decimal("3.00")
    assert por[f"cartao:{a.id}"].total == Decimal("10.00")
    assert r.total == Decimal("13.00")


def test_janela_atravessa_a_virada_do_mes(session: Session) -> None:
    banco = _conta(session, "Banco")
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    _gasto(session, pix, date(2026, 10, 6), "1.00")  # um dia antes: fora
    _gasto(session, pix, date(2026, 10, 7), "10.00")
    _gasto(session, pix, date(2026, 10, 31), "5.00")
    _gasto(session, pix, date(2026, 11, 1), "7.00")
    _gasto(session, pix, date(2026, 11, 5), "100.00")

    r = _gastos(session, hoje=date(2026, 11, 5))
    assert (r.inicio, r.hoje) == (date(2026, 10, 7), date(2026, 11, 5))
    pontos = _por_chave(r)["pix"].pontos
    assert len(pontos) == 30
    assert [p.data for p in pontos][:2] == [date(2026, 10, 7), date(2026, 10, 8)]
    assert pontos[-1].data == date(2026, 11, 5)
    ac = _acumulados(_por_chave(r)["pix"])
    assert ac[date(2026, 10, 7)] == Decimal("10.00")
    assert ac[date(2026, 10, 30)] == Decimal("10.00")
    assert ac[date(2026, 10, 31)] == Decimal("15.00")
    assert ac[date(2026, 11, 1)] == Decimal("22.00")
    assert ac[date(2026, 11, 4)] == Decimal("22.00")
    assert ac[date(2026, 11, 5)] == Decimal("122.00") == r.total


def test_filtro_por_pessoa_e_pessoas_conectadas(session: Session) -> None:
    ana, beto, carla = (_pessoa(session, n) for n in ("Ana", "Beto", "Carla"))
    conta_ana = _conta(session, "Banco Ana", ana)
    conta_beto = _conta(session, "Banco Beto", beto)
    conta_carla = _conta(session, "Banco Carla", carla)  # sem Pluggy
    conjunta = _conta(session, "Conjunta")
    cartao_ana = _forma(session, "Cartão Ana", TipoPagamento.CREDITO, conta_ana)
    cartao_beto = _forma(session, "Cartão Beto", TipoPagamento.CREDITO, conta_beto)
    pix_ana = _forma(session, "Pix Ana", TipoPagamento.PIX, conta_ana)
    pix_beto = _forma(session, "Pix Beto", TipoPagamento.PIX, conta_beto)
    pix_carla = _forma(session, "Pix Carla", TipoPagamento.PIX, conta_carla)
    pix_conjunta = _forma(session, "Pix conjunta", TipoPagamento.PIX, conjunta)
    la = _liga_pluggy(session, cartao_ana, conta_ana, "acc-ana")
    lb = _liga_pluggy(session, cartao_beto, conta_beto, "acc-beto")
    # Ligação desativada não conecta a pessoa.
    _liga_pluggy(session, pix_carla, conta_carla, "acc-carla", ativo=False)
    _gasto(session, cartao_ana, date(2026, 10, 1), "10.00")
    _gasto(session, cartao_beto, date(2026, 10, 2), "20.00")
    _gasto(session, pix_ana, date(2026, 10, 3), "1.00")
    _gasto(session, pix_beto, date(2026, 10, 3), "2.00")
    _gasto(session, pix_carla, date(2026, 10, 3), "4.00")
    _gasto(session, pix_conjunta, date(2026, 10, 4), "8.00")
    _gasto(session, None, date(2026, 10, 4), "16.00")
    _pendente(session, la, "pa", date(2026, 10, 5), "100.00")
    _pendente(session, lb, "pb", date(2026, 10, 5), "200.00")

    todos = _gastos(session)
    conectadas = [(p.id, p.nome) for p in todos.pessoas_conectadas]
    assert conectadas == [(ana.id, "Ana"), (beto.id, "Beto")]
    assert todos.total == Decimal("361.00") and todos.pessoa_id is None

    so_ana = _gastos(session, pessoa_id=ana.id)
    assert so_ana.pessoa_id == ana.id
    assert {s.chave for s in so_ana.series} == {f"cartao:{cartao_ana.id}", "pix"}
    assert _por_chave(so_ana)["pix"].total == Decimal("1.00")
    assert so_ana.total == Decimal("111.00") and so_ana.pendente == Decimal("100.00")
    # O filtro não esconde as pessoas: o controle continua com as duas.
    assert len(so_ana.pessoas_conectadas) == 2

    so_beto = _gastos(session, pessoa_id=beto.id)
    assert {s.chave for s in so_beto.series} == {f"cartao:{cartao_beto.id}", "pix"}
    assert _por_chave(so_beto)["pix"].total == Decimal("2.00")
    assert so_beto.total == Decimal("222.00") and so_beto.pendente == Decimal("200.00")

    # Conta sem titular e despesa sem forma só aparecem sem filtro; a conta da
    # Carla (sem Pluggy ativa) é filtrável por id, mas não é oferecida.
    so_carla = _gastos(session, pessoa_id=carla.id)
    assert [s.chave for s in so_carla.series] == ["pix"] and so_carla.total == Decimal("4.00")
    assert "outros" not in {s.chave for s in so_ana.series + so_beto.series + so_carla.series}
    assert _por_chave(todos)["outros"].total == Decimal("16.00")
    assert _por_chave(todos)["pix"].total == Decimal("15.00")  # inclui a conta conjunta


def test_cor_do_cartao_e_estavel(session: Session) -> None:
    banco = _conta(session, "Banco")
    # Ids crescentes; só C e E têm mapeamento ativo da Pluggy, então vêm primeiro.
    a = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco)
    b = _forma(session, "Cartão B", TipoPagamento.CREDITO, banco)
    c = _forma(session, "Cartão C", TipoPagamento.CREDITO, banco)
    d = _forma(session, "Cartão D", TipoPagamento.CREDITO, banco)
    e = _forma(session, "Cartão E", TipoPagamento.CREDITO, banco)
    f = _forma(session, "Cartão F", TipoPagamento.CREDITO, banco)
    morto = _forma(session, "Cartão excluído", TipoPagamento.CREDITO, banco)
    _liga_pluggy(session, c, banco, "acc-c")
    _liga_pluggy(session, e, banco, "acc-e")
    morto.deleted_em = datetime.now(UTC)  # fora do ranking
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    # `f` só tem gasto numa janela anterior: a cor dele não pode depender disso.
    for forma in (a, b, c, d, e):
        _gasto(session, forma, date(2026, 10, 3), "1.00")
    _gasto(session, pix, date(2026, 10, 3), "1.00")
    _gasto(session, f, date(2026, 8, 20), "1.00")

    esperado = {
        c.id: "serie-1",
        e.id: "serie-2",
        a.id: "serie-3",
        b.id: "serie-4",
        d.id: "serie-1",  # quinto: o ciclo recomeça
        f.id: "serie-2",
    }

    def cores(r: Any) -> dict[str, str]:
        return {s.chave: s.cor for s in r.series}

    todas = cores(_gastos(session))
    for forma in (a, b, c, d, e):
        assert todas[f"cartao:{forma.id}"] == esperado[forma.id]
    assert todas["pix"] == "serie-pix"

    com_filtro = cores(_gastos(session, series=[f"cartao:{b.id}"], somar=True))
    assert com_filtro[f"cartao:{b.id}"] == "serie-4"
    assert com_filtro[f"cartao:{c.id}"] == "serie-1"

    # Outra janela (um mês antes): `f` aparece e as cores dos demais são as mesmas.
    antes = _gastos(session, hoje=date(2026, 9, 5))
    assert {s.chave for s in antes.series} == {f"cartao:{f.id}"}
    assert antes.series[0].cor == esperado[f.id]

    fixas = {"serie-pix", "serie-debito", "serie-boleto", "serie-outros", "serie-soma"}
    assert not (fixas & {v for k, v in todas.items() if k.startswith("cartao:")})


def test_cores_fixas_das_outras_series(session: Session) -> None:
    banco = _conta(session, "Banco")
    for apelido, tipo in (
        ("Pix", TipoPagamento.PIX),
        ("Débito", TipoPagamento.DEBITO),
        ("Boleto", TipoPagamento.BOLETO),
        ("Dinheiro", TipoPagamento.DINHEIRO),
    ):
        _gasto(session, _forma(session, apelido, tipo, banco), date(2026, 10, 3), "1.00")
    r = _gastos(session, somar=True)
    assert {s.chave: s.cor for s in r.series} == {
        "pix": "serie-pix",
        "debito": "serie-debito",
        "boleto": "serie-boleto",
        "outros": "serie-outros",
    }
    assert r.soma is not None and r.soma.cor == "serie-soma"


def test_sem_despesa_volta_vazio(session: Session) -> None:
    r = _gastos(session, somar=True)
    assert r.series == [] and r.soma is None
    assert (r.total, r.pendente) == (Decimal("0"), Decimal("0"))
    assert (r.inicio, r.hoje) == (INICIO, HOJE)


def test_rota_aceita_series_somar_e_pessoa(client: TestClient, session: Session) -> None:
    resposta = client.get(
        "/analytics/inicio/gastos-30-dias",
        params=[("series", "pix"), ("series", "cartao:13"), ("somar", "true")],
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["series"] == [] and corpo["soma"] is None and corpo["total"] == "0"
    assert corpo["pessoa_id"] is None
    assert (
        client.get("/analytics/inicio/gastos-30-dias", params={"pessoa_id": 7}).json()["pessoa_id"]
        == 7
    )
