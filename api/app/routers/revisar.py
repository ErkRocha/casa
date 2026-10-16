"""Router da revisão (D-21, D-22): o que espera decisão no staging."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.revisar import RevisarResumo
from app.services.revisao import RevisaoService

router = APIRouter(prefix="/revisar", tags=["revisão"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/resumo", response_model=RevisarResumo)
def resumo(session: SessionDep) -> Any:
    """Quantos itens pendentes há, por motivo — o contador de "Revisar"."""
    return RevisaoService(session).resumo()
