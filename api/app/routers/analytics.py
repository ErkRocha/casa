"""Router de Analytics (fase 4).

Somente leitura. Todos os endpoints aceitam o mesmo conjunto de filtros da
tela de transações — é o que faz o gráfico responder ao filtro sem o front
recalcular nada.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.analytics import (
    AnalyticsResumo,
    Comparativo,
    ComposicaoCategoria,
    DivisaoPessoas,
    EvolucaoMensal,
    ProgressoOrcamento,
)
from app.schemas.transacoes import TransacaoFiltros, transacao_filtros
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_session)]
FiltrosDep = Annotated[TransacaoFiltros, Depends(transacao_filtros)]


@router.get("/resumo", response_model=AnalyticsResumo)
def resumo(
    session: SessionDep,
    filtros: FiltrosDep,
    categoria_pai_id: Annotated[
        int | None, Query(description="Drill-down da composição por categoria")
    ] = None,
) -> Any:
    """Os cinco painéis numa chamada — evita cinco round-trips na abertura."""
    return AnalyticsService(session).resumo(filtros, categoria_pai_id)


@router.get("/evolucao-mensal", response_model=EvolucaoMensal)
def evolucao_mensal(session: SessionDep, filtros: FiltrosDep) -> Any:
    """Gasto por mês, quebrado nos três baldes de pessoa."""
    return AnalyticsService(session).evolucao_mensal(filtros)


@router.get("/composicao-categoria", response_model=ComposicaoCategoria)
def composicao_categoria(
    session: SessionDep,
    filtros: FiltrosDep,
    categoria_pai_id: Annotated[int | None, Query()] = None,
) -> Any:
    """Composição do gasto por categoria.

    Sem `categoria_pai_id`, agrupa pelas raízes. Com ele, desce um nível — e a
    agregação do nível filho sai do banco, não de filtro no navegador (D-14).
    """
    return AnalyticsService(session).composicao_categoria(filtros, categoria_pai_id)


@router.get("/divisao-pessoas", response_model=DivisaoPessoas)
def divisao_pessoas(
    session: SessionDep,
    filtros: FiltrosDep,
    competencia: Annotated[date | None, Query()] = None,
) -> Any:
    """Quanto cada balde gastou no mês, com o mês anterior para o delta."""
    return AnalyticsService(session).divisao_pessoas(filtros, competencia)


@router.get("/orcamento", response_model=ProgressoOrcamento)
def orcamento(
    session: SessionDep,
    competencia: Annotated[date | None, Query()] = None,
) -> Any:
    """Meta contra realizado por categoria, de `vw_orcamento_mes`."""
    return AnalyticsService(session).orcamento(competencia)


@router.get("/comparativo", response_model=Comparativo)
def comparativo(session: SessionDep, filtros: FiltrosDep) -> Any:
    """Este mês, o anterior e a média da janela."""
    return AnalyticsService(session).comparativo(filtros)
