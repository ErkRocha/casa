"""Router da revisão (D-21, D-22): o que espera decisão no staging.

As ações genéricas (ajustar, aprovar, rejeitar) continuam em
`/importacoes/itens`. Aqui ficam a leitura por motivo e as decisões que a
tela de revisão tem e o staging sozinho não sabe fazer: duplicata e
transferência.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.revisar import (
    ConfirmarTransferencias,
    GrupoDuplicata,
    ItemRevisar,
    NaoETransferencia,
    ResolverDuplicata,
    ResultadoRevisao,
    RevisarResumo,
    TransferenciaRevisar,
)
from app.services.revisao import RevisaoService

router = APIRouter(prefix="/revisar", tags=["revisão"])

SessionDep = Annotated[Session, Depends(get_session)]

Motivo = Literal[
    "possivel_duplicata",
    "encargos",
    "pagamento_fatura_cartao",
    "transferencia",
    "observacao",
    "sem_categoria",
    "outros",
]


@router.get("/resumo", response_model=RevisarResumo)
def resumo(session: SessionDep) -> Any:
    """Quantos itens pendentes há, por motivo — o contador de "Revisar"."""
    return RevisaoService(session).resumo()


@router.get("/itens", response_model=list[ItemRevisar])
def itens(session: SessionDep, motivo: Annotated[Motivo | None, Query()] = None) -> Any:
    """Itens pendentes de um motivo (ou de todos), mais recentes primeiro."""
    return RevisaoService(session).itens(motivo)


@router.get("/duplicatas", response_model=list[GrupoDuplicata])
def duplicatas(session: SessionDep) -> Any:
    """Grupos de possível duplicata, com o gêmeo que já virou transação."""
    return RevisaoService(session).duplicatas()


@router.post("/duplicatas/resolver", response_model=ResultadoRevisao)
def resolver_duplicata(payload: ResolverDuplicata, session: SessionDep) -> Any:
    """ "Manter só um" (um fica, o resto sai) ou "são dois" (todos ficam).

    O que fica perde a nota de duplicata e é aprovado se não sobra outro
    motivo. "São dois" com itens idênticos para o banco é recusado: o índice
    de deduplicação não aceita (D-07).
    """
    resultado = RevisaoService(session).resolver_duplicata(
        payload.manter_ids, payload.descartar_ids
    )
    session.commit()
    return resultado


@router.get("/transferencias", response_model=list[TransferenciaRevisar])
def transferencias(session: SessionDep) -> Any:
    """Transferências pendentes, com "saiu de" e "foi para" sugeridos."""
    return RevisaoService(session).transferencias()


@router.post("/transferencias/confirmar", response_model=ResultadoRevisao)
def confirmar_transferencias(payload: ConfirmarTransferencias, session: SessionDep) -> Any:
    """Confirma uma ou várias. Erro num item não derruba os outros (D-05)."""
    resultado = RevisaoService(session).confirmar_transferencias(payload.itens)
    session.commit()
    return resultado


@router.post("/transferencias/{item_id}/nao-e", response_model=ItemRevisar)
def nao_e_transferencia(item_id: int, payload: NaoETransferencia, session: SessionDep) -> Any:
    """Vira despesa ou receita (pelo sentido do dinheiro, se não informado)."""
    item = RevisaoService(session).nao_e_transferencia(item_id, payload.tipo)
    session.commit()
    return item
