"""Despensa: o que tem em casa."""

from typing import Any

from fastapi import APIRouter

from compras.deps import QuemDep, SessionDep
from compras.enums import EstadoDespensa
from compras.schemas import DespensaDefinir, DespensaLeitura, DespensaResposta, ItemLeitura
from compras.services.despensa import DespensaService
from compras.services.lista import ListaService

router = APIRouter(prefix="/despensa", tags=["despensa"])


@router.get("", response_model=list[DespensaLeitura])
def listar(session: SessionDep, estado: EstadoDespensa | None = None) -> Any:
    """Produtos acompanhados, na ordem do percurso; filtro por estado no banco."""
    return [DespensaLeitura.de(d) for d in DespensaService(session).listar(estado)]


@router.put("/{produto_id}", response_model=DespensaResposta)
def definir(produto_id: int, payload: DespensaDefinir, session: SessionDep, quem: QuemDep) -> Any:
    """Muda o estado e começa a acompanhar, se não acompanhava.

    "acabou" põe o produto na lista (se não estiver) e devolve o item em
    `item_criado`. "acabando" não põe: aparece nas sugestões do `GET /lista`.
    """
    linha, item_id = DespensaService(session, quem).definir(produto_id, payload.estado)
    session.commit()
    item = ListaService(session).get(item_id) if item_id is not None else None
    return DespensaResposta(
        despensa=DespensaLeitura.de(linha),
        item_criado=ItemLeitura.de(item) if item is not None else None,
    )


@router.delete("/{produto_id}", response_model=DespensaLeitura)
def remover(produto_id: int, session: SessionDep, quem: QuemDep) -> Any:
    """Para de acompanhar o produto (soft delete)."""
    linha = DespensaService(session, quem).remover(produto_id)
    session.commit()
    return DespensaLeitura.de(linha)
