"""Comprado, aguardando nota: a lista, "fechar" e a pergunta dos 7 dias (D-33)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.apoio import ERIK, LAURA, produto
from tests.apoio_compra import acompanhar, comprar, despensa, na_lista, recuar_compra


def _aguardando(client: TestClient, session: Session, nome: str, dias: int = 0) -> dict[str, Any]:
    pid = produto(client, nome)
    item = na_lista(client, pid)
    comprar(client, item["id"])
    if dias:
        recuar_compra(session, item["id"], dias)
    return item


def test_lista_separa_aguardando_nota_e_pergunta_so_depois_de_7_dias(
    client: TestClient, session: Session
) -> None:
    recente = _aguardando(client, session, "Leite")
    seis = _aguardando(client, session, "Sal", dias=6)
    velho = _aguardando(client, session, "Arroz", dias=8)

    lista = client.get("/lista").json()
    assert {i["id"] for i in lista["aguardando_nota"]} == {recente["id"], seis["id"], velho["id"]}
    assert [i["id"] for i in lista["perguntas"]] == [velho["id"]]
    assert lista["aguardando_nota"][0]["fechamento"] is None

    # Dispensar: a pergunta não volta, o item continua aguardando nota.
    r = client.post(f"/lista/itens/{velho['id']}/dispensar-pergunta", headers=ERIK)
    assert r.status_code == 200, r.text
    assert r.json()["perguntado_em"] is not None and r.json()["fechamento"] is None
    primeira = r.json()["perguntado_em"]
    de_novo = client.post(f"/lista/itens/{velho['id']}/dispensar-pergunta", headers=LAURA)
    assert de_novo.status_code == 200 and de_novo.json()["perguntado_em"] == primeira
    lista = client.get("/lista").json()
    assert lista["perguntas"] == []
    assert velho["id"] in {i["id"] for i in lista["aguardando_nota"]}


def test_fechar_sem_nota(client: TestClient, session: Session) -> None:
    item = _aguardando(client, session, "Leite")
    r = client.post(f"/lista/itens/{item['id']}/fechar", json={"como": "sem_nota"}, headers=ERIK)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["situacao"] == "comprado" and corpo["fechamento"] == "sem_nota"
    assert corpo["fechado_por"] == "Erik" and corpo["fechado_em"] is not None
    assert client.get("/lista").json()["aguardando_nota"] == []
    outra = client.post(
        f"/lista/itens/{item['id']}/fechar", json={"como": "sem_nota"}, headers=ERIK
    )
    assert outra.status_code == 409
    assert (
        client.post(f"/lista/itens/{item['id']}/dispensar-pergunta", headers=ERIK).status_code
        == 409
    )
    assert (
        client.post(
            f"/lista/itens/{item['id']}/fechar", json={"como": "talvez"}, headers=ERIK
        ).status_code
        == 422
    )


def test_nao_comprei_volta_a_pendente_e_a_despensa_a_acabou(
    client: TestClient, session: Session
) -> None:
    item = _aguardando(client, session, "Leite", dias=8)
    acompanhar(client, session, item["produto_id"], "tem")
    r = client.post(f"/lista/itens/{item['id']}/fechar", json={"como": "nao_comprei"}, headers=ERIK)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["situacao"] == "pendente" and corpo["fechamento"] is None
    assert corpo["comprado_em"] is None and corpo["perguntado_em"] is None
    assert corpo["deleted_em"] is None
    assert despensa(client, item["produto_id"]) == "acabou"
    assert client.get("/lista").json()["aguardando_nota"] == []


def test_nao_comprei_com_outro_pendente_do_produto_remove_o_item(
    client: TestClient, session: Session
) -> None:
    item = _aguardando(client, session, "Leite", dias=8)
    outro = na_lista(client, item["produto_id"])
    r = client.post(f"/lista/itens/{item['id']}/fechar", json={"como": "nao_comprei"}, headers=ERIK)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["deleted_em"] is not None and corpo["fechamento"] == "nao_comprei"
    assert corpo["fechado_por"] == "Erik"
    lista = client.get("/lista").json()
    assert [i["id"] for i in lista["itens"]] == [outro["id"]]
    assert lista["aguardando_nota"] == []


def test_mudancas_expoe_o_fechamento(client: TestClient, session: Session) -> None:
    cursor = client.get("/lista").json()["cursor"]
    item = _aguardando(client, session, "Leite")
    client.post(f"/lista/itens/{item['id']}/fechar", json={"como": "sem_nota"}, headers=ERIK)
    itens = client.get("/mudancas", params={"desde": cursor}).json()["itens"]
    achado = next(i for i in itens if i["id"] == item["id"])
    assert achado["fechamento"] == "sem_nota" and achado["fechado_por"] == "Erik"
