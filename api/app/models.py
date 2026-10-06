"""Models SQLAlchemy do núcleo v1.

Espelham `docs/modelo-dados.md`. Regras que aparecem aqui e não são
negociáveis:

* dinheiro é ``Numeric(12, 2)`` — nunca float;
* ``pessoa_id`` nulo significa gasto conjunto, e não "sem dono" (D-03);
* ``descricao_original`` é o texto cru do extrato e é imutável;
* remoção é ``deleted_em``, nunca DELETE físico.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import DATERANGE, JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, IdMixin, SoftDeleteMixin, TimestampMixin, pg_enum
from app.enums import (
    StatusImportacao,
    StatusItem,
    TipoConta,
    TipoPagamento,
    TipoPessoa,
    TipoTransacao,
)

# --------------------------------------------------------------------------
# Helpers de tipo
# --------------------------------------------------------------------------


#: Dinheiro. Nunca float, real ou double precision.
Money = Numeric(12, 2)
#: Quantidade — 3 casas cobrem 1,250 kg e 42,318 L.
Quantidade = Numeric(12, 3)

#: Expressão da coluna gerada `hash_dedup`.
#:
#: Tem que casar exatamente com a da migration 0001. Só funções IMMUTABLE
#: cabem numa coluna gerada, e duas coisas tropeçam nisso:
#:
#: * ``data::text`` depende de DateStyle e é apenas STABLE — por isso a
#:   subtração de uma data fixa, que devolve inteiro;
#: * ``sha256()`` exige bytea, e a única ponte text→bytea é ``convert_to()``,
#:   que é STABLE. Sem cast imutável de text para bytea, sha256 não cabe aqui.
#:   ``md5(text)`` é IMMUTABLE — e isto é impressão digital de deduplicação
#:   num banco doméstico, não fronteira de segurança.
HASH_DEDUP_EXPR = """
md5(
  (data - DATE '1970-01-01')::text || '|' ||
  valor::text || '|' ||
  coalesce(descricao_original, '') || '|' ||
  coalesce(forma_pagamento_id::text, '') || '|' ||
  coalesce(parcela_num::text, '')
)
""".strip()


# --------------------------------------------------------------------------
# Cadastros
# --------------------------------------------------------------------------


class Pessoa(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "pessoas"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoPessoa] = mapped_column(
        pg_enum(TipoPessoa, "tipo_pessoa"), nullable=False, default=TipoPessoa.INDIVIDUAL
    )
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Conta(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Onde o dinheiro está. Sem ela não há conciliação de saldo (D-05)."""

    __tablename__ = "contas"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoConta] = mapped_column(pg_enum(TipoConta, "tipo_conta"), nullable=False)
    #: Nulo = conta conjunta.
    titular_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pessoas.id", ondelete="RESTRICT")
    )
    saldo_inicial: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    titular: Mapped[Pessoa | None] = relationship(lazy="joined")


