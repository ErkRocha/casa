"""Models do schema `compras` (docs/compras/modelo-dados.md).

Espelham a migration 0001: índices parciais, checks e triggers moram lá. O
model não carrega regra de negócio (regra 12); o ciclo lista e despensa é
do service.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from compras.db import Base, Comum, pg_enum
from compras.enums import EstadoDespensa, OrigemItem, SituacaoItem

#: Para onde vai o produto criado às pressas; sempre a última do percurso.
SEM_SECAO = "Sem seção"


class Secao(Comum, Base):
    __tablename__ = "secoes"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)


class Produto(Comum, Base):
    __tablename__ = "produtos"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(Text, nullable=False)
    secao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("secoes.id"), nullable=False)
    unidade_padrao: Mapped[str | None] = mapped_column(Text)
    id_cliente: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    secao: Mapped[Secao] = relationship(lazy="joined", innerjoin=True)


class ItemLista(Comum, Base):
    __tablename__ = "itens_lista"

    produto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("produtos.id"), nullable=False)
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unidade: Mapped[str | None] = mapped_column(Text)
    observacao: Mapped[str | None] = mapped_column(Text)
    situacao: Mapped[SituacaoItem] = mapped_column(
        pg_enum(SituacaoItem, "situacao_item"), nullable=False
    )
    origem: Mapped[OrigemItem] = mapped_column(pg_enum(OrigemItem, "origem_item"), nullable=False)
    adicionado_por: Mapped[str] = mapped_column(Text, nullable=False)
    comprado_por: Mapped[str | None] = mapped_column(Text)
    comprado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    id_cliente: Mapped[uuid.UUID | None] = mapped_column(Uuid)

    produto: Mapped[Produto] = relationship(lazy="joined", innerjoin=True)


class Despensa(Comum, Base):
    __tablename__ = "despensa"

    produto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("produtos.id"), nullable=False)
    estado: Mapped[EstadoDespensa] = mapped_column(
        pg_enum(EstadoDespensa, "estado_despensa"), nullable=False
    )
    estado_por: Mapped[str] = mapped_column(Text, nullable=False)
    estado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    produto: Mapped[Produto] = relationship(lazy="joined", innerjoin=True)
