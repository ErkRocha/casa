"""Router da sincronização com a Pluggy (D-22). Só leitura."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.sincronizacao import EstadoSincronizacao
from app.services.sincronizacao import SincronizacaoService

router = APIRouter(prefix="/sincronizacao", tags=["sincronização"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/estado", response_model=EstadoSincronizacao)
def estado(session: SessionDep) -> Any:
    """Última atualização dos bancos e se ela roda sozinha."""
    return SincronizacaoService(session).estado()
