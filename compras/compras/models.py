"""Models do schema `compras` (docs/compras/modelo-dados.md).

Espelham a migration 0001: índices parciais, checks e triggers moram lá. O
model não carrega regra de negócio (regra 12); o ciclo lista e despensa é
do service.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from compras.db import Base, Comum, pg_enum
from compras.enums import (
    EstadoDespensa,
    MedidaBase,
    OrigemAssociacao,
    OrigemItem,
    SituacaoItem,
    StatusNota,
    TipoRefeicao,
    UnidadeMedida,
)

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
    #: Em que o produto é medido (migration 0004). Nulo: sem conversão.
    medida_base: Mapped[MedidaBase | None] = mapped_column(pg_enum(MedidaBase, "medida_base"))
    #: Quanto de `medida_base` tem uma unidade do produto (uma embalagem ou uma peça).
    medida_por_unidade: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))

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


# --- Nota fiscal e preços (migration 0002) ------------------------------------


class Mercado(Comum, Base):
    __tablename__ = "mercados"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    razao_social: Mapped[str | None] = mapped_column(Text)
    cnpj: Mapped[str | None] = mapped_column(Text)
    endereco: Mapped[str | None] = mapped_column(Text)
    cidade: Mapped[str | None] = mapped_column(Text)


class NotaFiscal(Comum, Base):
    __tablename__ = "notas_fiscais"

    chave_acesso: Mapped[str] = mapped_column(Text, nullable=False)
    mercado_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("mercados.id"))
    emitida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    desconto_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    url_consulta: Mapped[str] = mapped_column(Text, nullable=False)
    conteudo_original: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    conteudo_tipo: Mapped[str | None] = mapped_column(Text)
    leitor_versao: Mapped[str | None] = mapped_column(Text)
    status: Mapped[StatusNota] = mapped_column(pg_enum(StatusNota, "status_nota"), nullable=False)
    erro_mensagem: Mapped[str | None] = mapped_column(Text)
    #: A compra em finanças. Id simples, sem FK (D-25).
    transacao_id: Mapped[int | None] = mapped_column(BigInteger)
    lida_por: Mapped[str] = mapped_column(Text, nullable=False)

    mercado: Mapped[Mercado | None] = relationship(lazy="joined")


class NotaItem(Comum, Base):
    __tablename__ = "nota_itens"

    nota_fiscal_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("notas_fiscais.id"), nullable=False
    )
    linha_num: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    #: O texto cru da nota. Imutável (trigger na 0002).
    descricao_original: Mapped[str] = mapped_column(Text, nullable=False)
    quantidade: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unidade: Mapped[str | None] = mapped_column(Text)
    valor_unitario: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    valor_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    desconto: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    produto_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("produtos.id"))
    origem_associacao: Mapped[OrigemAssociacao | None] = mapped_column(
        pg_enum(OrigemAssociacao, "origem_associacao")
    )

    produto: Mapped[Produto | None] = relationship(lazy="joined")


class Apelido(Comum, Base):
    __tablename__ = "apelidos"

    produto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("produtos.id"), nullable=False)
    texto_normalizado: Mapped[str | None] = mapped_column(Text)
    gtin: Mapped[str | None] = mapped_column(Text)
    #: Nulo: vale em qualquer mercado.
    mercado_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("mercados.id"))
    acertos: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    #: "usuario" (associou um item sem produto) ou "correcao" (trocou o que
    #: a associação automática tinha escolhido).
    criado_por: Mapped[str] = mapped_column(Text, nullable=False)


# --- Identidade pelo Tailscale (migration 0003) --------------------------------


class IdentidadeTailscale(Comum, Base):
    __tablename__ = "identidades_tailscale"

    #: `Tailscale-User-Login`, em minúsculas.
    login: Mapped[str] = mapped_column(Text, nullable=False)
    #: Como aparece em "adicionou" e "pegou": "Erik", "Laura".
    nome: Mapped[str] = mapped_column(Text, nullable=False)


# --- Cardápio (migration 0004, D-30) --------------------------------------------


class Pessoa(Comum, Base):
    """Quem come. Não é a `pessoa_id` de finanças (D-25)."""

    __tablename__ = "pessoas"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    identidade_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("identidades_tailscale.id")
    )
    porcao_padrao: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False, default=1)

    identidade: Mapped[IdentidadeTailscale | None] = relationship(lazy="joined")


class Receita(Comum, Base):
    __tablename__ = "receitas"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    nome_normalizado: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoRefeicao] = mapped_column(
        pg_enum(TipoRefeicao, "tipo_refeicao"), nullable=False
    )
    rendimento_porcoes: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    tempo_preparo_min: Mapped[int | None] = mapped_column(Integer)
    modo_preparo: Mapped[str | None] = mapped_column(Text)
    pode_antecipar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dura_dias: Mapped[int | None] = mapped_column(Integer)
    pode_congelar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    id_cliente: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class ReceitaIngrediente(Comum, Base):
    __tablename__ = "receita_ingredientes"

    receita_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("receitas.id"), nullable=False)
    produto_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("produtos.id"), nullable=False)
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unidade: Mapped[UnidadeMedida] = mapped_column(
        pg_enum(UnidadeMedida, "unidade_medida"), nullable=False
    )
    observacao: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)

    produto: Mapped[Produto] = relationship(lazy="joined", innerjoin=True)


class Semana(Comum, Base):
    __tablename__ = "semanas"

    #: Sempre segunda-feira.
    inicio: Mapped[date] = mapped_column(Date, nullable=False)
    observacao: Mapped[str | None] = mapped_column(Text)


class Refeicao(Comum, Base):
    """Um prato num dia e tipo de refeição."""

    __tablename__ = "refeicoes"

    semana_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("semanas.id"), nullable=False)
    dia: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[TipoRefeicao] = mapped_column(
        pg_enum(TipoRefeicao, "tipo_refeicao"), nullable=False
    )
    receita_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("receitas.id"))
    observacao: Mapped[str | None] = mapped_column(Text)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RefeicaoPessoa(Comum, Base):
    __tablename__ = "refeicao_pessoas"

    refeicao_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("refeicoes.id"), nullable=False)
    pessoa_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pessoas.id"), nullable=False)
    #: Nulo: vale a `porcao_padrao` da pessoa.
    porcoes: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))


class SessaoPreparo(Comum, Base):
    __tablename__ = "sessoes_preparo"

    semana_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("semanas.id"), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    rotulo: Mapped[str | None] = mapped_column(Text)


class ItemListaCardapio(Comum, Base):
    """O quanto cada semana pediu de cada item da lista."""

    __tablename__ = "itens_lista_cardapio"

    item_lista_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("itens_lista.id"), nullable=False
    )
    semana_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("semanas.id"), nullable=False)
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unidade: Mapped[str | None] = mapped_column(Text)
    gerado_por: Mapped[str] = mapped_column(Text, nullable=False)
