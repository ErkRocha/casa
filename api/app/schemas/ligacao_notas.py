"""Leituras que o `compras` faz para ligar uma nota a uma despesa (D-33, D-25)."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel

from app.enums import TipoPagamento


class DespesaCandidata(BaseModel):
    """Despesa viva como candidata a ser a compra de uma nota."""

    id: int
    data: date
    valor: Decimal
    descricao: str
    forma_pagamento_id: int | None
    forma_pagamento_apelido: str | None
    forma_pagamento_tipo: TipoPagamento | None
    lancada_pela_nota: bool


class PendenteCartao(BaseModel):
    """Compra pendente do cartão (D-28), só de exibição."""

    id_externo: str
    data: date
    valor: Decimal
    descricao: str
    forma_pagamento_id: int
    forma_pagamento_apelido: str
    forma_pagamento_tipo: TipoPagamento


class TransacaoDaPluggy(BaseModel):
    """A transação viva que nasceu do item da Pluggy com aquele id."""

    id_externo: str
    transacao_id: int


class SituacaoTransacao(BaseModel):
    """Existe? Foi apagada? Se foi juntada, qual ficou no lugar (D-33)."""

    id: int
    viva: bool
    substituida_por_id: int | None