class Categoria(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Hierárquica por auto-relacionamento. Profundidade prática: 2 níveis."""

    __tablename__ = "categorias"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    #: Nulo = categoria raiz.
    categoria_pai_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT")
    )
    tipo: Mapped[TipoTransacao] = mapped_column(
        pg_enum(TipoTransacao, "tipo_transacao"), nullable=False
    )
    #: Usada nos gráficos. Hex ou nome de token do front.
    cor: Mapped[str | None] = mapped_column(String(32))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    categoria_pai: Mapped["Categoria | None"] = relationship(remote_side="Categoria.id")

    __table_args__ = (
        # Transferência não tem categoria — a restrição está no check de
        # `transacoes`; aqui garantimos que ninguém cadastre uma.
        CheckConstraint("tipo <> 'transferencia'", name="categoria_nao_e_transferencia"),
    )


class FormaPagamento(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "formas_pagamento"

    apelido: Mapped[str] = mapped_column(Text, nullable=False)
    tipo: Mapped[TipoPagamento] = mapped_column(
        pg_enum(TipoPagamento, "tipo_pagamento"), nullable=False
    )
    #: De onde sai o dinheiro.
    conta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT")
    )
    titular_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pessoas.id", ondelete="RESTRICT")
    )
    #: Só cartão de crédito.
    dia_fechamento: Mapped[int | None] = mapped_column(SmallInteger)
    dia_vencimento: Mapped[int | None] = mapped_column(SmallInteger)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    conta: Mapped[Conta | None] = relationship(lazy="joined")
    titular: Mapped[Pessoa | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "dia_fechamento is null or dia_fechamento between 1 and 31",
            name="dia_fechamento_valido",
        ),
        CheckConstraint(
            "dia_vencimento is null or dia_vencimento between 1 and 31",
            name="dia_vencimento_valido",
        ),
    )


class Local(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "locais"

    nome: Mapped[str] = mapped_column(Text, nullable=False)
    #: Upper sem acento — é por aqui que a ingestão casa o estabelecimento.
    nome_normalizado: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    cidade: Mapped[str | None] = mapped_column(Text)
    cnpj: Mapped[str | None] = mapped_column(String(18))
    #: Auto-categorização na ingestão (fase 5).
    categoria_padrao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="SET NULL")
    )

    categoria_padrao: Mapped[Categoria | None] = relationship(lazy="joined")


# --------------------------------------------------------------------------
# Transações
# --------------------------------------------------------------------------


class Transacao(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Coração do sistema. Uma linha por movimento."""

    __tablename__ = "transacoes"

    #: Data do fato.
    data: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: 1º dia do mês de referência. Compra de 28/07 pode cair na fatura de
    #: agosto — sem isso o relatório mensal não bate com o que se paga (D-02).
    competencia: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    #: Sempre positivo; o sinal vem de `tipo`.
    valor: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tipo: Mapped[TipoTransacao] = mapped_column(
        pg_enum(TipoTransacao, "tipo_transacao"), nullable=False, index=True
    )
    #: Editável pelo usuário.
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    #: Texto cru do extrato. Imutável — edição do usuário vai em `descricao`.
    descricao_original: Mapped[str | None] = mapped_column(Text)

    #: **Nulo = gasto conjunto.** Responde quem gastou, nunca quem se
    #: beneficiou (D-03).
    pessoa_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pessoas.id", ondelete="RESTRICT"), index=True
    )
    categoria_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"), index=True
    )
    forma_pagamento_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("formas_pagamento.id", ondelete="RESTRICT"), index=True
    )
    conta_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT")
    )
    local_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("locais.id", ondelete="SET NULL"), index=True
    )
    #: Nulo = lançamento manual. FK criada na fase 5, junto de `importacoes`.
    importacao_id: Mapped[int | None] = mapped_column(BigInteger)

    #: Só quando tipo = transferencia.
    conta_origem_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT")
    )
    conta_destino_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT")
    )

    parcela_num: Mapped[int | None] = mapped_column(SmallInteger)
    parcela_total: Mapped[int | None] = mapped_column(SmallInteger)
    #: Liga as parcelas entre si.
    grupo_parcelamento_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True))

    #: Cupom aplicado na nota inteira.
    desconto_total: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    observacao: Mapped[str | None] = mapped_column(Text)

    #: Coluna gerada. Protege a promoção da ingestão: reimportar o mesmo PDF
    #: ou aprovar duas vezes esbarra no índice único parcial (D-07).
    hash_dedup: Mapped[str] = mapped_column(
        Text, Computed(HASH_DEDUP_EXPR, persisted=True), nullable=False
    )

    pessoa: Mapped[Pessoa | None] = relationship(lazy="joined")
    categoria: Mapped[Categoria | None] = relationship(lazy="joined", foreign_keys=[categoria_id])
    forma_pagamento: Mapped[FormaPagamento | None] = relationship(lazy="joined")
    local: Mapped[Local | None] = relationship(lazy="joined")

    __table_args__ = (
        CheckConstraint("valor > 0", name="valor_positivo"),
        CheckConstraint("desconto_total >= 0", name="desconto_nao_negativo"),
        CheckConstraint(
            "competencia = date_trunc('month', competencia)::date",
            name="competencia_e_dia_primeiro",
        ),
        # Transferência exige origem e destino, e não tem categoria.
        CheckConstraint(
            """
            (tipo = 'transferencia'
             and conta_origem_id is not null
             and conta_destino_id is not null
             and conta_origem_id <> conta_destino_id
             and categoria_id is null)
            or
            (tipo <> 'transferencia'
             and conta_origem_id is null
             and conta_destino_id is null)
            """,
            name="transferencia_coerente",
        ),
        CheckConstraint(
            """
            (parcela_num is null and parcela_total is null)
            or (parcela_num >= 1 and parcela_total >= 1 and parcela_num <= parcela_total)
            """,
            name="parcela_coerente",
        ),
        # O único parcial de deduplicação. Só vale para linha viva: reimportar
        # algo que foi excluído tem que passar.
        Index(
            "uq_transacoes_dedup",
            "hash_dedup",
            unique=True,
            postgresql_where=text("deleted_em IS NULL"),
        ),
    )


class Orcamento(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "orcamentos"

    categoria_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="RESTRICT"), nullable=False
    )
    #: Mês de referência — dia 1º.
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    valor_meta: Mapped[Decimal] = mapped_column(Money, nullable=False)

    categoria: Mapped[Categoria] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("categoria_id", "competencia", name="uq_orcamentos_categoria_competencia"),
        CheckConstraint("valor_meta > 0", name="meta_positiva"),
        CheckConstraint(
            "competencia = date_trunc('month', competencia)::date",
            name="competencia_e_dia_primeiro",
        ),
    )


