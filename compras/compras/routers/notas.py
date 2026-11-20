"""Nota fiscal (NFC-e): ler, ver, associar itens e sugerir a transação."""

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Response, status

from compras.deps import ConsultaDep, FinancasDep, LeitorDep, QuemDep, SessionDep
from compras.financas import FinancasIndisponivel
from compras.models import NotaFiscal, NotaItem
from compras.schemas import (
    AssociarItem,
    AssociarVariante,
    ConsolidacaoResultado,
    LancarDespesa,
    NotaDetalhe,
    NotaEntrada,
    NotaItemLeitura,
    NotaResumo,
    NotasPagina,
    PreviaLancamento,
    SugestaoLigacao,
    VincularTransacao,
)
from compras.schemas_conferencia import ConferenciaConfirmar, ConferenciaResposta
from compras.services.conferencia import ConferenciaService
from compras.services.ligacao_notas import LigacaoNotaService
from compras.services.notas import NotaService

router = APIRouter(prefix="/notas", tags=["nota fiscal"])


def _detalhe(servico: NotaService, nota: NotaFiscal, com_proximos: bool = False) -> NotaDetalhe:
    itens = servico.itens(nota.id)
    soma = servico.soma_itens(nota.id)
    precos = servico.precos_da_nota(nota.id)
    return NotaDetalhe(
        **NotaResumo.de(nota).model_dump(),
        proximos=ConferenciaService(servico.session).proximos(nota) if com_proximos else None,
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
    return _detalhe(servico, nota, com_proximos=True)


@router.get("", response_model=NotasPagina)
def listar(
    session: SessionDep,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    conferida: Annotated[
        bool | None, Query(description="Só as conferidas (true) ou não (false)")
    ] = None,
    com_transacao: Annotated[
        bool | None,
        Query(description="Só as ligadas a uma despesa (true) ou sem ligação (false)"),
    ] = None,
) -> Any:
    """As notas, da mais recente para a mais antiga (as sem data primeiro),
    paginadas com o total. Os filtros servem às filas "notas sem despesa"
    (`com_transacao=false`) e "notas sem conferência" (`conferida=false`)."""
    notas, total = NotaService(session).listar(limite, offset, conferida, com_transacao)
    return NotasPagina(
        items=[NotaResumo.de(n) for n in notas], total=total, limite=limite, offset=offset
    )


@router.post("/consolidar-ligacoes", response_model=ConsolidacaoResultado)
def consolidar_ligacoes(session: SessionDep, financas: FinancasDep) -> Any:
    """Idempotente. Nota ligada a uma pendente que já virou transação passa a
    transação; pendente sumida sem virar transação desfaz a ligação; nota
    ligada a uma transação juntada pela revisão passa para a substituta. Chamado
    pela tela de notas e pelo agendador de finanças depois da sync; por isso
    não exige `X-Quem` (a auditoria sai como `leitura_nfce`)."""
    resultado = LigacaoNotaService(session).consolidar(financas)
    session.commit()
    return resultado


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
    return _detalhe(servico, nota, com_proximos=True)


@router.post(
    "/{id_}/reler-forma-pagamento",
    response_model=NotaDetalhe,
    responses={
        409: {"description": "Nota não lida, ou forma já preenchida sem `sobrescrever`"},
        422: {"description": "Sem página guardada, ou página que o leitor não entende"},
    },
)
def reler_forma_pagamento(
    id_: int,
    session: SessionDep,
    quem: QuemDep,
    leitor: LeitorDep,
    sobrescrever: Annotated[bool, Query()] = False,
) -> Any:
    """Relê só a forma de pagamento da página guardada, sem tocar nos itens
    nem na despesa ligada. Página sem forma: a nota volta sem mudança."""
    servico = NotaService(session, leitor=leitor)
    nota = servico.reler_forma_pagamento(id_, sobrescrever)
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


@router.get("/{id_}/conferencia", response_model=ConferenciaResposta)
def previa_conferencia(id_: int, session: SessionDep) -> Any:
    """A prévia da conferência da lista: o que a confirmação faria, sem gravar
    nada. Nota que não foi lida: 409. Já conferida: o que foi aplicado."""
    return ConferenciaService(session).previa(id_)


@router.post("/{id_}/conferencia", response_model=ConferenciaResposta)
def confirmar_conferencia(
    id_: int,
    session: SessionDep,
    quem: QuemDep,
    payload: Annotated[ConferenciaConfirmar | None, Body()] = None,
) -> Any:
    """Confirma a conferência com as respostas às perguntas de quantidade
    (`{"diferencas": [{"item_lista_id": 41, "volta": true}]}`). Pergunta sem
    resposta: 422 com o que falta. Confirmar de novo: 200, sem mudança."""
    respostas = {d.item_lista_id: d.volta for d in (payload or ConferenciaConfirmar()).diferencas}
    resposta = ConferenciaService(session, quem).confirmar(id_, respostas)
    session.commit()
    return resposta


@router.get("/{id_}/sugestoes-transacao", response_model=list[SugestaoLigacao])
def sugestoes(id_: int, session: SessionDep, financas: FinancasDep) -> Any:
    """Despesas de finanças de um dia antes a um dia depois da emissão, com o
    valor exato, nas transações e nas compras pendentes do cartão (D-28). A
    forma do mesmo tipo que a da página vem primeiro, depois o dia mais
    próximo; nada é filtrado. Só sugestão: ligar é o `PUT /notas/{id}/transacao`,
    que o usuário confirma."""
    return LigacaoNotaService(session).sugestoes(id_, financas)


@router.put("/{id_}/transacao", response_model=NotaResumo)
def vincular(
    id_: int,
    payload: VincularTransacao,
    session: SessionDep,
    _quem: QuemDep,
    financas: FinancasDep,
) -> Any:
    """Confirma a despesa da nota: `{"transacao_id": 7}` ou
    `{"pendente_id_externo": "..."}` (um dos dois). Os dois nulos desfazem. O
    que se liga precisa existir em finanças."""
    nota = LigacaoNotaService(session).vincular(
        id_, payload.transacao_id, payload.pendente_id_externo, financas
    )
    session.commit()
    return NotaResumo.de(nota)


@router.get("/{id_}/lancar-despesa", response_model=PreviaLancamento)
def previa_lancamento(id_: int, session: SessionDep, financas: FinancasDep) -> Any:
    """A prévia de "lançar despesa pela nota": valor e data da nota, o mercado
    como descrição, a forma da página, a categoria sugerida pelos itens e as
    formas de pagamento de finanças. Nota já ligada: 409."""
    try:
        return LigacaoNotaService(session).previa(id_, financas)
    except FinancasIndisponivel as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


@router.post("/{id_}/lancar-despesa", response_model=NotaResumo)
def lancar_despesa(
    id_: int,
    payload: LancarDespesa,
    session: SessionDep,
    _quem: QuemDep,
    financas: FinancasDep,
) -> Any:
    """Cria a despesa em finanças (`POST /api/transacoes`, `lancada_pela_nota`),
    liga a nota a ela e marca `despesa_lancada_pela_nota`. Nota já ligada: 409.
    Finanças fora do ar: 503, e nada é gravado."""
    try:
        nota = LigacaoNotaService(session).lancar(id_, payload, financas)
    except FinancasIndisponivel as exc:
        session.rollback()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    session.commit()
    return NotaResumo.de(nota)


@router.delete("/{id_}", response_model=NotaResumo)
def remover(id_: int, session: SessionDep, _quem: QuemDep) -> Any:
    """Soft delete da nota e dos itens. A mesma chave pode ser lida de novo."""
    nota = NotaService(session).remover(id_)
    session.commit()
    return NotaResumo.de(nota)
