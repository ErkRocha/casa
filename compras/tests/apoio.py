"""Atalhos dos testes da API."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

LAURA = {"X-Quem": "Laura"}
ERIK = {"X-Quem": "Erik"}


def adicionar(
    client: TestClient,
    nome: str | None = None,
    *,
    quem: dict[str, str] = LAURA,
    id_cliente: uuid.UUID | None = None,
    **campos: Any,
) -> Any:
    """POST /lista/itens; devolve a resposta inteira."""
    corpo: dict[str, Any] = {"id_cliente": str(id_cliente or uuid.uuid4()), **campos}
    if nome is not None:
        corpo["produto_nome"] = nome
    return client.post("/lista/itens", json=corpo, headers=quem)


def item(client: TestClient, nome: str, **kwargs: Any) -> dict[str, Any]:
    resposta = adicionar(client, nome, **kwargs)
    assert resposta.status_code in (200, 201), resposta.text
    return dict(resposta.json())


def produto_id(client: TestClient, nome: str) -> int:
    achados = client.get("/produtos", params={"busca": nome}).json()
    assert achados, f"produto {nome} não encontrado"
    return int(achados[0]["id"])


# --- Cardápio -----------------------------------------------------------------


def produto(
    client: TestClient,
    nome: str,
    unidade: str | None = "un",
    base: str | None = None,
    por_unidade: str | None = None,
) -> int:
    """Cria o produto (ou acha o que já existe) e acerta unidade e medidas."""
    resposta = client.post(
        "/produtos",
        json={"nome": nome, "unidade_padrao": unidade, "id_cliente": str(uuid.uuid4())},
        headers=LAURA,
    )
    if resposta.status_code == 409:
        id_ = int(resposta.json()["produto"]["id"])
    else:
        assert resposta.status_code == 201, resposta.text
        id_ = int(resposta.json()["id"])
    campos: dict[str, Any] = {"unidade_padrao": unidade}
    if base is not None:
        campos["medida_base"] = base
        campos["medida_por_unidade"] = por_unidade
    patch = client.patch(f"/produtos/{id_}", json=campos, headers=LAURA)
    assert patch.status_code == 200, patch.text
    return id_


def ingrediente(
    produto_id: int, quantidade: str | None, unidade: str, observacao: str | None = None
) -> dict[str, Any]:
    corpo: dict[str, Any] = {"produto_id": produto_id, "unidade": unidade}
    if quantidade is not None:
        corpo["quantidade"] = quantidade
    if observacao is not None:
        corpo["observacao"] = observacao
    return corpo


def receita(
    client: TestClient,
    nome: str,
    ingredientes: list[dict[str, Any]],
    *,
    tipo: str = "almoco",
    rendimento: str = "1",
    **campos: Any,
) -> dict[str, Any]:
    corpo: dict[str, Any] = {
        "id_cliente": str(uuid.uuid4()),
        "nome": nome,
        "tipo": tipo,
        "rendimento_porcoes": rendimento,
        "ingredientes": ingredientes,
        **campos,
    }
    resposta = client.post("/receitas", json=corpo, headers=LAURA)
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())
