"""A API de finanças falsa dos testes de nota: em memória, nenhuma rede."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

import pytest

from compras.deps import financas
from compras.financas import (
    FinancasIndisponivel,
    FinancasRecusou,
    FormaPagamentoResumo,
    NovaDespesa,
    PendenteResumo,
    SituacaoTransacao,
    TransacaoResumo,
)
from compras.main import app


@dataclass
class FinancasFalsa:
    transacoes: list[TransacaoResumo] = field(default_factory=list)
    pendentes_do_cartao: list[PendenteResumo] = field(default_factory=list)
    #: id da Pluggy -> transação viva que a confirmou.
    pluggy: dict[str, int] = field(default_factory=dict)
    #: transação apagada -> o que a revisão disse dela.
    situacoes: dict[int, SituacaoTransacao] = field(default_factory=dict)
    categoria_da: dict[int, int] = field(default_factory=dict)
    categorias_de_despesa: set[int] = field(default_factory=set)
    formas: list[FormaPagamentoResumo] = field(default_factory=list)
    criadas: list[NovaDespesa] = field(default_factory=list)
    indisponivel: bool = False
    recusa: str | None = None
    pedidos: list[tuple[date, date, Decimal]] = field(default_factory=list)

    def _vivo(self) -> None:
        if self.indisponivel:
            raise FinancasIndisponivel("A API de finanças não respondeu: ConnectError.")

    def despesas(self, inicio: date, fim: date, valor: Decimal) -> list[TransacaoResumo]:
        self._vivo()
        self.pedidos.append((inicio, fim, valor))
        return [t for t in self.transacoes if inicio <= t.data <= fim and t.valor == valor]

    def pendentes(self, inicio: date, fim: date, valor: Decimal) -> list[PendenteResumo]:
        self._vivo()
        return [p for p in self.pendentes_do_cartao if inicio <= p.data <= fim and p.valor == valor]

    def existe(self, transacao_id: int) -> bool:
        self._vivo()
        return any(t.id == transacao_id for t in self.transacoes)

    def pendente_existe(self, id_externo: str) -> bool:
        self._vivo()
        return any(p.id_externo == id_externo for p in self.pendentes_do_cartao)

    def transacao_da_pluggy(self, id_externo: str) -> int | None:
        self._vivo()
        return self.pluggy.get(id_externo)

    def situacao(self, transacao_id: int) -> SituacaoTransacao | None:
        self._vivo()
        if transacao_id in self.situacoes:
            return self.situacoes[transacao_id]
        if any(t.id == transacao_id for t in self.transacoes):
            return SituacaoTransacao(transacao_id, True, None)
        return None

    def categoria_da_transacao(self, transacao_id: int) -> int | None:
        self._vivo()
        return self.categoria_da.get(transacao_id)

    def categoria_de_despesa(self, categoria_id: int) -> bool:
        self._vivo()
        return categoria_id in self.categorias_de_despesa

    def formas_pagamento(self) -> list[FormaPagamentoResumo]:
        self._vivo()
        return list(self.formas)

    def criar_despesa(self, despesa: NovaDespesa) -> int:
        self._vivo()
        if self.recusa:
            raise FinancasRecusou(f"Finanças recusou o lançamento: {self.recusa}")
        self.criadas.append(despesa)
        novo_id = 1000 + len(self.criadas)
        self.transacoes.append(
            TransacaoResumo(
                novo_id,
                despesa.data,
                despesa.valor,
                despesa.descricao,
                None,
                None,
                lancada_pela_nota=True,
            )
        )
        if despesa.categoria_id is not None:
            self.categoria_da[novo_id] = despesa.categoria_id
        return novo_id


@pytest.fixture
def fin() -> Iterator[FinancasFalsa]:
    falsa = FinancasFalsa()
    app.dependency_overrides[financas] = lambda: falsa
    yield falsa
    app.dependency_overrides.pop(financas, None)
