"""Schemas das telas de configuração (D-22): contas, categorias, Pluggy."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.enums import TipoConta, TipoPagamento

#: `sincronizando`: o mapeamento da Pluggy está ativo e houve movimento nos
#: últimos 12 meses. `pausado`: o mapeamento foi desativado. `sem_movimento`:
#: ativo, mas nada nos últimos 12 meses. `manual`: sem conexão com o banco.
SituacaoConta = Literal["sincronizando", "pausado", "sem_movimento", "manual"]


class ItemContaCartao(BaseModel):
    tipo: Literal["conta", "cartao"]
    conta_id: int
    #: O cartão é uma forma de pagamento da conta que paga a fatura.
    forma_pagamento_id: int | None
    nome: str
    tipo_conta: TipoConta | None
    titular: str | None
    situacao: SituacaoConta
    #: Conta: os tipos das formas que passam por ela (Pix, débito, boleto).
    formas: list[TipoPagamento]
    #: Conta: os cartões cuja fatura ela paga.
    cartoes: list[str]
    #: Cartão: a conta que paga a fatura.
    paga_por: str | None
    #: Cartão: finais de cartão virtual ou adicional vistos nas compras dele.
    cartoes_virtuais: list[str]
    ultimo_movimento: date | None


class GrupoContas(BaseModel):
    """Um banco: as contas e os cartões de uma conexão da Pluggy."""

    titulo: str
    #: Nulo no grupo das contas sem conexão.
    pluggy_item_id: str | None
    #: O início mais antigo entre os mapeamentos ativos do banco.
    desde: date | None
    situacao: Literal["funcionando", "parcial", "pausada", "manual"]
    itens: list[ItemContaCartao]


class ContasECartoes(BaseModel):
    grupos: list[GrupoContas]


class UsoCategoria(BaseModel):
    categoria_id: int
    #: Despesas e receitas do mês; na raiz, somadas as filhas.
    lancamentos: int


class UsoCategorias(BaseModel):
    competencia: date
    sem_categoria: int
    categorias: list[UsoCategoria]


class CategoriaPluggyUso(BaseModel):
    """Uma categoria que o banco envia, com a tradução para as daqui."""

    pluggy_categoria_id: str
    pluggy_categoria_nome: str
    #: Transações consolidadas com esta categoria nos comprovantes da sync.
    transacoes: int
    #: O mapeamento (`categorias_pluggy`), quando existe.
    mapeamento_id: int | None
    categoria_id: int | None
    categoria_nome: str | None
    ativo: bool | None
    #: Família de transferência da Pluggy: nunca vira despesa (D-21).
    transferencia: bool
