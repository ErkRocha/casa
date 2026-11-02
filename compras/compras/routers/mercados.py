"""Mercados, criados pela leitura das notas (pelo CNPJ)."""

from typing import Any

from fastapi import APIRouter

from compras.deps import QuemDep, SessionDep
from compras.schemas import MercadoAtualizar, MercadoLeitura
from compras.services.mercados import MercadoService

router = APIRouter(prefix="/mercados", tags=["mercados"])


@router.get("", response_model=list[MercadoLeitura])
def listar(session: SessionDep) -> Any:
    return [MercadoLeitura.de(m) for m in MercadoService(session).listar()]


@router.patch("/{id_}", response_model=MercadoLeitura)
def atualizar(id_: int, payload: MercadoAtualizar, session: SessionDep, _quem: QuemDep) -> Any:
    """O nome como o casal chama o mercado ("Zaffari da Ipiranga")."""
    mercado = MercadoService(session).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    session.refresh(mercado)
    return MercadoLeitura.de(mercado)
