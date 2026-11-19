"""Estorno (D-34): achar a compra original e o destino do abatimento.

O estorno abate o gasto na categoria e na pessoa da compra que ele desfez,
quando dá para identificá-la; senão, na categoria sugerida (a da Pluggy) e no
titular do cartão. A regra mora aqui, num lugar só, porque três caminhos a
usam: a promoção do item (`IngestaoService._promover`), a reaplicação nos
dados já gravados (`d34_reaplicar`) e o lançamento manual.

**A compra original** é a despesa da mesma forma de pagamento, até 90 dias
antes do estorno, de mesmo valor (desempate pelo estabelecimento). Sem
nenhuma de mesmo valor, vale a única compra maior do mesmo estabelecimento
(estorno parcial). Em caso de dúvida, nenhuma: nunca se adivinha.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.ingestao.base import sem_acento
from app.models import Conta, FormaPagamento, Transacao

#: Até quantos dias antes do estorno a compra original pode estar.
JANELA_ORIGINAL_DIAS = 90


@dataclass(frozen=True, slots=True)
class Compra:
    """Uma despesa candidata a ser a compra original do estorno."""

    id: int
    data: date
    valor: Decimal
    local_id: int | None
    estabelecimento: str
    categoria_id: int | None
    pessoa_id: int | None


def estabelecimento_de(descricao_original: str | None) -> str:
    """Texto comparável do estabelecimento: sem acento, sem parcela, sem pontuação."""
    texto = sem_acento(descricao_original or "").lower()
    texto = re.sub(r"\s+\d{1,2}\s*/\s*\d{1,2}$", "", texto.strip())
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def achar_original(
    *,
    valor: Decimal,
    local_id: int | None,
    estabelecimento: str,
    candidatas: list[Compra],
) -> Compra | None:
    """A compra que o estorno desfez, se for uma só; senão nada.

    Mesmo valor primeiro. Havendo várias, vale a do mesmo estabelecimento (mesmo
    local ou mesmo texto normalizado). Sem nenhuma de mesmo valor (estorno
    parcial), vale a única do mesmo estabelecimento com valor maior.
    """

    def mesmo_lugar(c: Compra) -> bool:
        return (local_id is not None and c.local_id == local_id) or (
            bool(estabelecimento) and c.estabelecimento == estabelecimento
        )

    por_valor = [c for c in candidatas if c.valor == valor]
    if len(por_valor) == 1:
        return por_valor[0]
    if len(por_valor) > 1:
        mesmo = [c for c in por_valor if mesmo_lugar(c)]
        return mesmo[0] if len(mesmo) == 1 else None
    parcial = [c for c in candidatas if c.valor > valor and mesmo_lugar(c)]
    return parcial[0] if len(parcial) == 1 else None


def compras_antes(session: Session, *, forma_pagamento_id: int | None, data: date) -> list[Compra]:
    """As despesas vivas da forma, na janela de 90 dias até `data`."""
    if forma_pagamento_id is None:
        return []
    # Colunas, não a entidade: a simulação da D-34 roda antes da migration 0009.
    linhas = session.execute(
        select(
            Transacao.id,
            Transacao.data,
            Transacao.valor,
            Transacao.local_id,
            Transacao.descricao_original,
            Transacao.categoria_id,
            Transacao.pessoa_id,
        ).where(
            Transacao.tipo == TipoTransacao.DESPESA,
            Transacao.deleted_em.is_(None),
            Transacao.forma_pagamento_id == forma_pagamento_id,
            Transacao.data <= data,
            Transacao.data >= data - timedelta(days=JANELA_ORIGINAL_DIAS),
        )
    )
    return [
        Compra(
            id=c.id,
            data=c.data,
            valor=c.valor,
            local_id=c.local_id,
            estabelecimento=estabelecimento_de(c.descricao_original),
            categoria_id=c.categoria_id,
            pessoa_id=c.pessoa_id,
        )
        for c in linhas
    ]


def localizar_original(
    session: Session,
    *,
    valor: Decimal,
    data: date,
    forma_pagamento_id: int | None,
    descricao_original: str | None,
    local_id: int | None,
) -> Compra | None:
    """`achar_original` com as candidatas lidas do banco."""
    return achar_original(
        valor=valor,
        local_id=local_id,
        estabelecimento=estabelecimento_de(descricao_original),
        candidatas=compras_antes(session, forma_pagamento_id=forma_pagamento_id, data=data),
    )


def titular_do_cartao(session: Session, forma_pagamento_id: int | None) -> int | None:
    """O titular da forma de pagamento; sem ele, o da conta dela."""
    if forma_pagamento_id is None:
        return None
    forma = session.get(FormaPagamento, forma_pagamento_id)
    if forma is None:
        return None
    if forma.titular_id is not None:
        return forma.titular_id
    conta = session.get(Conta, forma.conta_id) if forma.conta_id else None
    return conta.titular_id if conta else None
