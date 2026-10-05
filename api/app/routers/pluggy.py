"""Router do mapeamento de contas da Pluggy (fase 5b, passo 4).

CRUD de `contas_pluggy`. A tela vem no passo 8; por ora isto serve ao
`make pluggy-mapear` e a quem chamar a API direto.

Toda resposta de um mapeamento traz `avisos`: a sobreposição com PDF já
promovido naquela conta (D-16). É aviso, não erro — o mapeamento é gravado.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ContaPluggy
from app.schemas.common import OkResponse, Page, Paginacao, paginacao
from app.schemas.pluggy import ContaPluggyCreate, ContaPluggyRead, ContaPluggyUpdate
from app.services.pluggy_mapeamento import ContaPluggyService

router = APIRouter(prefix="/contas-pluggy", tags=["pluggy"])

SessionDep = Annotated[Session, Depends(get_session)]
PaginacaoDep = Annotated[Paginacao, Depends(paginacao)]


def _ler(service: ContaPluggyService, obj: ContaPluggy) -> ContaPluggyRead:
    lido = ContaPluggyRead.model_validate(obj)
    lido.avisos = service.avisos(obj)
    return lido


@router.get("", response_model=Page[ContaPluggyRead])
def listar(session: SessionDep, pag: PaginacaoDep, apenas_ativos: bool = False) -> Any:
    service = ContaPluggyService(session)
    itens, total = service.listar(pag, apenas_ativos=apenas_ativos)
    return Page(
        items=[_ler(service, i) for i in itens], total=total, limit=pag.limit, offset=pag.offset
    )


@router.get("/{id_}", response_model=ContaPluggyRead)
def obter(id_: int, session: SessionDep) -> Any:
    service = ContaPluggyService(session)
    return _ler(service, service.get(id_))


@router.post("", response_model=ContaPluggyRead, status_code=status.HTTP_201_CREATED)
def criar(payload: ContaPluggyCreate, session: SessionDep) -> Any:
    service = ContaPluggyService(session)
    obj = service.criar(payload.model_dump())
    session.commit()
    return _ler(service, obj)


@router.patch("/{id_}", response_model=ContaPluggyRead)
def atualizar(id_: int, payload: ContaPluggyUpdate, session: SessionDep) -> Any:
    service = ContaPluggyService(session)
    # `exclude_unset`: PATCH parcial não zera o que o cliente omitiu.
    obj = service.atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return _ler(service, obj)


@router.delete("/{id_}", response_model=OkResponse)
def remover(id_: int, session: SessionDep) -> Any:
    """Desativa o mapeamento: soft delete, nunca apaga a linha (regra 2)."""
    ContaPluggyService(session).remover(id_)
    session.commit()
    return OkResponse()
