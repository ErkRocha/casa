"""Router da sincronização com a Pluggy (D-24; fase 5b, passo 10)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.sincronizacao import EstadoSincronizacao, LinhaHistorico
from app.services.execucao_sync import SyncDesligada
from app.services.sincronizacao import SincronizacaoService

router = APIRouter(prefix="/sincronizacao", tags=["sincronização"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/estado", response_model=EstadoSincronizacao)
def estado(session: SessionDep) -> Any:
    """Última atualização dos bancos, a próxima (se houver agenda) e a
    execução disparada pelo painel."""
    return SincronizacaoService(session).estado()


@router.post("/atualizar", response_model=EstadoSincronizacao, status_code=status.HTTP_202_ACCEPTED)
def atualizar(session: SessionDep) -> Any:
    """Dispara a sync em segundo plano e volta na hora, sem esperar a Pluggy.

    Acompanhe por `GET /sincronizacao/estado` (`execucao.situacao`). Pedir de
    novo enquanto roda devolve a mesma execução. Se a agendada (ou um `make
    sync`) estiver rodando, a execução termina como `ocupada`, sem gravar.
    """
    try:
        return SincronizacaoService(session).atualizar_agora()
    except SyncDesligada as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/historico", response_model=list[LinhaHistorico])
def historico(session: SessionDep, dias: Annotated[int, Query(ge=1, le=366)] = 30) -> Any:
    """As importações do período: o que entrou, o que espera revisão, e se
    dá para desfazer (`POST /importacoes/{id}/desfazer`)."""
    return SincronizacaoService(session).historico(dias)
