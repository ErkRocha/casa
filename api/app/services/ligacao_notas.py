"""O que o `compras` pergunta para ligar uma nota a uma despesa (D-33).

Só leitura. O `compras` fala com finanças apenas por HTTP (D-25), então estas
consultas existem para ele: candidatas por data e valor exato, pendentes do
cartão, a transação que a Pluggy confirmou e o destino de uma transação
apagada que a revisão juntou com a do banco.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.models import FormaPagamento, ImportacaoItem, PluggyPendente, Transacao
from app.services.base import NaoEncontrado


class LigacaoNotasService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def despesas(
        self, data_inicio: date, data_fim: date, valor: Decimal, limite: int = 50
    ) -> list[dict[str, object]]:
        """Despesas vivas na janela de datas, com exatamente aquele valor."""
        linhas = self.session.execute(
            select(Transacao, FormaPagamento)
            .outerjoin(FormaPagamento, FormaPagamento.id == Transacao.forma_pagamento_id)
            .where(
                Transacao.deleted_em.is_(None),
                Transacao.tipo == TipoTransacao.DESPESA,
                Transacao.data >= data_inicio,
                Transacao.data <= data_fim,
                Transacao.valor == valor,
            )
            .order_by(Transacao.data, Transacao.id)
            .limit(limite)
        )
        return [
            {
                "id": t.id,
                "data": t.data,
                "valor": t.valor,
                "descricao": t.descricao,
                "forma_pagamento_id": t.forma_pagamento_id,
                "forma_pagamento_apelido": f.apelido if f else None,
                "forma_pagamento_tipo": f.tipo if f else None,
                "lancada_pela_nota": t.lancada_pela_nota,
            }
            for t, f in linhas
        ]

    def pendentes(
        self, data_inicio: date, data_fim: date, valor: Decimal, limite: int = 50
    ) -> list[dict[str, object]]:
        linhas = self.session.execute(
            select(PluggyPendente, FormaPagamento)
            .join(FormaPagamento, FormaPagamento.id == PluggyPendente.forma_pagamento_id)
            .where(
                PluggyPendente.data >= data_inicio,
                PluggyPendente.data <= data_fim,
                PluggyPendente.valor == valor,
            )
            .order_by(PluggyPendente.data, PluggyPendente.id)
            .limit(limite)
        )
        return [
            {
                "id_externo": p.id_externo,
                "data": p.data,
                "valor": p.valor,
                "descricao": p.descricao,
                "forma_pagamento_id": f.id,
                "forma_pagamento_apelido": f.apelido,
                "forma_pagamento_tipo": f.tipo,
            }
            for p, f in linhas
        ]

    def pendente(self, id_externo: str) -> dict[str, object]:
        """Uma compra pendente pelo id da Pluggy; 404 se sumiu (virou transação
        ou foi cancelada)."""
        linha = self.session.execute(
            select(PluggyPendente, FormaPagamento)
            .join(FormaPagamento, FormaPagamento.id == PluggyPendente.forma_pagamento_id)
            .where(PluggyPendente.id_externo == id_externo)
        ).first()
        if linha is None:
            raise NaoEncontrado("compra pendente", 0)
        p, f = linha
        return {
            "id_externo": p.id_externo,
            "data": p.data,
            "valor": p.valor,
            "descricao": p.descricao,
            "forma_pagamento_id": f.id,
            "forma_pagamento_apelido": f.apelido,
            "forma_pagamento_tipo": f.tipo,
        }

    def transacao_da_pluggy(self, id_externo: str) -> int:
        """A transação viva promovida pelo item de staging com aquele id."""
        transacao_id = self.session.scalar(
            select(Transacao.id)
            .join(ImportacaoItem, ImportacaoItem.transacao_id == Transacao.id)
            .where(
                ImportacaoItem.id_externo == id_externo,
                ImportacaoItem.deleted_em.is_(None),
                Transacao.deleted_em.is_(None),
            )
            .limit(1)
        )
        if transacao_id is None:
            raise NaoEncontrado("transação da Pluggy", 0)
        return int(transacao_id)

    def situacao(self, id_: int) -> dict[str, object]:
        """Mesmo apagada, diz para onde a revisão a juntou (`substituida_por_id`)."""
        t = self.session.get(Transacao, id_)
        if t is None:
            raise NaoEncontrado("transação", id_)
        return {
            "id": t.id,
            "viva": t.deleted_em is None,
            "substituida_por_id": t.substituida_por_id,
        }
