"""Remove do staging e de `transacoes` as compras em aberto da D-23 (D-28).

Desde a D-28 a compra pendente do cartão só é exibida (`pluggy_pendentes`).
As que a D-23 já gravou, enquanto pendentes (item com `MARCA_ABERTA` na
observação), saem daqui:

* o item e a transação viva vão por **soft delete** (`deleted_em`), o que
  libera o `id_externo` da Pluggy: a versão `POSTED` entra normalmente na sync
  em que o banco lançar;
* a transação que o usuário **editou** (pela auditoria, D-06) fica, com o
  item, e o item ganha uma nota para a pessoa conferir depois.

Duas fases, como o retroativo: `planejar` só lê; `executar` grava o plano com
autor `remover_abertas_d28` na auditoria.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.conversao_pluggy import MARCA_ABERTA
from app.enums import StatusItem
from app.models import FormaPagamento, ImportacaoItem
from app.models import Transacao as TransacaoDb
from app.services.sync_pluggy import _campos_editados

AUTOR = "remover_abertas_d28"

NOTA_EDITADA = "D-28: compra em aberto editada; ficou. Confira quando o banco lançar."


class Acao(StrEnum):
    REMOVER = "remover"
    MANTER_EDITADA = "manter (editada)"


@dataclass(slots=True)
class LinhaPlano:
    item_id: int
    id_externo: str | None
    data: date | None
    valor: Decimal | None
    cartao: str
    acao: Acao
    #: Transação viva que sai junto, quando há.
    transacao_id: int | None = None
    #: A nota já está no item (rodada anterior): não repete.
    ja_anotada: bool = False


@dataclass(slots=True)
class PlanoRemocao:
    linhas: list[LinhaPlano] = field(default_factory=list)

    @property
    def a_remover(self) -> list[LinhaPlano]:
        return [linha for linha in self.linhas if linha.acao is Acao.REMOVER]

    @property
    def mantidas(self) -> list[LinhaPlano]:
        return [linha for linha in self.linhas if linha.acao is Acao.MANTER_EDITADA]


class RemoverAbertasD28Service:
    def __init__(self, session: Session) -> None:
        self.session = session

    def planejar(self) -> PlanoRemocao:
        """Só lê: cada item vivo com a marca de aberta e o que se faria com ele."""
        plano = PlanoRemocao()
        itens = self.session.scalars(
            select(ImportacaoItem)
            .where(
                ImportacaoItem.deleted_em.is_(None),
                ImportacaoItem.observacao.contains(MARCA_ABERTA),
                ImportacaoItem.status.in_([StatusItem.PENDENTE, StatusItem.APROVADO]),
            )
            .order_by(ImportacaoItem.id)
        ).all()
        formas = {f.id: f.apelido for f in self.session.scalars(select(FormaPagamento))}
        for item in itens:
            transacao = (
                self.session.get(TransacaoDb, item.transacao_id)
                if item.status is StatusItem.APROVADO and item.transacao_id
                else None
            )
            viva = transacao if transacao is not None and transacao.deleted_em is None else None
            editada = viva is not None and bool(_campos_editados(self.session, viva.id))
            plano.linhas.append(
                LinhaPlano(
                    item_id=item.id,
                    id_externo=item.id_externo,
                    data=item.data,
                    valor=item.valor,
                    cartao=formas.get(item.forma_pagamento_sugerida_id or 0, "?"),
                    acao=Acao.MANTER_EDITADA if editada else Acao.REMOVER,
                    transacao_id=viva.id if viva is not None else None,
                    ja_anotada=NOTA_EDITADA in (item.observacao or ""),
                )
            )
        return plano

    def executar(self, plano: PlanoRemocao) -> dict[str, int]:
        """Grava o plano. Autor `remover_abertas_d28`; sem commit (quem chama decide)."""
        self.session.execute(text("SELECT set_config('app.autor', :a, true)"), {"a": AUTOR})
        removidos = anotados = 0
        for linha in plano.linhas:
            item = self.session.get(ImportacaoItem, linha.item_id)
            if item is None or item.deleted_em is not None:
                continue
            if linha.acao is Acao.MANTER_EDITADA:
                if not linha.ja_anotada:
                    item.observacao = f"{item.observacao or ''} {NOTA_EDITADA}".strip()
                    anotados += 1
                continue
            if linha.transacao_id is not None:
                transacao = self.session.get(TransacaoDb, linha.transacao_id)
                if transacao is not None and transacao.deleted_em is None:
                    transacao.deleted_em = func.now()
            # Status e `transacao_id` ficam como estão: o check
            # `aprovado_tem_transacao` continua valendo, e a auditoria guarda o elo.
            item.deleted_em = func.now()
            removidos += 1
        self.session.flush()
        return {"removidos": removidos, "mantidos": len(plano.mantidas), "anotados": anotados}
