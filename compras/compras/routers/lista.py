"""A lista da casa."""

from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from compras.config import get_settings
from compras.deps import QuemDep, SessionDep
from compras.schemas import (
    DespensaLeitura,
    HistoricoPagina,
    ItemAtualizar,
    ItemCriar,
    ItemLeitura,
    ItemResposta,
    ListaResposta,
)
from compras.services.despensa import DespensaService
from compras.services.lista import ListaService
from compras.services.mudancas import agora

router = APIRouter(prefix="/lista", tags=["lista"])


@router.get("", response_model=ListaResposta)
def listar(
    session: SessionDep,
    comprados_desde: Annotated[
        datetime | None,
        Query(description="Comprados a mostrar; padrão: as últimas 6 horas"),
    ] = None,
) -> Any:
    """Pendentes e comprados recentes, na ordem do percurso, com as sugestões
    da despensa ("acabando") e o cursor para `/mudancas`."""
    cursor = agora(session)
    desde = comprados_desde or cursor - timedelta(hours=get_settings().comprados_recentes_h)
    return ListaResposta(
        cursor=cursor,
        itens=[ItemLeitura.de(i) for i in ListaService(session).listar(desde)],
        sugestoes=[DespensaLeitura.de(d) for d in DespensaService(session).sugestoes()],
    )


@router.get("/historico", response_model=HistoricoPagina)
def historico(
    session: SessionDep,
    produto_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Comprados, mais recentes primeiro."""
    itens, total = ListaService(session).historico(produto_id, limit, offset)
    return HistoricoPagina(
        items=[ItemLeitura.de(i) for i in itens], total=total, limit=limit, offset=offset
    )


@router.post(
    "/itens",
    response_model=ItemResposta,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {
            "description": (
                "Nada criado: reenvio do mesmo `id_cliente`, ou o produto já estava "
                "pendente (`ja_estava: true`, sem somar quantidade)"
            )
        }
    },
)
def adicionar(payload: ItemCriar, response: Response, session: SessionDep, quem: QuemDep) -> Any:
    item, criado, ja_estava = ListaService(session, quem).criar(
        payload.id_cliente,
        produto_id=payload.produto_id,
        produto_nome=payload.produto_nome,
        quantidade=payload.quantidade,
        unidade=payload.unidade,
        observacao=payload.observacao,
        origem=payload.origem,
    )
    session.commit()
    if not criado:
        response.status_code = status.HTTP_200_OK
    return ItemResposta(**ItemLeitura.de(item).model_dump(), ja_estava=ja_estava)


@router.patch("/itens/{id_}", response_model=ItemLeitura)
def atualizar(id_: int, payload: ItemAtualizar, session: SessionDep, quem: QuemDep) -> Any:
    """Quantidade, unidade, observação. A última escrita vence (api.md)."""
    item = ListaService(session, quem).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return ItemLeitura.de(item)


@router.post("/itens/{id_}/comprar", response_model=ItemLeitura)
def comprar(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Marca comprado; na despensa, o produto passa a "tem". Repetir não muda nada."""
    item = ListaService(session, quem).comprar(id_)
    session.commit()
    return ItemLeitura.de(item)


@router.post("/itens/{id_}/desfazer", response_model=ItemLeitura)
def desfazer(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Volta a pendente; na despensa, o produto volta a "acabou"."""
    item = ListaService(session, quem).desfazer(id_)
    session.commit()
    return ItemLeitura.de(item)


@router.delete("/itens/{id_}", response_model=ItemLeitura)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Tira da lista (soft delete). A despensa não muda."""
    item = ListaService(session, quem).remover(id_)
    session.commit()
    return ItemLeitura.de(item)