class Auditoria(IdMixin, Base):
    """Preenchida por trigger, nunca por aplicação (D-06)."""

    __tablename__ = "auditoria"

    tabela: Mapped[str] = mapped_column(Text, nullable=False)
    registro_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    #: INSERT / UPDATE / DELETE.
    acao: Mapped[str] = mapped_column(Text, nullable=False)
    dados_antes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dados_depois: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Usuário ou nome do agente, vindo de `current_setting('app.autor')`.
    autor: Mapped[str] = mapped_column(Text, nullable=False)
    ocorrido_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_auditoria_tabela_registro", "tabela", "registro_id"),)


# --------------------------------------------------------------------------
# Ingestão (fase 5)
# --------------------------------------------------------------------------


class Importacao(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Um arquivo processado."""

    __tablename__ = "importacoes"

    arquivo_nome: Mapped[str] = mapped_column(Text, nullable=False)
    #: SHA-256 do arquivo. Barra reimportação do mesmo PDF (D-07).
    hash_arquivo: Mapped[str] = mapped_column(Text, nullable=False)
    #: O PDF original, para conferir a transação contra o comprovante meses
    #: depois. Nulo nas importações anteriores à migration 0004.
    #:
    #: `deferred`: são centenas de KB por linha, e nenhuma tela de listagem
    #: precisa disso. Sem o defer, abrir a lista de importações carregaria
    #: todos os PDFs para a memória a cada request.
    arquivo_conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, deferred=True)
    arquivo_tipo: Mapped[str | None] = mapped_column(Text)
    #: "nubank_fatura", "nubank_extrato".
    origem: Mapped[str | None] = mapped_column(Text)
    periodo_inicio: Mapped[date | None] = mapped_column(Date)
    periodo_fim: Mapped[date | None] = mapped_column(Date)
    status: Mapped[StatusImportacao] = mapped_column(
        pg_enum(StatusImportacao, "status_importacao"),
        nullable=False,
        default=StatusImportacao.PROCESSANDO,
    )
    parser_usado: Mapped[str | None] = mapped_column(Text)
    #: Versão do prompt, quando o LLM entrar (D-12). Nulo no determinístico.
    prompt_versao: Mapped[str | None] = mapped_column(Text)
    total_itens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    itens_aprovados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    custo_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    #: Total que o próprio documento declara. É o gabarito da extração — sem
    #: ele não dá para saber se o parser perdeu linha.
    total_declarado: Mapped[Decimal | None] = mapped_column(Money)
    erro_mensagem: Mapped[str | None] = mapped_column(Text)

    itens: Mapped[list["ImportacaoItem"]] = relationship(
        back_populates="importacao", cascade="all, delete-orphan"
    )


class ImportacaoItem(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Staging. Nada aqui afeta relatório.

    O agente de ingestão escreve aqui e nunca em `transacoes` (regra 5). Quem
    promove é o usuário, pelo painel.
    """

    __tablename__ = "importacao_itens"

    importacao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("importacoes.id", ondelete="CASCADE"), nullable=False
    )
    #: A linha exata do PDF, para conferir contra o documento.
    linha_bruta: Mapped[str] = mapped_column(Text, nullable=False)
    linha_num: Mapped[int | None] = mapped_column(Integer)

    data: Mapped[date | None] = mapped_column(Date)
    valor: Mapped[Decimal | None] = mapped_column(Money)
    descricao_original: Mapped[str | None] = mapped_column(Text)

    #: Sugestões — todas anuláveis. O parser preenche o que consegue; o resto
    #: o usuário resolve na tela de revisão.
    tipo_sugerido: Mapped[TipoTransacao | None] = mapped_column(
        pg_enum(TipoTransacao, "tipo_transacao")
    )
    competencia_sugerida: Mapped[date | None] = mapped_column(Date)
    categoria_sugerida_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="SET NULL")
    )
    local_sugerido_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("locais.id", ondelete="SET NULL")
    )
    pessoa_sugerida_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pessoas.id", ondelete="SET NULL")
    )
    forma_pagamento_sugerida_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("formas_pagamento.id", ondelete="SET NULL")
    )

    confianca: Mapped[Decimal | None] = mapped_column(Numeric(3, 2))
    #: "parser" | "regra" | "alias" | "llm".
    origem_sugestao: Mapped[str | None] = mapped_column(Text)

    status: Mapped[StatusItem] = mapped_column(
        pg_enum(StatusItem, "status_item"), nullable=False, default=StatusItem.PENDENTE
    )
    #: Preenchido ao aprovar. É o elo entre staging e o dado real.
    transacao_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transacoes.id", ondelete="SET NULL")
    )
    motivo_rejeicao: Mapped[str | None] = mapped_column(Text)
    #: Nota do parser ou da sync para a revisão (0006): possível duplicata,
    #: encargo deduzido, competência estimada.
    observacao: Mapped[str | None] = mapped_column(Text)
    #: Id da transação na origem externa (Pluggy, D-16). Nulo para PDF.
    #:
    #: Único entre linhas vivas em **qualquer status**: item rejeitado continua
    #: bloqueando, senão voltaria na sync seguinte.
    id_externo: Mapped[str | None] = mapped_column(Text)

    importacao: Mapped[Importacao] = relationship(back_populates="itens")

    __table_args__ = (
        Index(
            "uq_importacao_itens_id_externo",
            "id_externo",
            unique=True,
            postgresql_where=text("id_externo IS NOT NULL AND deleted_em IS NULL"),
        ),
    )


