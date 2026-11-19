"""Atalhos dos testes de lista, despensa e conferência (D-33)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.apoio import LAURA, adicionar


def na_lista(client: TestClient, pid: int, **campos: Any) -> dict[str, Any]:
    r = adicionar(client, None, produto_id=pid, **campos)
    assert r.status_code in (200, 201), r.text
    return dict(r.json())


def comprar(client: TestClient, item_id: int, quem: dict[str, str] = LAURA) -> dict[str, Any]:
    r = client.post(f"/lista/itens/{item_id}/comprar", headers=quem)
    assert r.status_code == 200, r.text
    return dict(r.json())


def despensa(client: TestClient, pid: int) -> str | None:
    for linha in client.get("/despensa").json():
        if linha["produto_id"] == pid:
            return str(linha["estado"])
    return None


def acompanhar(client: TestClient, session: Session, pid: int, estado: str) -> None:
    """Põe na despensa e recua o `estado_em`, para a nota poder ser mais nova que ele."""
    r = client.put(f"/despensa/{pid}", json={"estado": estado}, headers=LAURA)
    assert r.status_code == 200, r.text
    session.execute(
        text(
            "UPDATE compras.despensa SET estado_em = now() - interval '2 days' "
            "WHERE produto_id = :p"
        ),
        {"p": pid},
    )
    session.commit()


def recuar_compra(session: Session, item_id: int, dias: int) -> None:
    session.execute(
        text(
            "UPDATE compras.itens_lista SET comprado_em = now() - make_interval(days => :d) "
            "WHERE id = :i"
        ),
        {"d": dias, "i": item_id},
    )
    session.commit()
