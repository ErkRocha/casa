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
