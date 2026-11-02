"""O ciclo lista e despensa: comprou -> tem; acabou -> lista; acabando -> sugestão."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.models import Despensa, ItemLista
from tests.apoio import ERIK, LAURA, item, produto_id

pytestmark = pytest.mark.usefixtures("semeado")


def _estado(client: TestClient, produto: int) -> str | None:
    for linha in client.get("/despensa").json():
        if linha["produto_id"] == produto:
            return str(linha["estado"])
    return None


def test_comprou_a_despensa_passa_a_tem(client: TestClient) -> None:
    leite = produto_id(client, "leite")
    client.put(f"/despensa/{leite}", json={"estado": "acabando"}, headers=LAURA)
    criado = item(client, "Leite integral 1L")

    client.post(f"/lista/itens/{criado['id']}/comprar", headers=ERIK)

    linha = next(d for d in client.get("/despensa").json() if d["produto_id"] == leite)
    assert linha["estado"] == "tem"
    assert linha["estado_por"] == "Erik"


def test_comprar_produto_nao_acompanhado_nao_cria_despensa(
    client: TestClient, session: Session
) -> None:
    criado = item(client, "Banana")
    client.post(f"/lista/itens/{criado['id']}/comprar", headers=LAURA)
    assert session.scalar(select(func.count()).select_from(Despensa)) == 0


def test_acabou_volta_para_a_lista(client: TestClient) -> None:
    cafe = produto_id(client, "café")
    client.put(f"/despensa/{cafe}", json={"estado": "tem"}, headers=LAURA)

    resposta = client.put(f"/despensa/{cafe}", json={"estado": "acabou"}, headers=ERIK)

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["despensa"]["estado"] == "acabou"
    novo = corpo["item_criado"]
    assert novo["produto_id"] == cafe
    assert novo["situacao"] == "pendente"
    assert novo["origem"] == "despensa"
    assert novo["adicionado_por"] == "Erik"
    assert [i["id"] for i in client.get("/lista").json()["itens"]] == [novo["id"]]


def test_acabou_com_o_produto_ja_na_lista_nao_duplica(client: TestClient, session: Session) -> None:
    cafe = produto_id(client, "café")
    ja_na_lista = item(client, "Café 500g")
    resposta = client.put(f"/despensa/{cafe}", json={"estado": "acabou"}, headers=LAURA)
    assert resposta.json()["item_criado"] is None
    de_novo = client.put(f"/despensa/{cafe}", json={"estado": "acabou"}, headers=LAURA)
    assert de_novo.json()["item_criado"] is None
    assert session.scalar(select(func.count()).select_from(ItemLista)) == 1
    assert client.get("/lista").json()["itens"][0]["id"] == ja_na_lista["id"]


def test_acabando_nao_entra_sozinho_na_lista(client: TestClient, session: Session) -> None:
    arroz = produto_id(client, "arroz")
    resposta = client.put(f"/despensa/{arroz}", json={"estado": "acabando"}, headers=LAURA)

    assert resposta.json()["item_criado"] is None
    assert session.scalar(select(func.count()).select_from(ItemLista)) == 0
    lista = client.get("/lista").json()
    assert lista["itens"] == []
    # Aparece como sugestão, e sai dela quando alguém põe na lista.
    assert [s["produto_id"] for s in lista["sugestoes"]] == [arroz]
    item(client, "Arroz 5kg")
    assert client.get("/lista").json()["sugestoes"] == []


def test_desfazer_a_compra_volta_a_acabou(client: TestClient) -> None:
    leite = produto_id(client, "leite")
    client.put(f"/despensa/{leite}", json={"estado": "acabou"}, headers=LAURA)
    pendente = client.get("/lista").json()["itens"][0]
    client.post(f"/lista/itens/{pendente['id']}/comprar", headers=LAURA)
    assert _estado(client, leite) == "tem"

    client.post(f"/lista/itens/{pendente['id']}/desfazer", headers=LAURA)
    assert _estado(client, leite) == "acabou"


def test_tirar_da_lista_nao_mexe_na_despensa(client: TestClient) -> None:
    leite = produto_id(client, "leite")
    client.put(f"/despensa/{leite}", json={"estado": "acabou"}, headers=LAURA)
    pendente = client.get("/lista").json()["itens"][0]
    client.delete(f"/lista/itens/{pendente['id']}", headers=ERIK)
    assert _estado(client, leite) == "acabou"


def test_filtro_por_estado_e_parar_de_acompanhar(client: TestClient) -> None:
    leite, cafe = produto_id(client, "leite"), produto_id(client, "café")
    client.put(f"/despensa/{leite}", json={"estado": "tem"}, headers=LAURA)
    client.put(f"/despensa/{cafe}", json={"estado": "acabando"}, headers=LAURA)

    acabando = client.get("/despensa", params={"estado": "acabando"}).json()
    assert [d["produto_id"] for d in acabando] == [cafe]

    removida = client.delete(f"/despensa/{cafe}", headers=LAURA)
    assert removida.status_code == 200
    assert removida.json()["deleted_em"] is not None
    assert [d["produto_id"] for d in client.get("/despensa").json()] == [leite]
    assert client.delete(f"/despensa/{cafe}", headers=LAURA).status_code == 404


def test_produto_inexistente_na_despensa_e_404(client: TestClient) -> None:
    assert client.put("/despensa/999", json={"estado": "tem"}, headers=LAURA).status_code == 404
