"""Router das telas de configuração (D-22). Só leitura.

As edições usam os CRUDs que já existem: `/contas`, `/formas-pagamento`,
`/categorias`, `/regras` e `/categorias-pluggy`.
"""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.configuracoes import CategoriaPluggyUso, ContasECartoes, UsoCategorias
from app.services.configuracoes import ConfiguracoesService

router = APIRouter(prefix="/configuracoes", tags=["configurações"])

SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/contas", response_model=ContasECartoes)
def contas(session: SessionDep) -> Any:
    """Contas e cartões por banco, cada cartão na conta que paga a fatura,
    com a situação da sincronização e os cartões virtuais vistos."""
    return ConfiguracoesService(session).contas()


@router.get("/categorias", response_model=UsoCategorias)
def uso_categorias(
    session: SessionDep,
    competencia: Annotated[date | None, Query(description="Qualquer dia do mês")] = None,
) -> Any:
    """Quantos lançamentos cada categoria tem no mês; a raiz soma as filhas."""
    return ConfiguracoesService(session).uso_categorias(competencia)


@router.get("/categorias-pluggy", response_model=list[CategoriaPluggyUso])
def categorias_pluggy(session: SessionDep) -> Any:
    """As categorias que o banco envia, contadas nos comprovantes da sync,
    com a tradução para as daqui (`categorias_pluggy`)."""
    return ConfiguracoesService(session).categorias_pluggy()
