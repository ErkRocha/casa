"""Média mensal: Análises e relatório pela mesma função (`app.medias`).

Histórico curto: o primeiro mês com dados é setembro. "Hoje" é 18/11/2026.

    setembro  despesa 300,00 (Mercado)
    outubro   só uma receita de 1.000,00: tem lançamento, gasto zero
    novembro  despesa 50,00 (mês corrente, fora da média)

Média dos meses fechados com lançamento: (300 + 0) / 2 = 150,00. Os meses
antes de setembro, sem nada lançado, não entram na conta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.insights import tools
from app.medias import media_mensal_despesas
from app.models import Categoria, Pessoa, Transacao
from app.services.analises import AnalisesService

HOJE = date(2026, 11, 18)
SET, OUT, NOV = date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)


@pytest.fixture
def curto(session: Session) -> Pessoa:
    erik = Pessoa(nome="Erik")
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    session.add_all([erik, mercado, salario])
    session.flush()
    for data, valor, tipo, categoria in [
        (date(2026, 9, 10), "300.00", TipoTransacao.DESPESA, mercado),
        (date(2026, 10, 5), "1000.00", TipoTransacao.RECEITA, salario),
        (date(2026, 11, 3), "50.00", TipoTransacao.DESPESA, mercado),
    ]:
        session.add(
            Transacao(
                data=data,
                competencia=data.replace(day=1),
                valor=Decimal(valor),
                tipo=tipo,
                descricao=f"lançamento {data}",
                descricao_original=f"LANCAMENTO {data}",
                categoria_id=categoria.id,
                pessoa_id=erik.id,
            )
        )
    session.commit()
    return erik


def test_funcao_ignora_meses_sem_lancamento(session: Session, curto: Pessoa) -> None:
    media = media_mensal_despesas(session, date(2025, 11, 1), OUT)
    assert (media.media, media.meses) == (Decimal("150.00"), 2)


def test_janela_sem_nenhum_lancamento(session: Session, curto: Pessoa) -> None:
    media = media_mensal_despesas(session, date(2025, 1, 1), date(2025, 12, 1))
    assert (media.media, media.meses) == (None, 0)


def test_pessoa_sem_gasto_no_mes_da_casa_conta_zero(session: Session, curto: Pessoa) -> None:
    media = media_mensal_despesas(session, date(2025, 11, 1), OUT, pessoa="conjunto")
    assert (media.media, media.meses) == (Decimal("0.00"), 2)


@pytest.mark.parametrize("base", ["caixa", "compra"])
def test_analises_e_relatorio_dao_a_mesma_media(session: Session, curto: Pessoa, base: str) -> None:
    analises = AnalisesService(session, hoje=HOJE).resumo("12m", base=base)  # type: ignore[arg-type]
    relatorio = tools.comparar_periodos(session, NOV)

    assert analises.media_mensal == relatorio.media_janela == Decimal("150.00")
    assert analises.meses_na_media == relatorio.meses_na_media == 2
    # As categorias dividem pelos mesmos dois meses, não pelos onze fechados.
    assert [(c.nome, c.valor) for c in analises.categorias] == [("Mercado", Decimal("150.00"))]


def test_periodo_de_3_meses_com_um_so_mes_de_base(session: Session, curto: Pessoa) -> None:
    # Setembro e outubro fechados; as mudanças comparam outubro com setembro.
    r = AnalisesService(session, hoje=HOJE).resumo("3m")
    assert (r.media_mensal, r.meses_na_media) == (Decimal("150.00"), 2)
    assert r.mudancas is not None and r.mudancas.meses_base == 1


def test_sem_mes_fechado_com_dados_categorias_mostram_o_mes(session: Session) -> None:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add(mercado)
    session.flush()
    session.add(
        Transacao(
            data=date(2026, 11, 3),
            competencia=NOV,
            valor=Decimal("80.00"),
            tipo=TipoTransacao.DESPESA,
            descricao="só novembro",
            descricao_original="SO NOVEMBRO",
            categoria_id=mercado.id,
        )
    )
    session.commit()
    r = AnalisesService(session, hoje=HOJE).resumo("12m")
    assert (r.media_mensal, r.meses_na_media, r.base_categorias) == (None, 0, "mes")
    assert [(c.nome, c.valor) for c in r.categorias] == [("Mercado", Decimal("80.00"))]
    assert r.mudancas is None
