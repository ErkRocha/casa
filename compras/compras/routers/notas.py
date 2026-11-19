"""Nota fiscal (NFC-e): ler, ver, associar itens e sugerir a transação."""

from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status

from compras.deps import ConsultaDep, FinancasDep, LeitorDep, QuemDep, SessionDep
from compras.models import NotaFiscal, NotaItem
from compras.schemas import (
    AssociarItem,
    AssociarVariante,
    NotaDetalhe,
    NotaEntrada,
    NotaItemLeitura,
    NotaResumo,
    TransacaoSugerida,
    VincularTransacao,
)
from compras.services.notas import NotaService

router = APIRouter(prefix="/notas", tags=["nota fiscal"])


def _detalhe(servico: NotaService, nota: NotaFiscal) -> NotaDetalhe:
    itens = servico.itens(nota.id)
    soma = servico.soma_itens(nota.id)
    precos = servico.precos_da_nota(nota.id)
    return NotaDetalhe(
        **NotaResumo.de(nota).model_dump(),
        itens=[NotaItemLeitura.de(i, precos.get(i.id)) for i in itens],
        soma_itens=soma,
        diferenca=(nota.valor_total - soma) if nota.valor_total is not None and itens else None,
        sem_produto=sum(1 for i in itens if i.variante_id is None),
    )


@router.post(
    "",
    response_model=NotaDetalhe,
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "A chave já foi lida: a nota que existe, sem buscar de novo"},
        422: {"description": "Não é URL de NFC-e do RS nem chave válida"},
    },
)
def ler(
    payload: NotaEntrada,
    response: Response,
    session: SessionDep,
    quem: QuemDep,
    consulta: ConsultaDep,
    leitor: LeitorDep,
) -> Any:
    """Lê a nota pela URL do QR code ou pela chave de 44 dígitos.

    Guarda a resposta da SEFAZ inteira. Se a consulta ou o leitor falhar, a
    nota fica com `status = erro` (201 do mesmo jeito) e pode ser relida.
    """
    servico = NotaService(session, consulta, leitor)
    nota, nova = servico.ler(payload.entrada, quem)
    session.commit()
    if not nova:
        response.status_code = status.HTTP_200_OK
    return _detalhe(servico, nota)


@router.get("", response_model=list[NotaResumo])
def listar(session: SessionDep, limite: Annotated[int, Query(ge=1, le=200)] = 50) -> Any:
    """As notas, da mais recente para a mais antiga (as sem data primeiro)."""
    return [NotaResumo.de(n) for n in NotaService(session).listar(limite)]


@router.get("/itens-sem-produto", response_model=list[NotaItemLeitura])
def sem_produto(session: SessionDep, limite: Annotated[int, Query(ge=1, le=500)] = 100) -> Any:
    """A fila de "associar": itens de notas sem variante (e portanto sem
    produto). O preço só entra no histórico depois de associado."""
    return [NotaItemLeitura.de(i) for i in NotaService(session).sem_produto(limite)]


@router.get("/{id_}", response_model=NotaDetalhe)
def detalhe(id_: int, session: SessionDep) -> Any:
    servico = NotaService(session)
    return _detalhe(servico, servico.get(id_))


@router.post("/{id_}/reler", response_model=NotaDetalhe)
def reler(
    id_: int,
    session: SessionDep,
    quem: QuemDep,
    consulta: ConsultaDep,
    leitor: LeitorDep,
    buscar_de_novo: Annotated[bool, Query()] = False,
) -> Any:
    """Lê de novo uma nota com erro: o conteúdo guardado, ou a SEFAZ outra vez
    (sem conteúdo, ou com `buscar_de_novo`). Nota já lida: 409."""
    servico = NotaService(session, consulta, leitor)
    nota = servico.reler(id_, quem, buscar_de_novo)
    session.commit()
    return _detalhe(servico, nota)


def _item_resposta(servico: NotaService, item: NotaItem) -> NotaItemLeitura:
    return NotaItemLeitura.de(item, servico.precos_da_nota(item.nota_fiscal_id).get(item.id))


@router.put("/{id_}/itens/{item_id}/variante", response_model=NotaItemLeitura)
def associar_variante(
    id_: int, item_id: int, payload: AssociarVariante, session: SessionDep, quem: QuemDep
) -> Any:
    """Diz qual é a variante do item: `{"variante_id": 9}`, ou `{"produto_id": 7,
    "nova": {...}}` para criar uma (nome da nota, GTIN do item e `pesada` pela
    unidade `KG` por padrão). Grava o código do mercado e o apelido do texto: a
    próxima nota com o mesmo código ou texto já vem associada. A resposta traz
    `sugestao_medida` (lida na descrição) enquanto a variante não tem medida:
    só vale depois de confirmada em `PATCH /variantes/{id}`."""
    servico = NotaService(session)
    item = servico.associar_variante(
        id_,
        item_id,
        quem,
        variante_id=payload.variante_id,
        produto_id=payload.produto_id,
        nova=payload.nova.model_dump(exclude_none=True) if payload.nova else {},
    )
    session.commit()
    session.refresh(item)
    return _item_resposta(servico, item)


@router.put("/{id_}/itens/{item_id}/produto", response_model=NotaItemLeitura)
def associar(
    id_: int, item_id: int, payload: AssociarItem, session: SessionDep, quem: QuemDep
) -> Any:
    """Compatibilidade: equivale a `PUT .../variante` com `{"produto_id": ...,
    "nova": {}}`."""
    servico = NotaService(session)
    item = servico.associar_item(id_, item_id, payload.produto_id, quem)
    session.commit()
    session.refresh(item)
    return _item_resposta(servico, item)


@router.get("/{id_}/sugestoes-transacao", response_model=list[TransacaoSugerida])
def sugestoes(id_: int, session: SessionDep, financas: FinancasDep) -> Any:
    """Despesas de finanças do mesmo dia e com o mesmo valor. Só sugestão:
    vincular é o `PUT /notas/{id}/transacao`, que o usuário confirma."""
    return [
        TransacaoSugerida(
            id=t.id,
            data=t.data,
            valor=t.valor,
            descricao=t.descricao,
            forma_pagamento=t.forma_pagamento,
        )
        for t in NotaService(session).sugestoes_transacao(id_, financas)
    ]


@router.put("/{id_}/transacao", response_model=NotaResumo)
def vincular(
    id_: int,
    payload: VincularTransacao,
    session: SessionDep,
    _quem: QuemDep,
    financas: FinancasDep,
) -> Any:
    """Confirma a transação de finanças desta nota (nulo desfaz)."""
    nota = NotaService(session).vincular_transacao(id_, payload.transacao_id, financas)
    session.commit()
    return NotaResumo.de(nota)


@router.delete("/{id_}", response_model=NotaResumo)
def remover(id_: int, session: SessionDep, _quem: QuemDep) -> Any:
    """Soft delete da nota e dos itens. A mesma chave pode ser lida de novo."""
    nota = NotaService(session).remover(id_)
    session.commit()
    return NotaResumo.de(nota)
