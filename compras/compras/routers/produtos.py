"""Produtos canônicos ("leite integral 1L")."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from compras.deps import QuemDep, SessionDep
from compras.schemas import ProdutoAtualizar, ProdutoCriar, ProdutoLeitura
from compras.services.produtos import ProdutoService

router = APIRouter(prefix="/produtos", tags=["produtos"])


@router.get("", response_model=list[ProdutoLeitura])
def buscar(
    session: SessionDep,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Any:
    """Para o campo de adicionar: contém o texto (sem caixa nem acento); quem
    começa com ele primeiro, depois os mais comprados."""
    return [ProdutoLeitura.de(p) for p in ProdutoService(session).buscar(busca, limite)]


@router.post(
    "",
    response_model=ProdutoLeitura,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reenvio do mesmo `id_cliente`: o produto que já existe"}},
)
def criar(payload: ProdutoCriar, response: Response, session: SessionDep, _quem: QuemDep) -> Any:
    produto, criado = ProdutoService(session).criar(
        payload.nome, payload.id_cliente, payload.secao_id, payload.unidade_padrao
    )
    session.commit()
    if not criado:
        response.status_code = status.HTTP_200_OK
    return ProdutoLeitura.de(produto)


@router.patch("/{id_}", response_model=ProdutoLeitura)
def atualizar(id_: int, payload: ProdutoAtualizar, session: SessionDep, _quem: QuemDep) -> Any:
    produto = ProdutoService(session).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return ProdutoLeitura.de(produto)


@router.delete("/{id_}", response_model=ProdutoLeitura)
def remover(id_: int, session: SessionDep, _quem: QuemDep) -> Any:
    """Soft delete, e para de acompanhar na despensa. 409 se está na lista."""
    produto = ProdutoService(session).remover(id_)
    session.commit()
    return ProdutoLeitura.de(produto)
