"""Passos do roteiro marcados como feitos (D-30)."""

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.apoio import ERIK, LAURA, pessoa, receita, refeicao, semana

SEG = "2026-11-16"


@pytest.fixture
def cenario(client: TestClient) -> dict[str, Any]:
    """Uma semana com um frango que se prepara no domingo (a sessão da semana)."""
    pessoa(client, "Laura", "1")
    frango = receita(
        client,
        "Frango assado",
        [],
        tempo_preparo_min=90,
        pode_antecipar=True,
        dura_dias=3,
        pode_congelar=True,
        rendimento="2",
    )
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-16", "almoco", frango["id"])
    roteiro = client.get(f"/semanas/{s['id']}/preparo").json()
    return {
        "semana": s["id"],
        "receita": frango["id"],
        "sessao": roteiro["sessoes"][0]["sessao_id"],
    }


def _url(c: dict[str, Any], receita_id: int | None = None, sessao_id: int | None = None) -> str:
    return f"/sessoes/{sessao_id or c['sessao']}/passos/{receita_id or c['receita']}/feito"


def _marcar(client: TestClient, c: dict[str, Any], quem: dict[str, str] = LAURA, **kw: Any) -> Any:
    return client.put(_url(c, **kw), json={"id_cliente": str(uuid.uuid4())}, headers=quem)


def _passo(client: TestClient, c: dict[str, Any]) -> dict[str, Any]:
    roteiro = client.get(f"/semanas/{c['semana']}/preparo").json()
    return dict(roteiro["sessoes"][0]["passos"][0])


def test_sem_marcar_o_passo_vem_com_feito_nulo_e_a_sessao_com_id(
    client: TestClient, cenario: dict[str, Any]
) -> None:
    roteiro = client.get(f"/semanas/{cenario['semana']}/preparo").json()
    assert roteiro["sessoes"][0]["sessao_id"] == cenario["sessao"]
    assert roteiro["sessoes"][0]["passos"][0]["feito"] is None


def test_marcar_aparece_no_roteiro_com_por_e_em(
    client: TestClient, cenario: dict[str, Any]
) -> None:
    id_cliente = str(uuid.uuid4())
    r = client.put(_url(cenario), json={"id_cliente": id_cliente}, headers=LAURA)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["sessao_id"] == cenario["sessao"] and corpo["receita_id"] == cenario["receita"]
    assert corpo["feito_por"] == "Laura" and corpo["feito_em"] is not None
    assert corpo["id_cliente"] == id_cliente and corpo["deleted_em"] is None

    feito = _passo(client, cenario)["feito"]
    assert feito == {"por": "Laura", "em": corpo["feito_em"]}


def test_marcar_de_novo_mantem_o_primeiro(client: TestClient, cenario: dict[str, Any]) -> None:
    primeiro = _marcar(client, cenario, LAURA).json()
    r = _marcar(client, cenario, ERIK)  # outro celular, outro id_cliente
    assert r.status_code == 200
    assert r.json()["id"] == primeiro["id"] and r.json()["feito_por"] == "Laura"
    assert r.json()["feito_em"] == primeiro["feito_em"]
    assert _passo(client, cenario)["feito"]["por"] == "Laura"


def test_mesmo_id_cliente_repetido_devolve_200(client: TestClient, cenario: dict[str, Any]) -> None:
    corpo = {"id_cliente": str(uuid.uuid4())}
    primeira = client.put(_url(cenario), json=corpo, headers=LAURA)
    segunda = client.put(_url(cenario), json=corpo, headers=LAURA)
    assert (primeira.status_code, segunda.status_code) == (201, 200)
    assert segunda.json() == primeira.json()


def test_desfazer_some_do_roteiro_e_duas_vezes_e_ok(
    client: TestClient, cenario: dict[str, Any]
) -> None:
    _marcar(client, cenario)
    r = client.delete(_url(cenario), headers=ERIK)
    assert r.status_code == 200
    assert r.json()["deleted_em"] is not None and r.json()["feito_por"] == "Laura"
    assert _passo(client, cenario)["feito"] is None

    de_novo = client.delete(_url(cenario), headers=ERIK)
    assert de_novo.status_code == 200 and de_novo.json() is None
    assert _passo(client, cenario)["feito"] is None


def test_desfazer_o_que_nunca_foi_feito_e_ok(client: TestClient, cenario: dict[str, Any]) -> None:
    r = client.delete(_url(cenario), headers=LAURA)
    assert r.status_code == 200 and r.json() is None


