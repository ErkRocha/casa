"""Semanas do cardápio, com as refeições e as sessões de preparo (D-30)."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import JSONResponse

from compras.deps import QuemDep, SessionDep
from compras.schemas_cardapio import (
    RefeicaoCriar,
    RefeicaoLeitura,
    SemanaCopiada,
    SemanaCopiar,
    SemanaCriar,
    SemanaDetalhe,
    SemanaResumo,
    SemanasPagina,
    SessaoCriar,
    SessaoLeitura,
)
from compras.services.preparo import SessaoService
from compras.services.refeicoes import RefeicaoService
from compras.services.semanas import SemanaService

router = APIRouter(prefix="/semanas", tags=["cardápio: semanas"])


@router.get("", response_model=SemanasPagina)
def listar(
    session: SessionDep,
    limite: Annotated[int, Query(ge=1, le=100)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Any:
    """As semanas, mais recentes primeiro, com quantas refeições cada uma tem."""
    itens, total = SemanaService(session).listar(limite, offset)
    return SemanasPagina(items=itens, total=total, limite=limite, offset=offset)


@router.get(
    "/{inicio}", response_model=SemanaDetalhe, responses={404: {"description": "Sem semana"}}
)
def ler(
    inicio: date,
    session: SessionDep,
    ingredientes: Annotated[
        bool,
        Query(description="Traz os ingredientes de cada receita (na semana passada, os de então)"),
    ] = False,
) -> Any:
    """A semana pela segunda-feira. Não existe: 404 com `{"existe": false}`, para a
    tela oferecer criar ou copiar. Data que não é segunda: 422."""
    servico = SemanaService(session)
    semana = servico.por_inicio(inicio)
    if semana is None:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"existe": False, "detail": f"semana {inicio.isoformat()} não existe"},
        )
    return servico.detalhe(semana, ingredientes)


@router.post(
    "",
    response_model=SemanaDetalhe,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "A semana já existia"}},
)
def criar(payload: SemanaCriar, response: Response, session: SessionDep, quem: QuemDep) -> Any:
    """Cria com a sessão de preparo do domingo anterior."""
    servico = SemanaService(session, quem)
    semana, criada = servico.criar(payload.inicio, payload.observacao)
    session.commit()
    if not criada:
        response.status_code = status.HTTP_200_OK
    return servico.detalhe(semana)


@router.post("/{id_}/copiar", response_model=SemanaCopiada, status_code=status.HTTP_201_CREATED)
def copiar(id_: int, payload: SemanaCopiar, session: SessionDep, quem: QuemDep) -> Any:
    """Copia refeições, pessoas, ajustes e sessões, deslocando as datas. Destino com
    refeição: 409. Receita apagada vira refeição sem receita, com aviso."""
    servico = SemanaService(session, quem)
    semana, avisos = servico.copiar(id_, payload.destino)
    session.commit()
    detalhe = servico.detalhe(semana)
    return SemanaCopiada(**detalhe.model_dump(), avisos=avisos)


@router.delete("/{id_}", response_model=SemanaResumo)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Soft delete da semana e das refeições. O que ela pôs na lista fica."""
    servico = SemanaService(session, quem)
    semana = servico.remover(id_)
    session.commit()
    return SemanaResumo(
        id=semana.id,
        criado_em=semana.criado_em,
        atualizado_em=semana.atualizado_em,
        deleted_em=semana.deleted_em,
        inicio=semana.inicio,
        observacao=semana.observacao,
        passada=False,
        refeicoes=0,
    )


@router.post(
    "/{id_}/refeicoes", response_model=RefeicaoLeitura, status_code=status.HTTP_201_CREATED
)
def criar_refeicao(id_: int, payload: RefeicaoCriar, session: SessionDep, quem: QuemDep) -> Any:
    """Sem `pessoas`: todas as vivas, com a porção padrão."""
    semana = SemanaService(session).get(id_)
    servico = RefeicaoService(session, quem)
    refeicao = servico.criar(semana, payload)
    session.commit()
    return servico.leitura(refeicao)


@router.post("/{id_}/sessoes", response_model=SessaoLeitura, status_code=status.HTTP_201_CREATED)
def criar_sessao(id_: int, payload: SessaoCriar, session: SessionDep, quem: QuemDep) -> Any:
    """De sábado anterior a domingo da semana."""
    semana = SemanaService(session).get(id_)
    sessao = SessaoService(session, quem).criar(semana, payload.data, payload.rotulo)
    session.commit()
    return SessaoLeitura.model_validate(sessao, from_attributes=True)