class ContaPluggy(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Liga uma conta da Pluggy a uma `conta` daqui (D-16).

    Não tem `pessoa_id`: a pessoa sai de `contas.titular_id`. Conta da Pluggy
    sem mapeamento é ignorada pela sync, nunca adivinhada.
    """

    __tablename__ = "contas_pluggy"

    #: A conexão (item) na Pluggy. Uma conexão expõe várias contas.
    pluggy_item_id: Mapped[str] = mapped_column(Text, nullable=False)
    pluggy_account_id: Mapped[str] = mapped_column(Text, nullable=False)
    conta_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contas.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: Forma padrão dos itens desta conta. Obrigatória: entra no `hash_dedup`
    #: de `transacoes` e separa cartão de débito em conta.
    forma_pagamento_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("formas_pagamento.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    #: A partir desta data a Pluggy é a origem da conta; antes, o PDF.
    sincronizar_desde: Mapped[date] = mapped_column(Date, nullable=False)
    ultimo_sync_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    conta: Mapped[Conta] = relationship(lazy="joined")
    forma_pagamento: Mapped[FormaPagamento] = relationship(lazy="joined")

    __table_args__ = (
        Index(
            "uq_contas_pluggy_pluggy_account_id",
            "pluggy_account_id",
            unique=True,
            postgresql_where=text("deleted_em IS NULL"),
        ),
    )


class RegraCategorizacao(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Correção do usuário vira regra (D-09).

    O enriquecimento consulta regras primeiro — exatas e gratuitas — e só
    manda para o LLM o que sobrou.
    """

    __tablename__ = "regras_categorizacao"

    padrao: Mapped[str] = mapped_column(Text, nullable=False)
    #: "contem" | "regex" | "exato".
    tipo_match: Mapped[str] = mapped_column(Text, nullable=False, default="contem")
    categoria_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("categorias.id", ondelete="CASCADE")
    )
    local_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("locais.id", ondelete="CASCADE")
    )
    pessoa_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("pessoas.id", ondelete="CASCADE")
    )
    #: Menor roda primeiro.
    prioridade: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    #: "usuario" | "correcao_automatica".
    criada_por: Mapped[str] = mapped_column(Text, nullable=False, default="usuario")
    #: Quantas vezes já acertou — correção reforça em vez de duplicar.
    acertos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Relatorio(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Fechamento do mês em texto, com os números que o produziram.

    `dados_base` não é redundância: as transações continuam editáveis depois
    que o relatório foi escrito, então recalcular não reproduz o que o modelo
    viu. Sem a cópia, qualquer afirmação do texto vira palavra contra palavra.
    """

    __tablename__ = "relatorios"

    #: Sempre dia 1º — mês de referência (ou 1º de janeiro, no anual).
    competencia: Mapped[date] = mapped_column(Date, nullable=False)
    #: "mensal" | "anual" | "avulso".
    tipo: Mapped[str] = mapped_column(Text, nullable=False, default="mensal")
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    dados_base: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    #: Janela de competências considerada, como `[inicio, fim)`.
    periodo_dados: Mapped[Any | None] = mapped_column(DATERANGE)
    #: Nome do arquivo de prompt, ex. "relatorio_mensal_v1" (regra 9).
    prompt_versao: Mapped[str] = mapped_column(Text, nullable=False)
    #: Telemetria da execução: backend, modelo, tentativas, duração (D-12).
    execucao: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        CheckConstraint("tipo IN ('mensal', 'anual', 'avulso')", name="tipo_valido"),
        CheckConstraint(
            "competencia = date_trunc('month', competencia)::date",
            name="competencia_e_dia_primeiro",
        ),
        CheckConstraint("length(btrim(conteudo)) > 0", name="conteudo_nao_vazio"),
        Index(
            "uq_relatorios_competencia_tipo",
            "competencia",
            "tipo",
            unique=True,
            postgresql_where=text("deleted_em IS NULL"),
        ),
    )
