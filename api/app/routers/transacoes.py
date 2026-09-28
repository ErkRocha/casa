"""Router de transações: listagem filtrada, CRUD e ação em lote."""

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.common import LoteResponse, OkResponse, Paginacao, paginacao
from app.schemas.transacoes import (
    LoteAtribuir,
    LoteExcluir,
    TransacaoCreate,
    TransacaoFiltros,
    TransacaoListagem,
    TransacaoRead,
    TransacaoUpdate,
    transacao_filtros,
)
from app.services.cadastros import LocalService
from app.services.transacoes import TransacaoService

router = APIRouter(prefix="/transacoes", tags=["transações"])

SessionDep = Annotated[Session, Depends(get_session)]
FiltrosDep = Annotated[TransacaoFiltros, Depends(transacao_filtros)]
PaginacaoDep = Annotated[Paginacao, Depends(paginacao)]


@router.get("", response_model=TransacaoListagem)
def listar(session: SessionDep, filtros: FiltrosDep, pag: PaginacaoDep) -> Any:
    """Listagem paginada com todos os filtros combináveis.

    Os totais do rodapé vêm da mesma cláusula de filtro, somados no banco — o
    front não recalcula nada em cima da página que recebeu.
    """
    service = TransacaoService(session)
    itens, total = service.listar(filtros, pag)
    return TransacaoListagem(
        items=[TransacaoRead.model_validate(item) for item in itens],
        total=total,
        limit=pag.limit,
        offset=pag.offset,
        totais=service.totais(filtros),
    )


@router.get("/competencias", response_model=list[date])
def competencias(session: SessionDep) -> Any:
    """Meses que têm lançamento — alimenta o seletor de período."""
    return TransacaoService(session).competencias_disponiveis()


@router.get("/{id_}", response_model=TransacaoRead)
def obter(id_: int, session: SessionDep) -> Any:
    return TransacaoService(session).get(id_)


@router.post("", response_model=TransacaoRead, status_code=status.HTTP_201_CREATED)
def criar(
    payload: TransacaoCreate,
    session: SessionDep,
    local_nome: Annotated[
        str | None,
        Query(description="Nome livre do local; casa ou cria pelo nome normalizado"),
    ] = None,
) -> Any:
    """Cria uma transação.

    Sem `competencia`, vale o mês de `data` (D-02). O `hash_dedup` é coluna
    gerada: mandar a mesma transação duas vezes esbarra no índice único e
    volta 409.
    """
    service = TransacaoService(session)
    dados = payload.model_dump()

    # Conveniência do lançamento manual: o usuário digita o local livre e o
    # service casa pelo nome normalizado em vez de criar duplicata.
    if local_nome and dados.get("local_id") is None:
        dados["local_id"] = LocalService(session).buscar_ou_criar(local_nome).id

    transacao = service.criar(dados)
    session.commit()
    return transacao


@router.patch("/{id_}", response_model=TransacaoRead)
def atualizar(id_: int, payload: TransacaoUpdate, session: SessionDep) -> Any:
    """Edição parcial — é o que a edição inline da tabela usa.

    `descricao_original` não é editável: é o texto cru do extrato (regra 11).
    """
    transacao = TransacaoService(session).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return transacao


@router.delete("/{id_}", response_model=OkResponse)
def remover(id_: int, session: SessionDep) -> Any:
    TransacaoService(session).remover(id_)
    session.commit()
    return OkResponse()


@router.post("/lote/atribuir", response_model=LoteResponse)
def atribuir_em_lote(payload: LoteAtribuir, session: SessionDep) -> Any:
    """Aplica categoria e/ou pessoa a várias transações de uma vez.

    `pessoa: "conjunto"` limpa o dono — gasto conjunto é `pessoa_id` nulo, não
    uma pessoa chamada "conjunto" (D-03).
    """
    afetadas = TransacaoService(session).atribuir_em_lote(
        payload.ids, payload.categoria_id, payload.pessoa
    )
    session.commit()
    return LoteResponse(afetadas=afetadas)


@router.post("/lote/excluir", response_model=LoteResponse)
def excluir_em_lote(payload: LoteExcluir, session: SessionDep) -> Any:
    """Soft delete em lote. Reversível: basta limpar `deleted_em` (D-06)."""
    afetadas = TransacaoService(session).remover_em_lote(payload.ids)
    session.commit()
    return LoteResponse(afetadas=afetadas)
