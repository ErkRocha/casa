"""Routers dos cadastros do v1.

Router valida entrada e chama service; nenhuma regra de negócio mora aqui
(regra 12).

Os cinco verbos são iguais em todo cadastro, então saem de uma fábrica. Sem
`from __future__ import annotations` neste módulo de propósito: o FastAPI
precisa que a anotação do corpo seja a classe de verdade, não uma string.
"""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas import cadastros as s
from app.schemas.common import OkResponse, Page, Paginacao, paginacao
from app.services.base import CrudService
from app.services.cadastros import (
    CategoriaService,
    ContaService,
    FormaPagamentoService,
    LocalService,
    OrcamentoService,
    PessoaService,
)

SessionDep = Annotated[Session, Depends(get_session)]
PaginacaoDep = Annotated[Paginacao, Depends(paginacao)]


def crud_router(
    *,
    prefix: str,
    tag: str,
    service_cls: type[CrudService[Any]],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.get("", response_model=Page[read_schema])  # type: ignore[valid-type]
    def listar(
        session: SessionDep,
        pag: PaginacaoDep,
        apenas_ativos: bool = False,
    ) -> Any:
        itens, total = service_cls(session).listar(pag, apenas_ativos=apenas_ativos)
        return Page(items=itens, total=total, limit=pag.limit, offset=pag.offset)

    @router.get("/{id_}", response_model=read_schema)
    def obter(id_: int, session: SessionDep) -> Any:
        return service_cls(session).get(id_)

    @router.post("", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    def criar(payload: create_schema, session: SessionDep) -> Any:  # type: ignore[valid-type]
        # `payload` é sempre um BaseModel em runtime — o tipo concreto vem do
        # parâmetro da fábrica, que o mypy não consegue estreitar.
        obj = service_cls(session).criar(cast(BaseModel, payload).model_dump())
        session.commit()
        return obj

    @router.patch("/{id_}", response_model=read_schema)
    def atualizar(id_: int, payload: update_schema, session: SessionDep) -> Any:  # type: ignore[valid-type]
        # `exclude_unset`: só o que o cliente mandou de fato. Sem isso, um
        # PATCH parcial zeraria todo campo omitido.
        dados = cast(BaseModel, payload).model_dump(exclude_unset=True)
        obj = service_cls(session).atualizar(id_, dados)
        session.commit()
        return obj

    @router.delete("/{id_}", response_model=OkResponse)
    def remover(id_: int, session: SessionDep) -> Any:
        """Soft delete: grava `deleted_em`. Nunca apaga a linha (regra 2)."""
        service_cls(session).remover(id_)
        session.commit()
        return OkResponse()

    return router


pessoas_router = crud_router(
    prefix="/pessoas",
    tag="pessoas",
    service_cls=PessoaService,
    create_schema=s.PessoaCreate,
    update_schema=s.PessoaUpdate,
    read_schema=s.PessoaRead,
)

contas_router = crud_router(
    prefix="/contas",
    tag="contas",
    service_cls=ContaService,
    create_schema=s.ContaCreate,
    update_schema=s.ContaUpdate,
    read_schema=s.ContaRead,
)

categorias_router = crud_router(
    prefix="/categorias",
    tag="categorias",
    service_cls=CategoriaService,
    create_schema=s.CategoriaCreate,
    update_schema=s.CategoriaUpdate,
    read_schema=s.CategoriaRead,
)

formas_pagamento_router = crud_router(
    prefix="/formas-pagamento",
    tag="formas de pagamento",
    service_cls=FormaPagamentoService,
    create_schema=s.FormaPagamentoCreate,
    update_schema=s.FormaPagamentoUpdate,
    read_schema=s.FormaPagamentoRead,
)

locais_router = crud_router(
    prefix="/locais",
    tag="locais",
    service_cls=LocalService,
    create_schema=s.LocalCreate,
    update_schema=s.LocalUpdate,
    read_schema=s.LocalRead,
)

orcamentos_router = crud_router(
    prefix="/orcamentos",
    tag="orçamentos",
    service_cls=OrcamentoService,
    create_schema=s.OrcamentoCreate,
    update_schema=s.OrcamentoUpdate,
    read_schema=s.OrcamentoRead,
)


# --------------------------------------------------------------------------
# Endpoints específicos
# --------------------------------------------------------------------------


@categorias_router.get(
    "/arvore/completa",
    response_model=list[s.CategoriaArvore],
    tags=["categorias"],
)
def arvore_categorias(session: SessionDep) -> Any:
    """Raízes com as filhas embutidas.

    É o que a tela de filtro e o select de categoria consomem — evita o front
    remontar a hierarquia a cada render.
    """
    return [
        s.CategoriaArvore(
            **s.CategoriaRead.model_validate(raiz).model_dump(),
            subcategorias=[s.CategoriaRead.model_validate(f) for f in filhas],
        )
        for raiz, filhas in CategoriaService(session).arvore()
    ]
