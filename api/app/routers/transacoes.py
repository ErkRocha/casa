"""Router de transações: listagem filtrada, CRUD e ação em lote."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.schemas.common import LoteResponse, OkResponse, Paginacao, paginacao
from app.schemas.ligacao_notas import (
    DespesaCandidata,
    PendenteCartao,
    SituacaoTransacao,
    TransacaoDaPluggy,
)
from app.schemas.transacoes import (
    LoteAtribuir,
    LoteExcluir,
    TotalDia,
    TransacaoCreate,
    TransacaoFiltros,
    TransacaoListagem,
    TransacaoRead,
    TransacaoUpdate,
    transacao_filtros,
)
from app.services.cadastros import LocalService
from app.services.ligacao_notas import LigacaoNotasService
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


@router.get("/dias", response_model=list[TotalDia])
def dias(session: SessionDep, filtros: FiltrosDep) -> Any:
    """O total de cada dia do filtro, para a listagem agrupada por dia (D-24).

    Despesas e receitas somadas no banco; transferências contam na
    quantidade e ficam fora das somas (D-05).
    """
    return TransacaoService(session).dias(filtros)


@router.get("/candidatas-nota", response_model=list[DespesaCandidata])
def candidatas_nota(
    session: SessionDep,
    data_inicio: date,
    data_fim: date,
    valor: Annotated[Decimal, Query(gt=0)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Any:
    """Despesas vivas na janela de datas com exatamente aquele valor, com a
    forma de pagamento e a marca `lancada_pela_nota`. Para o `compras` sugerir
    a despesa de uma nota (D-33)."""
    return LigacaoNotasService(session).despesas(data_inicio, data_fim, valor, limit)


@router.get("/pendentes-cartao", response_model=list[PendenteCartao])
def pendentes_cartao(
    session: SessionDep,
    data_inicio: date,
    data_fim: date,
    valor: Annotated[Decimal, Query(gt=0)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Any:
    """Compras pendentes do cartão (D-28) na janela de datas, com o valor exato."""
    return LigacaoNotasService(session).pendentes(data_inicio, data_fim, valor, limit)


@router.get("/pendentes-cartao/{id_externo}", response_model=PendenteCartao)
def pendente_cartao(id_externo: str, session: SessionDep) -> Any:
    """Uma compra pendente pelo id da Pluggy; 404 se ela sumiu (D-28)."""
    return LigacaoNotasService(session).pendente(id_externo)


@router.get("/por-pluggy/{id_externo}", response_model=TransacaoDaPluggy)
def por_pluggy(id_externo: str, session: SessionDep) -> Any:
    """A transação viva que o item da Pluggy com este id virou; 404 se não há."""
    return {
        "id_externo": id_externo,
        "transacao_id": LigacaoNotasService(session).transacao_da_pluggy(id_externo),
    }


@router.get("/{id_}/situacao", response_model=SituacaoTransacao)
def situacao(id_: int, session: SessionDep) -> Any:
    """Viva ou apagada, e `substituida_por_id` quando a revisão a juntou com a
    do banco. Diferente de `GET /transacoes/{id}`, não dá 404 para a apagada."""
    return LigacaoNotasService(session).situacao(id_)


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
