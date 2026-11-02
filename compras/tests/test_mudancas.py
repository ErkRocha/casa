"""`GET /mudancas?desde=`: inclusões, mudanças e remoções desde o cursor."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from compras.config import get_settings
from tests.apoio import ERIK, LAURA, item, produto_id

pytestmark = pytest.mark.usefixtures("semeado")


@pytest.fixture
def sem_folga() -> Iterator[None]:
    """Folga zero, para provar o corte exato do cursor."""
    cfg = get_settings()
    antes = cfg.folga_mudancas_s
    cfg.folga_mudancas_s = 0
    yield
    cfg.folga_mudancas_s = antes


def _mudancas(client: TestClient, desde: str) -> dict:  # type: ignore[type-arg]
    resposta = client.get("/mudancas", params={"desde": desde})
    assert resposta.status_code == 200, resposta.text
    return dict(resposta.json())


@pytest.mark.usefixtures("sem_folga")
def test_desde_devolve_inclusoes_mudancas_e_remocoes(client: TestClient) -> None:
    antigo = item(client, "Tomate")  # antes do cursor: não volta
    a_comprar = item(client, "Banana")
    a_tirar = item(client, "Cebola")
    cursor = client.get("/lista").json()["cursor"]

    incluido = item(client, "Leite integral 1L", quem=ERIK)
    client.post(f"/lista/itens/{a_comprar['id']}/comprar", headers=LAURA)
    client.delete(f"/lista/itens/{a_tirar['id']}", headers=ERIK)

    corpo = _mudancas(client, cursor)
    assert corpo["recarregar"] is False
    por_id = {i["id"]: i for i in corpo["itens"]}
    assert set(por_id) == {incluido["id"], a_comprar["id"], a_tirar["id"]}
    assert antigo["id"] not in por_id
    assert por_id[incluido["id"]]["situacao"] == "pendente"
    assert por_id[a_comprar["id"]]["situacao"] == "comprado"
    assert por_id[a_comprar["id"]]["comprado_por"] == "Laura"
    assert por_id[a_tirar["id"]]["deleted_em"] is not None

    # O cursor novo não devolve nada do que já veio.
    assert _mudancas(client, corpo["cursor"])["itens"] == []


@pytest.mark.usefixtures("sem_folga")
def test_desde_traz_despensa_produtos_e_secoes(client: TestClient) -> None:
    cursor = client.get("/lista").json()["cursor"]
    leite = produto_id(client, "leite")
    client.put(f"/despensa/{leite}", json={"estado": "acabando"}, headers=LAURA)
    client.patch(f"/produtos/{leite}", json={"unidade_padrao": "cx"}, headers=LAURA)
    secao = client.post("/secoes", json={"nome": "Pet"}, headers=ERIK).json()

    corpo = _mudancas(client, cursor)
    assert [d["produto_id"] for d in corpo["despensa"]] == [leite]
    assert [p["id"] for p in corpo["produtos"]] == [leite]
    assert corpo["produtos"][0]["unidade_padrao"] == "cx"
    # A seção nova e a "Sem seção", que andou uma posição para trás.
    assert {s["nome"] for s in corpo["secoes"]} == {"Pet", "Sem seção"}
    assert secao["id"] in {s["id"] for s in corpo["secoes"]}


def test_folga_devolve_o_que_mudou_pouco_antes_do_cursor(client: TestClient) -> None:
    """Com a folga padrão (30 s), uma escrita carimbada um instante antes do
    cursor volta. É o caso da escrita que confirmou depois da leitura."""
    escrito = item(client, "Banana")
    cursor = client.get("/lista").json()["cursor"]
    corpo = _mudancas(client, cursor)
    assert [i["id"] for i in corpo["itens"]] == [escrito["id"]]


def test_sem_cursor_ou_com_cursor_velho_pede_recarga(client: TestClient) -> None:
    item(client, "Banana")
    sem = client.get("/mudancas").json()
    assert sem["recarregar"] is True
    assert sem["itens"] == []
    assert sem["cursor"]

    velho = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    assert _mudancas(client, velho)["recarregar"] is True
