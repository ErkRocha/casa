"""Tela Início (D-24, D-31): somas, previsão e avisos, todos do banco.

"Hoje" é 16/10/2026. Os números foram escolhidos para a conta fechar à mão:

    lançamentos com competência de outubro:
      compra de cartão com data 25/09 (fatura de outubro)  100,00
      05/10 Restaurante, Laura                               50,00
      10/10 sem categoria, conjunto                          30,00
      20/10 Mercado (depois de hoje)                         40,00
      receita 05/10                                        1000,00
      transferência 06/10 (fora de tudo)                    999,00

    topo, pela data da compra (D-31), até o dia 16:
      gasto 80,00 (a compra de 25/09 é de setembro) · receitas 1000,00
      setembro até o dia 16: 70,00
    caixa, por competência (D-27):
      comprometido 100,00 · previsão = 100 + (180 - 100) / 16 * 31 = 255,00
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import TipoConta, TipoPagamento, TipoTransacao
from app.models import Categoria, Conta, FormaPagamento, Orcamento, Pessoa, Transacao
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
    forma: FormaPagamento | None = None,
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
            forma_pagamento_id=forma.id if forma else None,
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
        assert r.gasto == Decimal("80.00")
        assert r.receitas == Decimal("1000.00")
        assert r.sobra == Decimal("920.00")
        assert r.gasto_mes_anterior == Decimal("70.00")
        assert r.diferenca_mes_anterior == Decimal("10.00")

    def test_previsao_separa_o_comprometido(self, session: Session, mes: dict[str, Any]) -> None:
        previsao = _resumo(session).caixa.previsao
        assert previsao is not None
        assert previsao.comprometido == Decimal("100.00")
        assert previsao.valor == Decimal("255.00")

    def test_orcamento_total_e_faixa(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session)
        assert r.orcamento is not None
        assert r.orcamento.total == Decimal("555.00")
        assert r.orcamento.percentual_usado == 14  # 80 / 555, pela data da compra
        assert r.orcamento.faixa == "ok"

    def test_serie_acumulada_dia_a_dia(self, session: Session, mes: dict[str, Any]) -> None:
        pontos = _resumo(session).caixa.serie
        serie = {p.dia: p.acumulado for p in pontos}
        # D-27: o mês corrente traz todos os dias; `acumulado` para em hoje.
        assert list(serie) == list(range(1, 32))
        assert serie[1] == Decimal("100.00")  # sem cartão cadastrado: compra antiga no dia 1
        assert serie[4] == Decimal("100.00")
        assert serie[5] == Decimal("150.00")
        assert serie[16] == Decimal("180.00")
        assert serie[31] == Decimal("180.00")
        com_a_pagar = {p.dia: p.com_a_pagar for p in pontos}
        assert com_a_pagar[16] == Decimal("180.00")
        assert com_a_pagar[19] == Decimal("180.00")
        assert com_a_pagar[20] == Decimal("220.00")  # o Mercado de 20/10 ainda vai sair
        assert com_a_pagar[31] == Decimal("220.00")  # fecha no total da competência

    def test_quem_gastou(self, session: Session, mes: dict[str, Any]) -> None:
        pessoas = [(p.nome, p.valor, p.percentual) for p in _resumo(session).pessoas]
        assert pessoas == [
            ("Erik", Decimal("0"), 0),
            ("Laura", Decimal("50.00"), 63),
            ("Juntos", Decimal("30.00"), 38),
        ]

    def test_categorias_com_sem_categoria_no_fim(
        self, session: Session, mes: dict[str, Any]
    ) -> None:
        categorias = [
            (c.tipo, c.nome, c.valor, c.percentual, c.largura) for c in _resumo(session).categorias
        ]
        assert categorias == [
            ("categoria", "Restaurante", Decimal("50.00"), 63, 100),
            ("sem_categoria", "Sem categoria", Decimal("30.00"), 38, 60),
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

    @pytest.mark.parametrize(
        ("meta_cada", "faixa"),
        [
            ("50.01", "ok"),  # 80 / 100,02 = 79,98%
            ("50", "atencao"),  # 80 / 100 = 80%: a partir de 80%
            ("40.01", "atencao"),  # 80 / 80,02 = 99,98%
            ("40", "estourado"),  # 80 / 80 = 100%: a partir de 100%
        ],
    )
    def test_faixas_nos_limiares(
        self, session: Session, mes: dict[str, Any], meta_cada: str, faixa: str
    ) -> None:
        for o in session.query(Orcamento).all():
            o.valor_meta = Decimal(meta_cada)
        session.commit()
        assert _resumo(session).orcamento.faixa == faixa  # type: ignore[union-attr]


class TestOutrosMeses:
    def test_mes_passado_vale_inteiro_e_sem_previsao(
        self, session: Session, mes: dict[str, Any]
    ) -> None:
        r = _resumo(session, date(2026, 9, 1))
        assert (r.situacao, r.dia_referencia) == ("passado", 30)
        # Pela data da compra: a compra de 25/09 da fatura de outubro entra.
        assert r.gasto == Decimal("670.00")
        assert r.caixa.previsao is None
        assert r.orcamento is None
        assert len(r.caixa.serie) == 30

    def test_mes_futuro_vazio(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session, date(2026, 11, 1))
        assert (r.situacao, r.dia_referencia, r.tem_dados) == ("futuro", 0, False)
        assert r.gasto == Decimal("0")
        assert r.caixa.serie == [] and r.categorias == [] and r.avisos == []
        assert r.caixa.previsao is None
        assert all(p.valor == 0 and p.percentual == 0 for p in r.pessoas)

    def test_mes_sem_dados(self, session: Session, mes: dict[str, Any]) -> None:
        r = _resumo(session, date(2026, 6, 1))
        assert r.tem_dados is False
        assert r.gasto == Decimal("0")
        assert r.categorias == []


class TestPartesSomamOGasto:
    """D-31: quem gastou e por categoria somam o gasto do topo.

    Cartão que fecha dia 28: as compras de 27 e 28/09 são da fatura de
    outubro, as de 29/09 em diante da de novembro. O topo é pela data da
    compra, então a competência não pode puxar nada de um mês para o outro.
    """

    @pytest.fixture
    def virada(self, session: Session) -> None:
        erik, laura = Pessoa(nome="Erik"), Pessoa(nome="Laura")
        saiu = Pessoa(nome="Antiga", deleted_em=datetime(2026, 10, 1, tzinfo=UTC))
        cats = [Categoria(nome=f"Cat {n}", tipo=TipoTransacao.DESPESA) for n in range(7)]
        nubank = Conta(nome="Nubank", tipo=TipoConta.CARTAO)
        session.add_all([erik, laura, saiu, nubank, *cats])
        session.flush()
        cartao = FormaPagamento(
            apelido="Nubank",
            tipo=TipoPagamento.CREDITO,
            conta_id=nubank.id,
            dia_fechamento=28,
            dia_vencimento=5,
        )
        pix = FormaPagamento(apelido="Pix", tipo=TipoPagamento.PIX)
        session.add_all([cartao, pix])
        session.flush()
        out, nov, set_ = OUTUBRO, date(2026, 11, 1), date(2026, 9, 1)
        compras = [
            # setembro pela data: 205,00
            (date(2026, 9, 27), "10.00", out, cats[0], erik, cartao),
            (date(2026, 9, 28), "120.00", out, cats[1], laura, cartao),
            (date(2026, 9, 29), "60.00", nov, cats[2], None, cartao),
            (date(2026, 9, 30), "15.00", set_, cats[3], saiu, pix),
            # outubro pela data, até o dia 16: 124,00
            (date(2026, 10, 1), "45.00", nov, cats[4], erik, cartao),
            (date(2026, 10, 2), "33.00", nov, cats[5], None, cartao),
            (date(2026, 10, 3), "5.00", nov, cats[0], laura, cartao),
            (date(2026, 10, 4), "4.00", nov, cats[1], laura, cartao),
            (date(2026, 10, 5), "3.00", nov, cats[2], erik, cartao),
            (date(2026, 10, 6), "2.00", nov, cats[3], None, cartao),
            (date(2026, 10, 10), "7.00", out, cats[6], laura, pix),
            (date(2026, 10, 16), "25.00", nov, None, erik, cartao),
            # depois de hoje: fora
            (date(2026, 10, 17), "999.00", nov, cats[0], erik, cartao),
        ]
        for data, valor, comp, cat, pessoa, forma in compras:
            _t(session, data, valor, comp, categoria=cat, pessoa=pessoa, forma=forma)
        session.commit()

    @pytest.mark.parametrize(
        ("competencia", "gasto"),
        [(OUTUBRO, Decimal("124.00")), (date(2026, 9, 1), Decimal("205.00"))],
    )
    def test_pessoas_e_categorias_somam_o_gasto(
        self, session: Session, virada: None, competencia: date, gasto: Decimal
    ) -> None:
        r = _resumo(session, competencia)
        assert r.gasto == gasto
        assert sum((p.valor for p in r.pessoas), Decimal(0)) == gasto
        assert sum((c.valor for c in r.categorias), Decimal(0)) == gasto

    def test_outras_categorias_junta_o_resto(self, session: Session, virada: None) -> None:
        linhas = [(c.tipo, c.nome, c.valor) for c in _resumo(session).categorias]
        assert linhas[-2:] == [
            ("outras", "Outras categorias", Decimal("5.00")),  # Cat 2 (3,00) + Cat 3 (2,00)
            ("sem_categoria", "Sem categoria", Decimal("25.00")),
        ]
        assert [t for t, _, _ in linhas].count("categoria") == 5

    def test_pessoa_removida_com_gasto_continua_na_conta(
        self, session: Session, virada: None
    ) -> None:
        nomes = [p.nome for p in _resumo(session, date(2026, 9, 1)).pessoas]
        assert "Antiga" in nomes
        assert "Antiga" not in [p.nome for p in _resumo(session).pessoas]

    def test_caixa_continua_por_competencia(self, session: Session, virada: None) -> None:
        # A fatura de outubro (27 e 28/09) é o degrau do caixa, não do topo.
        faturas = _resumo(session).caixa.faturas
        assert [(f.cartao, f.valor) for f in faturas] == [("Nubank", Decimal("130.00"))]


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
