"""Tela Análises (D-22): meses, categorias, mudanças e orçamento, do banco.

"Hoje" é 16/10/2026. Os números fecham à mão:

                          ago      set      out (corrente)
    Mercado (Erik)        100      300       60
    Restaurante (Laura)    50       50        —
    Casa (conjunto)       200      200      120
    sem categoria           —       30        —
    receita (conjunto)   1000     1000      500
    transferência           —        —      999  (fora de tudo)

    despesas              350      580      180
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
from app.services.analises import AnalisesService

HOJE = date(2026, 10, 16)
AGO, SET, OUT = date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)


@pytest.fixture
def dados(session: Session) -> dict[str, Any]:
    laura, erik = Pessoa(nome="Laura"), Pessoa(nome="Erik")
    alimentacao = Categoria(nome="Alimentação", tipo=TipoTransacao.DESPESA)
    casa = Categoria(nome="Casa", tipo=TipoTransacao.DESPESA)
    lazer = Categoria(nome="Lazer", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    a = Conta(nome="Banco A", tipo=TipoConta.CORRENTE)
    b = Conta(nome="Banco B", tipo=TipoConta.CORRENTE)
    session.add_all([laura, erik, alimentacao, casa, lazer, salario, a, b])
    session.flush()
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA, categoria_pai_id=alimentacao.id)
    restaurante = Categoria(
        nome="Restaurante", tipo=TipoTransacao.DESPESA, categoria_pai_id=alimentacao.id
    )
    session.add_all([mercado, restaurante])
    session.flush()

    n = 0

    def lancar(
        competencia: date,
        valor: str,
        categoria: Categoria | None,
        pessoa: Pessoa | None = None,
        tipo: TipoTransacao = TipoTransacao.DESPESA,
        **campos: Any,
    ) -> None:
        nonlocal n
        n += 1
        session.add(
            Transacao(
                data=competencia.replace(day=5),
                competencia=competencia,
                valor=Decimal(valor),
                tipo=tipo,
                descricao=f"lançamento {n}",
                descricao_original=f"LANCAMENTO {n}",
                categoria_id=categoria.id if categoria else None,
                pessoa_id=pessoa.id if pessoa else None,
                **campos,
            )
        )

    for mes, valor_mercado in ((AGO, "100"), (SET, "300")):
        lancar(mes, valor_mercado, mercado, erik)
        lancar(mes, "50", restaurante, laura)
        lancar(mes, "200", casa)
        lancar(mes, "1000", salario, tipo=TipoTransacao.RECEITA)
    lancar(SET, "30", None)
    lancar(OUT, "60", mercado, erik)
    lancar(OUT, "120", casa)
    lancar(OUT, "500", salario, tipo=TipoTransacao.RECEITA)
    lancar(
        OUT,
        "999",
        None,
        tipo=TipoTransacao.TRANSFERENCIA,
        conta_origem_id=a.id,
        conta_destino_id=b.id,
    )

    session.add_all(
        [
            # 60 de 65 = 92,3%: "perto". 120 de 100: estourado. 0 de 100: ok.
            Orcamento(categoria_id=alimentacao.id, competencia=OUT, valor_meta=Decimal("65")),
            Orcamento(categoria_id=casa.id, competencia=OUT, valor_meta=Decimal("100")),
            Orcamento(categoria_id=lazer.id, competencia=OUT, valor_meta=Decimal("100")),
            # Meta de outro mês não entra.
            Orcamento(categoria_id=casa.id, competencia=SET, valor_meta=Decimal("1")),
        ]
    )
    session.commit()
    return {"erik": erik, "mercado": mercado, "alimentacao": alimentacao, "casa": casa}


def _resumo(session: Session, periodo: Any, pessoa: str | None = None) -> Any:
    return AnalisesService(session, hoje=HOJE).resumo(periodo, pessoa)


def test_tres_meses(session: Session, dados: dict[str, Any]) -> None:
    r = _resumo(session, "3m")
    assert (r.inicio, r.fim, r.dia_referencia, r.dias_no_mes) == (AGO, OUT, 16, 31)
    assert [(m.competencia, m.despesas, m.receitas, m.em_curso) for m in r.meses] == [
        (AGO, Decimal("350"), Decimal("1000"), False),
        (SET, Decimal("580"), Decimal("1000"), False),
        (OUT, Decimal("180"), Decimal("500"), True),
    ]
    assert r.meses_fechados == 2
    assert r.base_categorias == "media_mensal"
    assert r.media_mensal == Decimal("465.00")
    assert r.mes_mais_caro is not None
    assert (r.mes_mais_caro.competencia, r.mes_mais_caro.despesas) == (SET, Decimal("580"))


def test_categorias_pela_media_dos_meses_fechados(session: Session, dados: dict[str, Any]) -> None:
    categorias = _resumo(session, "3m").categorias
    assert [(c.nome, c.valor) for c in categorias] == [
        ("Alimentação", Decimal("250.00")),
        ("Casa", Decimal("200.00")),
        ("Sem categoria", Decimal("15.00")),
    ]
    assert categorias[0].categoria_id == dados["alimentacao"].id
    assert [(s.nome, s.valor) for s in categorias[0].subcategorias] == [
        ("Mercado", Decimal("200.00")),
        ("Restaurante", Decimal("50.00")),
    ]
    assert categorias[1].subcategorias == []
    assert categorias[2].categoria_id is None


def test_o_que_mais_mudou(session: Session, dados: dict[str, Any]) -> None:
    mudancas = _resumo(session, "3m").mudancas
    assert mudancas is not None
    assert (mudancas.referencia, mudancas.meses_base) == (SET, 1)
    primeira = mudancas.linhas[0]
    assert (primeira.nome, primeira.valor, primeira.media, primeira.variacao) == (
        "Mercado",
        Decimal("300"),
        Decimal("100.00"),
        200,
    )
    # Sem categoria não entra: não há o que comparar.
    assert {linha.nome for linha in mudancas.linhas} == {"Mercado", "Restaurante", "Casa"}


def test_orcamento_nas_faixas_do_readme(session: Session, dados: dict[str, Any]) -> None:
    orcamento = _resumo(session, "3m").orcamento
    assert [
        (o.nome, o.gasto, o.meta, o.percentual, o.faixa, o.largura, o.excesso) for o in orcamento
    ] == [
        ("Casa", Decimal("120"), Decimal("100"), 120, "estourado", 100, Decimal("20")),
        ("Alimentação", Decimal("60"), Decimal("65"), 92, "perto", 92, None),
        ("Lazer", Decimal("0"), Decimal("100"), 0, "ok", 0, None),
    ]


def test_pessoa_vale_para_a_tela_inteira(session: Session, dados: dict[str, Any]) -> None:
    r = _resumo(session, "3m", str(dados["erik"].id))
    assert [(m.despesas, m.receitas) for m in r.meses] == [
        (Decimal("100"), Decimal("0")),
        (Decimal("300"), Decimal("0")),
        (Decimal("60"), Decimal("0")),
    ]
    assert [(c.nome, c.valor) for c in r.categorias] == [("Alimentação", Decimal("200.00"))]
    # O gasto é o da pessoa; a meta continua a da casa.
    casa = next(o for o in r.orcamento if o.nome == "Casa")
    assert (casa.gasto, casa.meta) == (Decimal("0"), Decimal("100"))

    juntos = _resumo(session, "3m", "conjunto")
    assert [m.receitas for m in juntos.meses] == [Decimal("1000"), Decimal("1000"), Decimal("500")]


def test_doze_meses(session: Session, dados: dict[str, Any]) -> None:
    r = _resumo(session, "12m")
    assert r.inicio == date(2025, 11, 1)
    assert len(r.meses) == 12
    assert r.meses_fechados == 11
    # Mês sem gasto conta como zero na média: (350 + 580) / 11.
    assert r.media_mensal == Decimal("84.55")
    assert r.mudancas is not None
    assert (r.mudancas.referencia, r.mudancas.meses_base) == (SET, 10)


def test_este_mes(session: Session, dados: dict[str, Any]) -> None:
    r = _resumo(session, "mes")
    assert [m.competencia for m in r.meses] == [OUT]
    assert r.meses_fechados == 0
    assert r.base_categorias == "mes"
    assert r.media_mensal is None
    assert r.mudancas is None
    assert [(c.nome, c.valor) for c in r.categorias] == [
        ("Casa", Decimal("120.00")),
        ("Alimentação", Decimal("60.00")),
    ]


def test_sem_dados(session: Session) -> None:
    r = _resumo(session, "3m")
    assert [m.despesas for m in r.meses] == [Decimal("0")] * 3
    assert r.media_mensal == Decimal("0.00")
    assert r.mes_mais_caro is None
    assert r.categorias == []
    assert r.mudancas is not None and r.mudancas.linhas == []
    assert r.orcamento == []


def test_endpoint_valida_periodo_e_pessoa(client: TestClient) -> None:
    resposta = client.get("/analytics/analises", params={"periodo": "3m"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["periodo"] == "3m"
    assert client.get("/analytics/analises", params={"periodo": "6m"}).status_code == 422
    assert client.get("/analytics/analises", params={"pessoa": "erik"}).status_code == 422
    assert client.get("/analytics/analises", params={"pessoa": "conjunto"}).status_code == 200
