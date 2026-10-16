"""Schemas da revisão (D-21, D-22)."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.enums import StatusItem, TipoPagamento, TipoTransacao


class MotivoRevisao(BaseModel):
    #: Chave estável (`possivel_duplicata`, `transferencia`...).
    motivo: str
    rotulo: str
    quantidade: int


class RevisarResumo(BaseModel):
    """Itens pendentes no staging, por motivo, na ordem de leitura."""

    total: int
    #: Só os motivos com algum item.
    motivos: list[MotivoRevisao]


class ItemRevisar(BaseModel):
    """Um item do staging como a revisão mostra: com nomes, não só ids."""

    id: int
    importacao_id: int
    motivo: str
    status: StatusItem
    data: date | None
    valor: Decimal | None
    tipo_sugerido: TipoTransacao | None
    competencia_sugerida: date | None
    #: A descrição que a promoção vai gravar, derivada da linha crua.
    descricao: str
    descricao_original: str | None
    observacao: str | None
    categoria_sugerida_id: int | None
    categoria_nome: str | None
    pessoa_sugerida_id: int | None
    pessoa_nome: str | None
    forma_pagamento_sugerida_id: int | None
    forma_pagamento_tipo: TipoPagamento | None
    forma_pagamento_apelido: str | None
    #: A conta da forma de pagamento: de onde o item veio.
    conta_id: int | None
    conta_nome: str | None
    #: Preenchido no item já aprovado (gêmeo que já virou transação).
    transacao_id: int | None = None


class ContaResumo(BaseModel):
    id: int
    nome: str


TipoTransferencia = Literal[
    "pagamento_fatura_conta", "pagamento_fatura_cartao", "mesma_pessoa", "outra"
]


class TransferenciaRevisar(BaseModel):
    """Transferência pendente, com o "saiu de" e o "foi para" que dá para saber."""

    item: ItemRevisar
    tipo: TipoTransferencia
    #: Da transação da Pluggy guardada no comprovante. Nulo quando não há
    #: comprovante (PDF) ou a Pluggy não informa.
    direcao: Literal["entrada", "saida"] | None
    origem: ContaResumo | None
    destino: ContaResumo | None
    #: O cartão cuja fatura foi paga, quando o dinheiro foi para uma fatura
    #: da própria conta ("Nubank Gold •••• 7704").
    fatura_de: str | None
    #: A outra ponta do mesmo dinheiro, quando também está na revisão:
    #: mesmo valor, sentido oposto, outra conta, até 3 dias de distância.
    par_item_id: int | None
    #: O que confirmar faz. `descartar`: o cartão é forma da própria conta e
    #: o gasto já está nas compras, então não há transferência a gravar (D-05).
    ao_confirmar: Literal["transferencia", "descartar"]


class GrupoDuplicata(BaseModel):
    """Itens com a mesma conta, data, valor e descrição: possível duplicata."""

    data: date
    valor: Decimal
    descricao: str
    #: Pendentes e o gêmeo que já virou transação, se houver.
    itens: list[ItemRevisar]
    #: Um dos itens já é transação: só resta descartar os outros.
    ja_lancado: bool
    #: O banco aceita os itens como transações separadas? Itens com a mesma
    #: data, valor, descrição original e forma de pagamento esbarram no
    #: índice de deduplicação (`uq_transacoes_dedup`, D-07).
    podem_ser_dois: bool


class ResolverDuplicata(BaseModel):
    """ "Manter só um": um em `manter_ids`, o resto em `descartar_ids`.

    "São dois": todos em `manter_ids`.
    """

    manter_ids: Annotated[list[int], Field(min_length=1, max_length=50)]
    descartar_ids: Annotated[list[int], Field(max_length=50)] = []


class ConfirmarTransferencia(BaseModel):
    item_id: int
    #: Nulos = vale a sugestão da revisão.
    conta_origem_id: int | None = None
    conta_destino_id: int | None = None


class ConfirmarTransferencias(BaseModel):
    """Uma ou várias ("confirmar todas")."""

    itens: Annotated[list[ConfirmarTransferencia], Field(min_length=1, max_length=500)]


class NaoETransferencia(BaseModel):
    #: Nulo = pelo sentido do dinheiro: saída é despesa, entrada é receita.
    tipo: Literal[TipoTransacao.DESPESA, TipoTransacao.RECEITA] | None = None


class ErroItem(BaseModel):
    item_id: int
    erro: str


class ResultadoRevisao(BaseModel):
    """O que uma decisão da revisão fez com cada item."""

    #: Viraram transação.
    aprovados: int = 0
    #: Rejeitados, com o motivo gravado no item.
    descartados: int = 0
    #: Seguem na revisão, por outro motivo (sem categoria, observação...).
    pendentes: int = 0
    erros: list[ErroItem] = []
