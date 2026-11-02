"""Identidade pelo Tailscale (roadmap, Lista de compras, 3).

Com `Tailscale-User-Login` (posto pelo `tailscale serve`), o "quem" vem da
tailnet e o `X-Quem` do aparelho é ignorado. Sem ele, vale o `X-Quem`.
"""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

LOGIN = "laura.exemplo@example.com"
#: Nome com acento, como o Tailscale manda: RFC 2047 "Q".
NOME_RFC2047 = "=?utf-8?q?La=C3=BAra_Exemplo?="


def _tailscale(login: str = LOGIN, nome: str | None = NOME_RFC2047, **extra: str) -> dict[str, str]:
    cabecalhos = {"Tailscale-User-Login": login, **extra}
    if nome is not None:
        cabecalhos["Tailscale-User-Name"] = nome
    return cabecalhos


def _adicionar(client: TestClient, nome: str, headers: dict[str, str]) -> dict[str, object]:
    r = client.post(
        "/lista/itens",
        json={"id_cliente": str(uuid.uuid4()), "produto_nome": nome},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


# --- sem Tailscale ------------------------------------------------------------------


def test_eu_sem_nada_pede_para_perguntar(client: TestClient) -> None:
    assert client.get("/eu").json() == {
        "quem": None,
        "origem": None,
        "login": None,
        "cadastrado": False,
    }


def test_eu_com_x_quem_e_do_aparelho(client: TestClient) -> None:
    eu = client.get("/eu", headers={"X-Quem": "Laura"}).json()
    assert (eu["quem"], eu["origem"]) == ("Laura", "aparelho")


def test_escrita_sem_ninguem_e_recusada(client: TestClient) -> None:
    r = client.post("/lista/itens", json={"id_cliente": str(uuid.uuid4()), "produto_nome": "Pão"})
    assert r.status_code == 400


# --- com Tailscale -------------------------------------------------------------------


def test_eu_pelo_tailscale_decodifica_o_nome(client: TestClient) -> None:
    eu = client.get("/eu", headers=_tailscale()).json()
    assert eu == {
        "quem": "Laúra Exemplo",
        "origem": "tailscale",
        "login": LOGIN,
        "cadastrado": False,
    }


def test_sem_nome_do_tailscale_vale_o_login(client: TestClient) -> None:
    eu = client.get("/eu", headers=_tailscale(nome=None)).json()
    assert eu["quem"] == LOGIN


def test_x_quem_forjado_e_ignorado_com_identidade_do_tailscale(
    client: TestClient, session: Session
) -> None:
    item = _adicionar(client, "Pão", _tailscale(**{"X-Quem": "Intruso"}))
    assert item["adicionado_por"] == "Laúra Exemplo"
    autores = session.execute(
        text("SELECT DISTINCT autor FROM compras.auditoria WHERE tabela = 'itens_lista'")
    ).scalars()
    assert list(autores) == ["Laúra Exemplo"]


def test_pelo_tailscale_nao_precisa_de_x_quem(client: TestClient) -> None:
    item = _adicionar(client, "Leite", _tailscale())
    assert item["adicionado_por"] == "Laúra Exemplo"


def test_login_cadastrado_usa_o_nome_cadastrado(client: TestClient) -> None:
    r = client.post(
        "/identidades", json={"login": "  Laura.Exemplo@Example.com ", "nome": "Laura"},
        headers={"X-Quem": "Erik"},
    )  # fmt: skip
    assert r.status_code == 201, r.text
    assert r.json()["login"] == LOGIN

    # A caixa do login que o Tailscale manda não importa.
    eu = client.get("/eu", headers=_tailscale(login=LOGIN.upper())).json()
    assert (eu["quem"], eu["cadastrado"]) == ("Laura", True)

    comprado = _adicionar(client, "Café", _tailscale(**{"X-Quem": "Outra"}))
    r = client.post(f"/lista/itens/{comprado['id']}/comprar", headers=_tailscale())
    assert r.json()["comprado_por"] == "Laura"
    assert r.json()["adicionado_por"] == "Laura"


def test_login_duplicado_editar_e_remover(client: TestClient) -> None:
    erik = {"X-Quem": "Erik"}
    criada = client.post("/identidades", json={"login": LOGIN, "nome": "Laura"}, headers=erik)
    assert criada.status_code == 201
    repetida = client.post("/identidades", json={"login": LOGIN, "nome": "L"}, headers=erik)
    assert repetida.status_code == 409

    id_ = criada.json()["id"]
    r = client.patch(f"/identidades/{id_}", json={"nome": "Laurinha"}, headers=erik)
    assert r.json()["nome"] == "Laurinha"
    assert client.get("/eu", headers=_tailscale()).json()["quem"] == "Laurinha"

    assert client.delete(f"/identidades/{id_}", headers=erik).status_code == 200
    assert client.get("/identidades").json() == []
    # Sem cadastro, volta ao nome do Tailscale.
    assert client.get("/eu", headers=_tailscale()).json()["quem"] == "Laúra Exemplo"


def test_cadastrar_exige_quem(client: TestClient) -> None:
    r = client.post("/identidades", json={"login": LOGIN, "nome": "Laura"})
    assert r.status_code == 400