def test_marcar_de_novo_depois_de_desfazer(client: TestClient, cenario: dict[str, Any]) -> None:
    primeiro = _marcar(client, cenario, LAURA).json()
    client.delete(_url(cenario), headers=LAURA)
    segundo = _marcar(client, cenario, ERIK)  # id_cliente novo: outra linha viva
    assert segundo.status_code == 201, segundo.text
    assert segundo.json()["id"] != primeiro["id"] and segundo.json()["feito_por"] == "Erik"
    assert _passo(client, cenario)["feito"]["por"] == "Erik"


def test_reenviar_o_id_cliente_de_um_passo_desfeito_marca_de_novo(
    client: TestClient, cenario: dict[str, Any]
) -> None:
    corpo = {"id_cliente": str(uuid.uuid4())}
    primeiro = client.put(_url(cenario), json=corpo, headers=LAURA).json()
    client.delete(_url(cenario), headers=LAURA)
    de_novo = client.put(_url(cenario), json=corpo, headers=ERIK)
    assert de_novo.status_code == 201
    assert de_novo.json()["id"] == primeiro["id"] and de_novo.json()["deleted_em"] is None
    assert _passo(client, cenario)["feito"]["por"] == "Erik"


def test_unique_parcial_so_uma_linha_viva_por_sessao_e_receita(
    client: TestClient, cenario: dict[str, Any], session: Session
) -> None:
    _marcar(client, cenario)
    client.delete(_url(cenario), headers=LAURA)
    _marcar(client, cenario)
    client.delete(_url(cenario), headers=LAURA)
    _marcar(client, cenario)
    session.rollback()
    vivas, todas = session.execute(
        text(
            "SELECT count(*) FILTER (WHERE deleted_em IS NULL), count(*) FROM compras.passos_feitos"
        )
    ).one()
    assert (vivas, todas) == (1, 3)


def test_aparece_no_mudancas_ao_marcar_e_ao_desfazer(
    client: TestClient, cenario: dict[str, Any]
) -> None:
    cursor = client.get("/lista").json()["cursor"]
    marcado = _marcar(client, cenario, LAURA).json()

    corpo = client.get("/mudancas", params={"desde": cursor}).json()
    assert [p["id"] for p in corpo["passos_feitos"]] == [marcado["id"]]
    linha = corpo["passos_feitos"][0]
    assert linha["sessao_id"] == cenario["sessao"] and linha["receita_id"] == cenario["receita"]
    assert linha["feito_por"] == "Laura" and linha["deleted_em"] is None

    client.delete(_url(cenario), headers=ERIK)
    corpo = client.get("/mudancas", params={"desde": corpo["cursor"]}).json()
    # Com a folga de 30 s a linha volta; o que vale é a versão mais nova.
    linha = next(p for p in corpo["passos_feitos"] if p["id"] == marcado["id"])
    assert linha["deleted_em"] is not None
    assert linha["atualizado_em"] >= marcado["atualizado_em"]


def test_mudancas_sem_cursor_recarrega_com_a_lista_vazia(client: TestClient) -> None:
    corpo = client.get("/mudancas").json()
    assert corpo["recarregar"] is True and corpo["passos_feitos"] == []


def test_sessao_ou_receita_inexistente_da_404(client: TestClient, cenario: dict[str, Any]) -> None:
    assert _marcar(client, cenario, sessao_id=9999).status_code == 404
    assert _marcar(client, cenario, receita_id=9999).status_code == 404
    client.delete(f"/sessoes/{cenario['sessao']}", headers=LAURA)
    assert _marcar(client, cenario).status_code == 404  # sessão apagada
    assert client.get("/mudancas", params={"desde": "2000-01-01T00:00:00Z"}).status_code == 200


def test_marcar_exige_quem_e_o_corpo(client: TestClient, cenario: dict[str, Any]) -> None:
    sem_quem = client.put(_url(cenario), json={"id_cliente": str(uuid.uuid4())})
    assert sem_quem.status_code == 400
    assert client.put(_url(cenario), json={}, headers=LAURA).status_code == 422


def test_id_cliente_de_outro_passo_da_409(client: TestClient, cenario: dict[str, Any]) -> None:
    outra = receita(client, "Arroz", [], pode_antecipar=True, dura_dias=3)
    corpo = {"id_cliente": str(uuid.uuid4())}
    assert client.put(_url(cenario), json=corpo, headers=LAURA).status_code == 201
    r = client.put(_url(cenario, receita_id=outra["id"]), json=corpo, headers=LAURA)
    assert r.status_code == 409
