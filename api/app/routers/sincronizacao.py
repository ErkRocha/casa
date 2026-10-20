"""Router da sincronização com a Pluggy (D-22). Só leitura."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.sincronizacao import EstadoSincronizacao, LinhaHistorico
from app.services.sincronizacao import SincronizacaoService

router = APIRouter(prefix="/sincronizacao", tags=["sincronização"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/estado", response_model=EstadoSincronizacao)
def estado(session: SessionDep) -> Any:
    """Última atualização dos bancos e se ela roda sozinha."""
    return SincronizacaoService(session).estado()


@router.get("/historico", response_model=list[LinhaHistorico])
def historico(session: SessionDep, dias: Annotated[int, Query(ge=1, le=366)] = 30) -> Any:
    """As importações do período: o que entrou, o que espera revisão, e se
    dá para desfazer (`POST /importacoes/{id}/desfazer`)."""
    return SincronizacaoService(session).historico(dias)
