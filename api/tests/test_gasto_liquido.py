"""Gasto líquido (D-34): despesa menos estorno em toda soma de gasto.

"Hoje" é 16/10/2026. Outubro, pela data da compra, até o dia 16:

    Restaurante, Laura   despesa 100,00 (05/10) - estorno 30,00 (08/10) = 70,00
    Mercado, Erik        despesa  60,00 (06/10)
    sem categoria        despesa  20,00 (07/10)
    receita 1000,00 (o estorno nunca é receita)
    cartão A (fecha dia 2): despesa 100,00 (25/09) + 50,00 (12/10) - estorno 30,00 (08/10)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.enums import TipoPagamento, TipoTransacao
from app.insights import tools
from app.mcp.consultas import FiltroTransacoes, totalizar_transacoes
from app.medias import media_mensal_despesas
from app.models import Categoria, Orcamento, Pessoa, Transacao
from app.schemas.transacoes import TransacaoFiltros
from app.services.analises import AnalisesService
from app.services.analytics import AnalyticsService
from app.services.inicio import InicioService
from app.services.transacoes import TransacaoService
from tests.test_caixa import _conta, _forma

HOJE = date(2026, 10, 16)
OUTUBRO = date(2026, 10, 1)
D, E, R = TipoTransacao.DESPESA, TipoTransacao.ESTORNO, TipoTransacao.RECEITA


def _t(
    session: Session,
    data: date,
    valor: str,
    tipo: TipoTransacao = D,
    *,
    competencia: date = OUTUBRO,
    categoria: Categoria | None = None,
    pessoa: Pessoa | None = None,
    forma_id: int | None = None,
    descricao: str | None = None,
) -> None:
    session.add(
        Transacao(
            data=data,
            competencia=competencia,
            valor=Decimal(valor),
            tipo=tipo,
            descricao=descricao or f"{tipo.value} {data} {valor}",
            descricao_original=f"{tipo.value.upper()} {data} {valor}",
            categoria_id=categoria.id if categoria else None,
            pessoa_id=pessoa.id if pessoa else None,
            forma_pagamento_id=forma_id,
        )
    )


@pytest.fixture
def mes(session: Session) -> dict[str, Any]:
    laura, erik = Pessoa(nome="Laura"), Pessoa(nome="Erik")
    restaurante = Categoria(nome="Restaurante", tipo=TipoTransacao.DESPESA)
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    session.add_all([laura, erik, restaurante, mercado, salario])
    session.flush()
    _t(session, date(2026, 10, 5), "100.00", categoria=restaurante, pessoa=laura)
    _t(session, date(2026, 10, 8), "30.00", E, categoria=restaurante, pessoa=laura)
    _t(session, date(2026, 10, 6), "60.00", categoria=mercado, pessoa=erik)
    _t(session, date(2026, 10, 7), "20.00")
    _t(session, date(2026, 10, 5), "1000.00", R, categoria=salario)
    session.add(
        Orcamento(categoria_id=restaurante.id, competencia=OUTUBRO, valor_meta=Decimal("100"))
    )
    session.commit()
    return {"laura": laura, "erik": erik, "restaurante": restaurante}


def test_inicio_gasto_pessoas_categorias_e_orcamento(session: Session, mes: dict[str, Any]) -> None:
    r = InicioService(session, hoje=HOJE).resumo(OUTUBRO)
    assert r.gasto == Decimal("150.00")  # 70 + 60 + 20
    assert r.receitas == Decimal("1000.00")  # o estorno não é receita
    assert {p.nome: p.valor for p in r.pessoas} == {
        "Erik": Decimal("60.00"),
        "Laura": Decimal("70.00"),
        "Juntos": Decimal("20.00"),
    }
    assert {c.nome: c.valor for c in r.categorias}["Restaurante"] == Decimal("70.00")
    assert r.orcamento is not None
    assert r.orcamento.percentual_usado == 150  # 150 de 100: o orçamento é só do restaurante


def test_analises_mensal_categorias_e_orcamento(session: Session, mes: dict[str, Any]) -> None:
    r = AnalisesService(session, hoje=HOJE).resumo("3m", None, "caixa")
    restaurante = next(o for o in r.orcamento if o.nome == "Restaurante")
    assert restaurante.gasto == Decimal("70.00")
    assert r.meses[-1].despesas == Decimal("150.00")
    assert r.meses[-1].receitas == Decimal("1000.00")


def test_analytics_divisao_e_orcamento(session: Session, mes: dict[str, Any]) -> None:
    servico = AnalyticsService(session, hoje=HOJE)
    divisao = servico.divisao_pessoas(TransacaoFiltros(), OUTUBRO)
    assert divisao.total == Decimal("150.00")
    assert {linha.nome: linha.valor for linha in divisao.linhas}["Laura"] == Decimal("70.00")
    orcamento = servico.orcamento(OUTUBRO)
    assert orcamento.linhas[0].realizado == Decimal("70.00")


def test_listagem_totais_e_dias(session: Session, mes: dict[str, Any]) -> None:
    servico = TransacaoService(session)
    totais = servico.totais(TransacaoFiltros())
    assert totais["total_despesa"] == Decimal("150.00")
    assert totais["total_receita"] == Decimal("1000.00")
    assert totais["resultado"] == Decimal("850.00")
    assert sum(totais["por_balde"].values()) == Decimal("150.00")
    dia = {d["data"]: d for d in servico.dias(TransacaoFiltros())}[date(2026, 10, 8)]
    assert dia["despesas"] == Decimal("-30.00")


def test_media_mensal(session: Session, mes: dict[str, Any]) -> None:
    assert media_mensal_despesas(session, OUTUBRO, OUTUBRO).media == Decimal("150.00")


def test_tools_de_insights(session: Session, mes: dict[str, Any]) -> None:
    resumo = tools.resumo_mensal(session, OUTUBRO, HOJE)
    assert (resumo.receitas, resumo.despesas, resumo.saldo) == (
        Decimal("1000.00"),
        Decimal("150.00"),
        Decimal("850.00"),
    )
    assert tools.cobertura_categorias(session, OUTUBRO).total == Decimal("150.00")
    por_categoria = {
        linha.categoria: linha.total for linha in tools.gasto_por_categoria(session, OUTUBRO).linhas
    }
    assert por_categoria["Restaurante"] == Decimal("70.00")
    por_pessoa = {
        linha.pessoa: linha.total for linha in tools.divisao_pessoas(session, OUTUBRO).linhas
    }
    assert por_pessoa["Laura"] == Decimal("70.00")
    assert tools.comparar_periodos(session, OUTUBRO).total_atual == Decimal("150.00")
    assert tools.status_orcamento(session, OUTUBRO).linhas[0].realizado == Decimal("70.00")


def test_mcp_totais(session: Session, mes: dict[str, Any]) -> None:
    totais = totalizar_transacoes(session, FiltroTransacoes(competencia=OUTUBRO))
    assert totais.despesas == Decimal("150.00")
    assert totais.receitas == Decimal("1000.00")
    assert totais.saldo == Decimal("850.00")


def test_fatura_do_cartao_abate_o_estorno(session: Session) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão A", TipoPagamento.CREDITO, banco, fecha=2, vence=7)
    _t(session, date(2026, 9, 25), "100.00", forma_id=cartao.id)
    _t(session, date(2026, 10, 12), "50.00", forma_id=cartao.id)
    _t(session, date(2026, 10, 8), "30.00", E, forma_id=cartao.id)
    session.commit()

    r = InicioService(session, hoje=HOJE).resumo(OUTUBRO)
    assert [(f.cartao, f.valor) for f in r.caixa.faturas] == [("Cartão A", Decimal("120.00"))]
    # Fatura aberta (desde 02/10): 50 - 30.
    assert [(f.cartao, f.valor) for f in r.faturas_abertas] == [("Cartão A", Decimal("20.00"))]
    assert r.caixa.serie[-1].com_a_pagar == Decimal("120.00")


def test_reajuste_ignora_estorno(session: Session) -> None:
    """O reajuste é achado pelas cobranças; o estorno do mês não as altera nem as duplica."""
    for mes, valor in (
        (date(2026, 7, 1), "19.90"),
        (date(2026, 8, 1), "19.90"),
        (date(2026, 9, 1), "19.90"),
        (OUTUBRO, "27.90"),
    ):
        _t(session, mes.replace(day=5), valor, competencia=mes, descricao="Streaming X")
    _t(session, date(2026, 10, 9), "5.00", E, descricao="Streaming X")
    session.commit()
    (reajuste,) = tools.recorrencias_com_reajuste(session, OUTUBRO).linhas
    assert (reajuste.valor_anterior, reajuste.valor_atual) == (Decimal("19.90"), Decimal("27.90"))
