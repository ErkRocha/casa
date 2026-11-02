"""Seções (ordem do percurso) e produtos (busca, criação idempotente)."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.apoio import ERIK, LAURA, item, produto_id

pytestmark = pytest.mark.usefixtures("semeado")


# --- produtos ---------------------------------------------------------------


def test_busca_sem_caixa_nem_acento(client: TestClient) -> None:
    assert [p["nome"] for p in client.get("/produtos", params={"busca": "acucar"}).json()] == [
        "Açúcar 1kg"
    ]
    assert client.get("/produtos", params={"busca": "PÃO"}).json()[0]["nome"] == "Pão francês"


def test_busca_quem_comeca_vem_antes_depois_os_mais_comprados(client: TestClient) -> None:
    # "Água sanitária" e "Água mineral" começam com "agua"; "Sabão" não.
    nomes = [p["nome"] for p in client.get("/produtos", params={"busca": "agua"}).json()]
    assert nomes == ["Água mineral 1,5L", "Água sanitária 2L"]

    for _ in range(2):
        comprado = item(client, "Água sanitária 2L")
        client.post(f"/lista/itens/{comprado['id']}/comprar", headers=LAURA)
    nomes = [p["nome"] for p in client.get("/produtos", params={"busca": "agua"}).json()]
    assert nomes == ["Água sanitária 2L", "Água mineral 1,5L"]


def test_busca_trata_curinga_como_texto(client: TestClient) -> None:
    assert client.get("/produtos", params={"busca": "%"}).json() == []


def test_criar_produto_e_idempotente_pelo_id_cliente(client: TestClient) -> None:
    pedido = str(uuid.uuid4())
    corpo = {"nome": "Granola", "id_cliente": pedido, "unidade_padrao": "pct"}
    primeiro = client.post("/produtos", json=corpo, headers=LAURA)
    reenvio = client.post("/produtos", json=corpo, headers=LAURA)
    assert primeiro.status_code == 201
    assert primeiro.json()["secao_nome"] == "Sem seção"
    assert reenvio.status_code == 200
    assert reenvio.json()["id"] == primeiro.json()["id"]


def test_produto_com_nome_repetido_e_409_com_o_existente(client: TestClient) -> None:
    corpo = {"nome": "leite integral 1l", "id_cliente": str(uuid.uuid4())}
    resposta = client.post("/produtos", json=corpo, headers=LAURA)
    assert resposta.status_code == 409
    assert resposta.json()["produto"]["nome"] == "Leite integral 1L"


def test_mudar_produto_de_secao_e_renomear(client: TestClient) -> None:
    secoes = {s["nome"]: s["id"] for s in client.get("/secoes").json()}
    criado = client.post(
        "/produtos", json={"nome": "Ração", "id_cliente": str(uuid.uuid4())}, headers=ERIK
    ).json()
    alterado = client.patch(
        f"/produtos/{criado['id']}",
        json={"nome": "Ração do gato 1kg", "secao_id": secoes["Mercearia"]},
        headers=ERIK,
    )
    assert alterado.status_code == 200
    assert alterado.json()["secao_nome"] == "Mercearia"
    assert (
        client.get("/produtos", params={"busca": "racao do gato"}).json()[0]["id"] == (criado["id"])
    )


def test_remover_produto_na_lista_e_409(client: TestClient) -> None:
    item(client, "Banana")
    banana = produto_id(client, "banana")
    assert client.delete(f"/produtos/{banana}", headers=LAURA).status_code == 409


def test_remover_produto_para_de_acompanhar_na_despensa(client: TestClient) -> None:
    sabonete = produto_id(client, "sabonete")
    client.put(f"/despensa/{sabonete}", json={"estado": "tem"}, headers=LAURA)
    assert client.delete(f"/produtos/{sabonete}", headers=LAURA).status_code == 200
    assert client.get("/despensa").json() == []
    assert client.get("/produtos", params={"busca": "sabonete"}).json() == []


# --- seções -----------------------------------------------------------------


def test_secao_nova_entra_antes_de_sem_secao(client: TestClient) -> None:
    resposta = client.post("/secoes", json={"nome": "Pet"}, headers=LAURA)
    assert resposta.status_code == 201
    nomes = [s["nome"] for s in client.get("/secoes").json()]
    assert nomes[-2:] == ["Pet", "Sem seção"]
    assert client.post("/secoes", json={"nome": "pet"}, headers=LAURA).status_code == 409


def test_reordenar_muda_a_ordem_da_lista(client: TestClient) -> None:
    item(client, "Banana")
    item(client, "Sabão em pó")
    secoes = client.get("/secoes").json()
    ids = [s["id"] for s in secoes]
    limpeza = next(s["id"] for s in secoes if s["nome"] == "Limpeza")
    nova = [limpeza, *(i for i in ids if i != limpeza)]

    resposta = client.put("/secoes/ordem", json={"ids": nova}, headers=ERIK)
    assert resposta.status_code == 200
    assert [s["id"] for s in resposta.json()] == nova
    assert [i["produto_nome"] for i in client.get("/lista").json()["itens"]] == [
        "Sabão em pó",
        "Banana",
    ]


def test_reordenar_exige_todas_as_secoes(client: TestClient) -> None:
    ids = [s["id"] for s in client.get("/secoes").json()]
    assert client.put("/secoes/ordem", json={"ids": ids[:-1]}, headers=ERIK).status_code == 422
    repetido = [ids[0], *ids[:-1]]
    assert client.put("/secoes/ordem", json={"ids": repetido}, headers=ERIK).status_code == 422


def test_remover_secao_leva_produtos_para_sem_secao(client: TestClient) -> None:
    secoes = {s["nome"]: s["id"] for s in client.get("/secoes").json()}
    assert client.delete(f"/secoes/{secoes['Congelados']}", headers=LAURA).status_code == 200
    assert "Congelados" not in [s["nome"] for s in client.get("/secoes").json()]

    criado = client.post(
        "/produtos",
        json={"nome": "Pizza congelada", "id_cliente": str(uuid.uuid4())},
        headers=LAURA,
    ).json()
    assert criado["secao_nome"] == "Sem seção"
    # Seção nova antes da remoção: os produtos dela vão para "Sem seção".
    pet = client.post("/secoes", json={"nome": "Pet"}, headers=LAURA).json()
    racao = client.post(
        "/produtos",
        json={"nome": "Ração", "secao_id": pet["id"], "id_cliente": str(uuid.uuid4())},
        headers=LAURA,
    ).json()
    client.delete(f"/secoes/{pet['id']}", headers=LAURA)
    busca = client.get("/produtos", params={"busca": "racao"}).json()
    assert busca[0]["id"] == racao["id"]
    assert busca[0]["secao_nome"] == "Sem seção"


def test_sem_secao_nao_se_remove_nem_renomeia(client: TestClient) -> None:
    sem = next(s for s in client.get("/secoes").json() if s["nome"] == "Sem seção")
    assert client.delete(f"/secoes/{sem['id']}", headers=LAURA).status_code == 422
    renomear = client.patch(f"/secoes/{sem['id']}", json={"nome": "Outros"}, headers=LAURA)
    assert renomear.status_code == 422
