"""Despesa lançada pela nota (D-33): migration 0010, leituras para o `compras`,
a sync que a põe na revisão e o "juntar" que fica com a transação do banco."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import StatusItem, TipoPagamento, TipoTransacao
from app.models import (
    Categoria,
    FormaPagamento,
    ImportacaoItem,
    PluggyPendente,
    Transacao,
)
from tests.test_sync_pluggy import CARTAO, LeitorFalso, _itens, _sync, _tx
from tests.test_sync_pluggy import cenario as cenario  # fixture reaproveitada

DIA = date(2025, 5, 1)


def _lancada(session: Session, forma_id: int, categoria_id: int | None = None) -> Transacao:
    t = Transacao(
        data=DIA,
        competencia=date(2025, 5, 1),
        valor=Decimal("100.00"),
        tipo=TipoTransacao.DESPESA,
        descricao="Mercado Exemplo",
        forma_pagamento_id=forma_id,
        categoria_id=categoria_id,
        lancada_pela_nota=True,
    )
    session.add(t)
    session.commit()
    return t


def _leitor_com_compra(valor: str = "100.00") -> LeitorFalso:
    leitor = LeitorFalso()
    leitor.transacoes[CARTAO] = [_tx("k1", CARTAO, "2025-05-01T15:00:00Z", valor)]
    return leitor


# --- migration e escrita -----------------------------------------------------------


def test_transacao_nasce_sem_marca_e_aceita_a_marca(client: TestClient, session: Session) -> None:
    comum = Transacao(
        data=DIA,
        competencia=DIA,
        valor=Decimal("1.00"),
        tipo=TipoTransacao.DESPESA,
        descricao="x",
    )
    session.add(comum)
    session.commit()
    assert comum.lancada_pela_nota is False
    assert comum.substituida_por_id is None

    r = client.post(
        "/transacoes",
        json={
            "data": "2025-05-01",
            "valor": "12.34",
            "descricao": "Nota",
            "lancada_pela_nota": True,
        },
    )
    assert r.status_code == 201, r.text
    marcada = session.get(Transacao, r.json()["id"])
    assert marcada is not None and marcada.lancada_pela_nota is True


# --- leituras para o compras -------------------------------------------------------


def test_candidatas_nota_traz_forma_e_marca(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    t = _lancada(session, cenario["credito"].id)
    session.add(
        Transacao(
            data=date(2025, 5, 9),
            competencia=DIA,
            valor=Decimal("100.00"),
            tipo=TipoTransacao.DESPESA,
            descricao="Fora da janela",
        )
    )
    session.add(
        Transacao(
            data=DIA,
            competencia=DIA,
            valor=Decimal("100.01"),
            tipo=TipoTransacao.DESPESA,
            descricao="Valor diferente",
        )
    )
    session.commit()

    r = client.get(
        "/transacoes/candidatas-nota",
        params={"data_inicio": "2025-04-30", "data_fim": "2025-05-02", "valor": "100.00"},
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert [c["id"] for c in corpo] == [t.id]
    assert corpo[0]["lancada_pela_nota"] is True
    assert corpo[0]["forma_pagamento_tipo"] == "credito"
    assert corpo[0]["forma_pagamento_apelido"] == cenario["credito"].apelido


def test_pendentes_do_cartao_por_data_e_valor(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    for id_, dia, valor in [("p1", DIA, "55.00"), ("p2", date(2025, 5, 9), "55.00")]:
        session.add(
            PluggyPendente(
                id_externo=id_,
                conta_pluggy_id=cenario["mapa_cartao"].id,
                forma_pagamento_id=cenario["credito"].id,
                data=dia,
                valor=Decimal(valor),
                descricao="MERCADO",
            )
        )
    session.commit()
    r = client.get(
        "/transacoes/pendentes-cartao",
        params={"data_inicio": "2025-04-30", "data_fim": "2025-05-02", "valor": "55.00"},
    )
    assert [p["id_externo"] for p in r.json()] == ["p1"]
    assert r.json()[0]["forma_pagamento_tipo"] == "credito"
    assert client.get("/transacoes/pendentes-cartao/p2").json()["data"] == "2025-05-09"
    assert client.get("/transacoes/pendentes-cartao/sumiu").status_code == 404


def test_transacao_pelo_id_da_pluggy(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    assert client.get("/transacoes/por-pluggy/k1").status_code == 404
    leitor = _leitor_com_compra()
    session.add(
        Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    )  # sem regra: a compra segue para a revisão
    session.commit()
    _sync(session, leitor)
    item = _itens(session)[0]
    t = Transacao(
        data=DIA,
        competencia=DIA,
        valor=Decimal("100.00"),
        tipo=TipoTransacao.DESPESA,
        descricao="x",
    )
    session.add(t)
    session.flush()
    item.transacao_id = t.id
    item.status = StatusItem.APROVADO
    session.commit()
    r = client.get("/transacoes/por-pluggy/k1")
    assert r.status_code == 200 and r.json()["transacao_id"] == t.id


def test_situacao_de_transacao_apagada_mostra_a_substituta(
    client: TestClient, session: Session
) -> None:
    nova = Transacao(
        data=DIA, competencia=DIA, valor=Decimal("1"), tipo=TipoTransacao.DESPESA, descricao="a"
    )
    session.add(nova)
    session.flush()
    velha = Transacao(
        data=DIA,
        competencia=DIA,
        valor=Decimal("1"),
        tipo=TipoTransacao.DESPESA,
        descricao="b",
        descricao_original="B",
        substituida_por_id=nova.id,
    )
    session.add(velha)
    session.commit()
    assert client.delete(f"/transacoes/{velha.id}").status_code == 200

    assert client.get(f"/transacoes/{velha.id}").status_code == 404
    r = client.get(f"/transacoes/{velha.id}/situacao")
    assert r.json() == {"id": velha.id, "viva": False, "substituida_por_id": nova.id}
    assert client.get(f"/transacoes/{nova.id}/situacao").json()["viva"] is True
    assert client.get("/transacoes/999999/situacao").status_code == 404


# --- sync ---------------------------------------------------------------------------


def test_sync_nao_promove_o_que_repete_a_lancada_pela_nota(
    session: Session, cenario: dict[str, Any]
) -> None:
    _lancada(session, cenario["credito"].id)
    resultado = _sync(session, _leitor_com_compra())

    assert resultado.promovidos == 0
    assert resultado.na_revisao["possivel_duplicata"] == 1
    item = _itens(session)[0]
    assert item.status is StatusItem.PENDENTE
    assert item.observacao is not None
    assert "Possível duplicata: despesa lançada pela nota" in item.observacao


def test_sync_valor_diferente_nao_e_marcado(session: Session, cenario: dict[str, Any]) -> None:
    _lancada(session, cenario["credito"].id)
    _sync(session, _leitor_com_compra("100.50"))
    assert "lançada pela nota" not in (_itens(session)[0].observacao or "")


def test_sync_lancada_apagada_nao_conta(session: Session, cenario: dict[str, Any]) -> None:
    from sqlalchemy import func

    t = _lancada(session, cenario["credito"].id)
    t.deleted_em = func.now()
    session.commit()
    _sync(session, _leitor_com_compra())
    assert "lançada pela nota" not in (_itens(session)[0].observacao or "")


def test_sync_forma_diferente_nao_e_marcado(session: Session, cenario: dict[str, Any]) -> None:
    outra = FormaPagamento(apelido="Cartão da Laura", tipo=TipoPagamento.CREDITO)
    session.add(outra)
    session.flush()
    _lancada(session, outra.id)
    _sync(session, _leitor_com_compra())
    assert "lançada pela nota" not in (_itens(session)[0].observacao or "")


# --- revisão ------------------------------------------------------------------------


def _preparar(session: Session, cenario: dict[str, Any]) -> tuple[Transacao, ImportacaoItem]:
    categoria = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add(categoria)
    session.flush()
    lancada = _lancada(session, cenario["credito"].id, categoria.id)
    _sync(session, _leitor_com_compra())
    return lancada, _itens(session)[0]


def test_revisao_lista_a_lancada_no_grupo(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    lancada, item = _preparar(session, cenario)
    grupos = client.get("/revisar/duplicatas").json()
    assert len(grupos) == 1
    assert [x["transacao_id"] for x in grupos[0]["lancadas_pela_nota"]] == [lancada.id]
    assert grupos[0]["itens"][0]["id"] == item.id


def test_juntar_fica_com_a_do_banco_e_aponta_a_substituta(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    lancada, item = _preparar(session, cenario)
    r = client.post(
        "/revisar/duplicatas/resolver",
        json={"manter_ids": [item.id], "juntar_lancada_pela_nota_id": lancada.id},
    )
    assert r.status_code == 200, r.text
    assert r.json()["aprovados"] == 1

    session.expire_all()
    item = session.get(ImportacaoItem, item.id)  # type: ignore[assignment]
    assert item.status is StatusItem.APROVADO and item.transacao_id is not None
    nova = session.get(Transacao, item.transacao_id)
    antiga = session.get(Transacao, lancada.id)
    assert nova is not None and antiga is not None
    assert nova.deleted_em is None and nova.lancada_pela_nota is False
    assert nova.categoria_id == lancada.categoria_id  # herdada da lançada
    assert antiga.deleted_em is not None
    assert antiga.substituida_por_id == nova.id
    situacao = client.get(f"/transacoes/{antiga.id}/situacao").json()
    assert situacao["viva"] is False and situacao["substituida_por_id"] == nova.id


def test_sao_duas_mantem_as_duas(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    lancada, item = _preparar(session, cenario)
    r = client.post("/revisar/duplicatas/resolver", json={"manter_ids": [item.id]})
    assert r.status_code == 200, r.text

    session.expire_all()
    assert session.get(Transacao, lancada.id).deleted_em is None  # type: ignore[union-attr]
    assert session.get(Transacao, lancada.id).substituida_por_id is None  # type: ignore[union-attr]
    item = session.get(ImportacaoItem, item.id)  # type: ignore[assignment]
    # A nota de duplicata sai; o item segue pelo outro motivo que já tinha
    # (competência estimada), como em toda duplicata resolvida.
    assert "lançada pela nota" not in (item.observacao or "")
    assert item.status is StatusItem.PENDENTE
    assert [
        t.id for t in session.scalars(select(Transacao).where(Transacao.deleted_em.is_(None)))
    ] == [lancada.id]


def test_juntar_recusa_transacao_que_nao_e_lancada_pela_nota(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    _, item = _preparar(session, cenario)
    comum = Transacao(
        data=DIA, competencia=DIA, valor=Decimal("100"), tipo=TipoTransacao.DESPESA, descricao="z"
    )
    session.add(comum)
    session.commit()
    r = client.post(
        "/revisar/duplicatas/resolver",
        json={"manter_ids": [item.id], "juntar_lancada_pela_nota_id": comum.id},
    )
    assert r.status_code == 422, r.text
