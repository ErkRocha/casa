"""Tela Início (D-22): somas, previsão e avisos, todos do banco.

"Hoje" é 16/10/2026. Os números foram escolhidos para a conta fechar à mão:

    outubro (competência), até o dia 16:
      compra de cartão com data 25/09 (fatura de outubro)  100,00  dia 1
      05/10 Restaurante, Laura                               50,00
      10/10 sem categoria, conjunto                          30,00
      20/10 Mercado (depois de hoje: fora)                   40,00
      receita 05/10                                        1000,00
      transferência 06/10 (fora de tudo)                    999,00
    gasto 180,00 · comprometido 100,00 · receitas 1000,00
    previsão = 100 + (180 - 100) / 16 * 31 = 255,00
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import TipoConta, TipoTransacao
from app.models import Categoria, Conta, Orcamento, Pessoa, Transacao
from app.services.inicio import InicioService

HOJE = date(2026, 10, 16)
OUTUBRO = date(2026, 10, 1)


def _t(
    session: Session,
    data: date,
    valor: str,
    competencia: date,
    *,
    tipo: TipoTransacao = TipoTransacao.DESPESA,
    categoria: Categoria | None = None,
    pessoa: Pessoa | None = None,
    descricao: str | None = None,
    contas: tuple[Conta, Conta] | None = None,
) -> None:
    session.add(
        Transacao(
            data=data,
            competencia=competencia,
            valor=Decimal(valor),
            tipo=tipo,
            descricao=descricao or f"lançamento {data} {valor}",
            descricao_original=descricao or f"LANCAMENTO {data} {valor}",
            categoria_id=categoria.id if categoria else None,
            pessoa_id=pessoa.id if pessoa else None,
            conta_origem_id=contas[0].id if contas else None,
            conta_destino_id=contas[1].id if contas else None,
        )
    )


@pytest.fixture
def mes(session: Session) -> dict[str, Any]:
    laura, erik = Pessoa(nome="Laura"), Pessoa(nome="Erik")
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    restaurante = Categoria(nome="Restaurante", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    a = Conta(nome="Banco A", tipo=TipoConta.CORRENTE)
    b = Conta(nome="Banco B", tipo=TipoConta.CORRENTE)
    session.add_all([laura, erik, mercado, restaurante, salario, a, b])
    session.flush()

    _t(session, date(2026, 9, 25), "100.00", OUTUBRO, categoria=mercado, pessoa=erik)
    _t(session, date(2026, 10, 5), "50.00", OUTUBRO, categoria=restaurante, pessoa=laura)
    _t(session, date(2026, 10, 10), "30.00", OUTUBRO)
    _t(session, date(2026, 10, 20), "40.00", OUTUBRO, categoria=mercado, pessoa=erik)
    _t(
        session,
        date(2026, 10, 5),
        "1000.00",
        OUTUBRO,
        tipo=TipoTransacao.RECEITA,
        categoria=salario,
    )
    _t(
        session,
        date(2026, 10, 6),
        "999.00",
        OUTUBRO,
        tipo=TipoTransacao.TRANSFERENCIA,
        contas=(a, b),
    )
    # Setembro: só o que caiu até o dia 16 entra na comparação.
    _t(session, date(2026, 9, 3), "70.00", date(2026, 9, 1), categoria=mercado)
    _t(session, date(2026, 9, 28), "500.00", date(2026, 9, 1), categoria=mercado)

    session.add_all(
        [
            Orcamento(categoria_id=mercado.id, competencia=OUTUBRO, valor_meta=Decimal("500")),
            # 50 de 55 = 90,9%: a detecção de atenção (>= 80%) dispara.
            Orcamento(categoria_id=restaurante.id, competencia=OUTUBRO, valor_meta=Decimal("55")),
        ]
    )
    session.commit()
    return {"laura": laura, "erik": erik, "mercado": mercado, "restaurante": restaurante}


def _resumo(session: Session, competencia: date | None = OUTUBRO) -> Any:
    return InicioService(session, hoje=HOJE).resumo(competencia)


class TestMesCorrente:
    def test_totais_e_comparacao(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session)
        assert (r.situacao, r.dias_no_mes, r.dia_referencia) == ("corrente", 31, 16)
        assert r.tem_dados is True
        assert r.gasto == Decimal("180.00")
        assert r.receitas == Decimal("1000.00")
        assert r.sobra == Decimal("820.00")
        assert r.gasto_mes_anterior == Decimal("70.00")
        assert r.diferenca_mes_anterior == Decimal("110.00")

    def test_previsao_separa_o_comprometido(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session)
        assert r.previsao is not None
        assert r.previsao.comprometido == Decimal("100.00")
        assert r.previsao.valor == Decimal("255.00")
        assert r.previsao.diferenca_orcamento == Decimal("-300.00")

    def test_orcamento_total_e_faixa(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session)
        assert r.orcamento is not None
        assert r.orcamento.total == Decimal("555.00")
        assert r.orcamento.percentual_usado == 32  # 180 / 555
        assert r.orcamento.faixa == "ok"

    def test_serie_acumulada_dia_a_dia(self, session: Session, mes: dict[str, Any]) -> None:
        serie = {p.dia: p.acumulado for p in _resumo(session).serie}
        assert list(serie) == list(range(1, 17))
        assert serie[1] == Decimal("100.00")  # a fatura conta no dia 1
        assert serie[4] == Decimal("100.00")
        assert serie[5] == Decimal("150.00")
        assert serie[16] == Decimal("180.00")

    def test_quem_gastou(self, session: Session, mes: dict[str, Any]) -> None:
        pessoas = [(p.nome, p.valor, p.percentual) for p in _resumo(session).pessoas]
        assert pessoas == [
            ("Erik", Decimal("100.00"), 56),
            ("Laura", Decimal("50.00"), 28),
            ("Juntos", Decimal("30.00"), 17),
        ]

    def test_categorias_com_sem_categoria_no_fim(
        self, session: Session, mes: dict[str, Any]
    ) -> None:
        categorias = [
            (c.nome, c.valor, c.percentual, c.largura) for c in _resumo(session).categorias
        ]
        assert categorias == [
            ("Mercado", Decimal("100.00"), 56, 100),
            ("Restaurante", Decimal("50.00"), 28, 50),
            ("Sem categoria", Decimal("30.00"), 17, 30),
        ]

    def test_aviso_de_orcamento_vem_da_deteccao(
        self, session: Session, mes: dict[str, Any]
    ) -> None:
        avisos = _resumo(session).avisos
        assert len(avisos) == 1
        aviso = avisos[0]
        assert aviso.tipo == "orcamento"
        assert aviso.categoria == "Restaurante"
        assert aviso.situacao == "atencao"
        assert aviso.dias_restantes == 15

    def test_faixa_perto_e_estourado(self, session: Session, mes: dict[str, Any]) -> None:
        orcamentos = session.query(Orcamento).all()
        for o in orcamentos:
            o.valor_meta = Decimal("95")  # 180 / 190 = 94,7%
        session.commit()
        assert _resumo(session).orcamento.faixa == "perto"  # type: ignore[union-attr]
        for o in orcamentos:
            o.valor_meta = Decimal("80")  # 180 / 160
        session.commit()
        assert _resumo(session).orcamento.faixa == "estourado"  # type: ignore[union-attr]


class TestOutrosMeses:
    def test_mes_passado_vale_inteiro_e_sem_previsao(
        self, session: Session, mes: dict[str, Any]
    ) -> None:
        r = _resumo(session, date(2026, 9, 1))
        assert (r.situacao, r.dia_referencia) == ("passado", 30)
        assert r.gasto == Decimal("570.00")
        assert r.previsao is None
        assert r.orcamento is None
        assert len(r.serie) == 30

    def test_mes_futuro_vazio(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session, date(2026, 11, 1))
        assert (r.situacao, r.dia_referencia, r.tem_dados) == ("futuro", 0, False)
        assert r.gasto == Decimal("0")
        assert r.serie == [] and r.categorias == [] and r.avisos == []
        assert r.previsao is None
        assert all(p.valor == 0 and p.percentual == 0 for p in r.pessoas)

    def test_mes_sem_dados(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session, date(2026, 6, 1))
        assert r.tem_dados is False
        assert r.gasto == Decimal("0")
        assert r.categorias == []


def test_reajuste_vira_aviso(session: Session) -> None:
    for mes, valor in [(7, "39.90"), (8, "39.90"), (9, "39.90"), (10, "44.90")]:
        _t(session, date(2026, mes, 5), valor, date(2026, mes, 1), descricao="Streaming")
    session.commit()
    avisos = [a for a in _resumo(session).avisos if a.tipo == "reajuste"]
    assert len(avisos) == 1
    assert avisos[0].descricao == "Streaming"
    assert (avisos[0].valor_anterior, avisos[0].valor_atual) == (
        Decimal("39.90"),
        Decimal("44.90"),
    )


def test_endpoint(client: TestClient, mes: dict[str, Any]) -> None:
    resposta = client.get("/analytics/inicio", params={"competencia": "2099-01-01"})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["situacao"] == "futuro"
    assert corpo["gasto"] == "0"
    assert client.get("/analytics/inicio").status_code == 200
