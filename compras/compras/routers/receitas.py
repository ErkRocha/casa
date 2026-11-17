"""Receitas do cardápio (D-30)."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from compras.deps import QuemDep, SessionDep
from compras.enums import TipoRefeicao
from compras.schemas_cardapio import (
    ReceitaCorpo,
    ReceitaCriar,
    ReceitaDetalhe,
    ReceitaResumo,
    ReceitasPagina,
)
from compras.services.receitas import ReceitaService

router = APIRouter(prefix="/receitas", tags=["cardápio: receitas"])


@router.get("", response_model=ReceitasPagina)
def listar(
    session: SessionDep,
    busca: Annotated[str | None, Query(max_length=120)] = None,
    tipo: TipoRefeicao | None = None,
    pode_antecipar: bool | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """Contém o texto no nome (sem caixa nem acento); quem começa com ele vem antes."""
    receitas, total = ReceitaService(session).listar(busca, tipo, pode_antecipar, limite, offset)
    return ReceitasPagina(
        items=[ReceitaResumo.model_validate(r, from_attributes=True) for r in receitas],
        total=total,
        limite=limite,
        offset=offset,
    )


@router.get("/{id_}", response_model=ReceitaDetalhe)
def ler(id_: int, session: SessionDep) -> Any:
    """A receita com os ingredientes na ordem e se cada um converte."""
    servico = ReceitaService(session)
    return servico.detalhe(servico.get(id_))


@router.post(
    "",
    response_model=ReceitaDetalhe,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Reenvio do mesmo `id_cliente`: a receita que já existe"}},
)
def criar(payload: ReceitaCriar, response: Response, session: SessionDep, quem: QuemDep) -> Any:
    servico = ReceitaService(session, quem)
    receita, criada = servico.criar(payload)
    session.commit()
    if not criada:
        response.status_code = status.HTTP_200_OK
    return servico.detalhe(receita)


@router.put("/{id_}", response_model=ReceitaDetalhe)
def substituir(id_: int, payload: ReceitaCorpo, session: SessionDep, quem: QuemDep) -> Any:
    """Substitui os campos e os ingredientes. Os antigos levam soft delete."""
    servico = ReceitaService(session, quem)
    receita = servico.substituir(id_, payload)
    session.commit()
    return servico.detalhe(receita)


@router.post("/{id_}/duplicar", response_model=ReceitaDetalhe, status_code=status.HTTP_201_CREATED)
def duplicar(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    servico = ReceitaService(session, quem)
    receita = servico.duplicar(id_)
    session.commit()
    return servico.detalhe(receita)


@router.delete("/{id_}", response_model=ReceitaResumo)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Soft delete. Usada em semana que não acabou: 409, com as semanas."""
    receita = ReceitaService(session, quem).remover(id_)
    session.commit()
    return ReceitaResumo.model_validate(receita, from_attributes=True)
