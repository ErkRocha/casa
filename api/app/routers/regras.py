"""Router de regras de categorização (fase 5, passo 5)."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.common import OkResponse, Page, Paginacao, paginacao
from app.services.ingestao import IngestaoService
from app.services.regras import RegraService

router = APIRouter(prefix="/regras", tags=["regras"])

SessionDep = Annotated[Session, Depends(get_session)]
PaginacaoDep = Annotated[Paginacao, Depends(paginacao)]

TipoMatch = Annotated[str, Field(pattern="^(contem|regex|exato)$")]


class RegraCreate(BaseModel):
    padrao: Annotated[str, Field(min_length=1, max_length=200)]
    tipo_match: TipoMatch = "contem"
    categoria_id: int | None = None
    local_id: int | None = None
    pessoa_id: int | None = None
    #: Menor roda primeiro.
    prioridade: int = 100
    ativo: bool = True


class RegraUpdate(BaseModel):
    padrao: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    tipo_match: TipoMatch | None = None
    categoria_id: int | None = None
    local_id: int | None = None
    pessoa_id: int | None = None
    prioridade: int | None = None
    ativo: bool | None = None


class RegraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    padrao: str
    tipo_match: str
    categoria_id: int | None
    local_id: int | None
    pessoa_id: int | None
    prioridade: int
    #: "usuario" | "correcao_automatica".
    criada_por: str
    #: Quantas vezes já foi reforçada por uma correção do usuário.
    acertos: int
    ativo: bool
    criado_em: datetime


class TesteRegra(BaseModel):
    padrao: str
    tipo_match: TipoMatch = "contem"
    texto: str


class Reaplicacao(BaseModel):
    avaliados: int
    alterados: int


@router.get("", response_model=Page[RegraRead])
def listar(session: SessionDep, pag: PaginacaoDep) -> Any:
    """Na ordem em que rodam: prioridade, depois as que mais acertam."""
    itens, total = RegraService(session).listar_ordenado(pag)
    return Page(items=itens, total=total, limit=pag.limit, offset=pag.offset)


@router.post("", response_model=RegraRead, status_code=status.HTTP_201_CREATED)
def criar(payload: RegraCreate, session: SessionDep) -> Any:
    regra = RegraService(session).criar(payload.model_dump())
    session.commit()
    return regra


@router.patch("/{id_}", response_model=RegraRead)
def atualizar(id_: int, payload: RegraUpdate, session: SessionDep) -> Any:
    regra = RegraService(session).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return regra


@router.delete("/{id_}", response_model=OkResponse)
def remover(id_: int, session: SessionDep) -> Any:
    """Soft delete: a regra some do motor mas fica no histórico."""
    RegraService(session).remover(id_)
    session.commit()
    return OkResponse()


@router.post("/testar", response_model=dict[str, bool])
def testar(payload: TesteRegra, session: SessionDep) -> Any:
    """Prévia do casamento, para cadastrar regra sem tentativa e erro."""
    casa = RegraService(session).testar(payload.padrao, payload.tipo_match, payload.texto)
    return {"casa": casa}


@router.post("/reaplicar", response_model=Reaplicacao)
def reaplicar(
    session: SessionDep,
    importacao_id: int | None = None,
) -> Any:
    """Roda as regras de novo sobre os itens ainda pendentes.

    É o que fecha o ciclo da D-09: corrigir uma linha resolve as outras do
    mesmo estabelecimento sem tocar em cada uma.

    Só mexe em item pendente, e só preenche campo vazio — escolha feita na mão
    não é sobrescrita.
    """
    resultado = IngestaoService(session).reaplicar_regras(importacao_id)
    session.commit()
    return resultado
