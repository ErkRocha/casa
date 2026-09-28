"""Schemas compartilhados."""

from typing import Annotated, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Toda listagem é paginada (CLAUDE.md § Convenções)."""

    items: list[T]
    total: int
    limit: int
    offset: int


class Paginacao(BaseModel):
    limit: Annotated[int, Field(ge=1, le=200)] = 50
    offset: Annotated[int, Field(ge=0)] = 0


def paginacao(
    limit: Annotated[int, Query(ge=1, le=200, description="Itens por página")] = 50,
    offset: Annotated[int, Query(ge=0, description="Deslocamento")] = 0,
) -> Paginacao:
    """Dependência de paginação para os routers."""
    return Paginacao(limit=limit, offset=offset)


class OkResponse(BaseModel):
    ok: bool = True


class LoteResponse(BaseModel):
    """Resultado de ação em lote na tela de transações."""

    afetadas: int
