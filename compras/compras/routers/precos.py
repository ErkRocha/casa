"""Histórico de preço por produto e mercado."""

from typing import Annotated, Any

from fastapi import APIRouter, Query

from compras.deps import SessionDep
from compras.schemas import PrecoLinha
from compras.services.precos import PrecoService

router = APIRouter(prefix="/precos", tags=["preços"])


@router.get("", response_model=list[PrecoLinha])
def listar(
    session: SessionDep,
    produto_id: int | None = None,
    mercado_id: int | None = None,
    limite: Annotated[int, Query(ge=1, le=500)] = 100,
) -> Any:
    """Último preço, mínimo, máximo, média e quantas compras, por produto,
    mercado e unidade, a partir dos itens de nota associados. Unidades
    diferentes (KG e UN) ficam em linhas separadas."""
    return PrecoService(session).listar(produto_id, mercado_id, limite)
