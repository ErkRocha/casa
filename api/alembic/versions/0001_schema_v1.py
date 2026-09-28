"""schema v1 — núcleo

Revision ID: 0001
Revises:
Create Date: 2026-08-06

Migration inicial. DDL explícito em vez de autogenerate porque metade do que
importa aqui — coluna gerada, índice parcial, trigger, view — o autogenerate
não escreve direito.

Nunca edite este arquivo depois de aplicado. Correção é migration nova.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _criar_enums()
    _criar_funcoes()
    _criar_tabelas()
    _criar_indices()
    _criar_triggers()
    _criar_views()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_orcamento_mes")
    op.execute("DROP VIEW IF EXISTS vw_gasto_por_pessoa")
    op.execute("DROP VIEW IF EXISTS vw_transacoes_completa")

    for tabela in (
        "auditoria",
        "orcamentos",
        "transacoes",
        "locais",
        "formas_pagamento",
        "categorias",
        "contas",
        "pessoas",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tabela} CASCADE")

    op.execute("DROP FUNCTION IF EXISTS fn_auditoria() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_set_atualizado_em() CASCADE")
    op.execute("DROP FUNCTION IF EXISTS fn_categoria_sem_ciclo() CASCADE")

    for enum in (
        "periodicidade",
        "status_item",
        "status_importacao",
        "tipo_pessoa",
        "tipo_pagamento",
        "tipo_conta",
        "tipo_transacao",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum}")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def _criar_enums() -> None:
    op.execute("CREATE TYPE tipo_transacao AS ENUM ('despesa', 'receita', 'transferencia')")
    op.execute(
        "CREATE TYPE tipo_conta AS ENUM "
        "('corrente', 'poupanca', 'carteira', 'investimento', 'cartao')"
    )
    op.execute(
        "CREATE TYPE tipo_pagamento AS ENUM "
        "('credito', 'debito', 'pix', 'dinheiro', 'boleto', 'transferencia')"
    )
    op.execute("CREATE TYPE tipo_pessoa AS ENUM ('individual', 'conjunta')")
    # Os dois abaixo só são usados na fase 5, mas o tipo nasce junto do resto
    # para não haver migration de enum solta no meio da ingestão.
    op.execute(
        "CREATE TYPE status_importacao AS ENUM "
        "('processando', 'aguardando_revisao', 'concluida', 'erro', 'cancelada')"
    )
    op.execute("CREATE TYPE status_item AS ENUM ('pendente', 'aprovado', 'rejeitado', 'duplicado')")
    op.execute(
        "CREATE TYPE periodicidade AS ENUM "
        "('mensal', 'bimestral', 'trimestral', 'semestral', 'anual')"
    )


# ---------------------------------------------------------------------------
# Funções
# ---------------------------------------------------------------------------


def _criar_funcoes() -> None:
    op.execute(
        """
        CREATE FUNCTION fn_set_atualizado_em() RETURNS trigger AS $$
        BEGIN
          NEW.atualizado_em := now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Trigger, e não código de aplicação: agentes escrevem por caminhos
    # diferentes e nem todos passam pelo ORM (D-06).
    op.execute(
        """
        CREATE FUNCTION fn_auditoria() RETURNS trigger AS $$
        DECLARE
          v_autor text;
        BEGIN
          v_autor := coalesce(nullif(current_setting('app.autor', true), ''), 'desconhecido');

          IF TG_OP = 'INSERT' THEN
            INSERT INTO auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, NEW.id, TG_OP, NULL, to_jsonb(NEW), v_autor);
            RETURN NEW;

          ELSIF TG_OP = 'UPDATE' THEN
            INSERT INTO auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, NEW.id, TG_OP, to_jsonb(OLD), to_jsonb(NEW), v_autor);
            RETURN NEW;

          ELSE
            INSERT INTO auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, OLD.id, TG_OP, to_jsonb(OLD), NULL, v_autor);
            RETURN OLD;
          END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Profundidade prática de categorias é 2. Exigir que o pai seja raiz
    # entrega isso e mata ciclo de tabela junto — não há como fechar um laço
    # se todo pai tem `categoria_pai_id` nulo.
    op.execute(
        """
        CREATE FUNCTION fn_categoria_sem_ciclo() RETURNS trigger AS $$
        DECLARE
          v_avo bigint;
        BEGIN
          IF NEW.categoria_pai_id IS NULL THEN
            RETURN NEW;
          END IF;

          IF NEW.categoria_pai_id = NEW.id THEN
            RAISE EXCEPTION 'categoria nao pode ser pai de si mesma (id=%)', NEW.id;
          END IF;

          SELECT categoria_pai_id INTO v_avo
          FROM categorias WHERE id = NEW.categoria_pai_id;

          IF v_avo IS NOT NULL THEN
            RAISE EXCEPTION
              'hierarquia de categorias tem no maximo 2 niveis (pai % ja e subcategoria)',
              NEW.categoria_pai_id;
          END IF;

          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------

#: Colunas comuns a toda tabela de domínio editável.
_BASE_COLS = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz,
  deleted_em timestamptz
"""


def _criar_tabelas() -> None:
    op.execute(
        f"""
        CREATE TABLE pessoas (
          {_BASE_COLS},
          nome text NOT NULL,
          tipo tipo_pessoa NOT NULL DEFAULT 'individual',
          ativo boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE contas (
          {_BASE_COLS},
          nome text NOT NULL,
          tipo tipo_conta NOT NULL,
          -- NULL = conta conjunta
          titular_id bigint REFERENCES pessoas (id) ON DELETE RESTRICT,
          saldo_inicial numeric(12, 2) NOT NULL DEFAULT 0,
          ativo boolean NOT NULL DEFAULT true
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE categorias (
          {_BASE_COLS},
          nome text NOT NULL,
          -- NULL = categoria raiz
          categoria_pai_id bigint REFERENCES categorias (id) ON DELETE RESTRICT,
          tipo tipo_transacao NOT NULL,
          cor varchar(32),
          ativo boolean NOT NULL DEFAULT true,
          CONSTRAINT ck_categorias_categoria_nao_e_transferencia
            CHECK (tipo <> 'transferencia')
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE formas_pagamento (
          {_BASE_COLS},
          apelido text NOT NULL,
          tipo tipo_pagamento NOT NULL,
          conta_id bigint REFERENCES contas (id) ON DELETE RESTRICT,
          titular_id bigint REFERENCES pessoas (id) ON DELETE RESTRICT,
          dia_fechamento smallint,
          dia_vencimento smallint,
          ativo boolean NOT NULL DEFAULT true,
          CONSTRAINT ck_formas_pagamento_dia_fechamento_valido
            CHECK (dia_fechamento IS NULL OR dia_fechamento BETWEEN 1 AND 31),
          CONSTRAINT ck_formas_pagamento_dia_vencimento_valido
            CHECK (dia_vencimento IS NULL OR dia_vencimento BETWEEN 1 AND 31)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE locais (
          {_BASE_COLS},
          nome text NOT NULL,
          -- upper + sem acento, para matching na ingestão
          nome_normalizado text NOT NULL,
          cidade text,
          cnpj varchar(18),
          categoria_padrao_id bigint REFERENCES categorias (id) ON DELETE SET NULL
        )
        """
    )

    # `auditoria` antes de `transacoes` porque o trigger de auditoria insere
    # nela. Não tem soft delete: log não se apaga.
    op.execute(
        """
        CREATE TABLE auditoria (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          criado_em timestamptz NOT NULL DEFAULT now(),
          tabela text NOT NULL,
          registro_id bigint NOT NULL,
          acao text NOT NULL,
          dados_antes jsonb,
          dados_depois jsonb,
          autor text NOT NULL,
          ocorrido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE transacoes (
          {_BASE_COLS},
          data date NOT NULL,
          -- 1º dia do mês de referência (D-02)
          competencia date NOT NULL,
          -- sempre positivo; o sinal vem de `tipo`
          valor numeric(12, 2) NOT NULL,
          tipo tipo_transacao NOT NULL,
          descricao text NOT NULL,
          -- texto cru do extrato, imutável (ver trigger abaixo)
          descricao_original text,

          -- NULL = gasto conjunto (D-03)
          pessoa_id bigint REFERENCES pessoas (id) ON DELETE RESTRICT,
          categoria_id bigint REFERENCES categorias (id) ON DELETE RESTRICT,
          forma_pagamento_id bigint REFERENCES formas_pagamento (id) ON DELETE RESTRICT,
          conta_id bigint REFERENCES contas (id) ON DELETE RESTRICT,
          local_id bigint REFERENCES locais (id) ON DELETE SET NULL,
          -- FK para `importacoes` entra na fase 5
          importacao_id bigint,

          conta_origem_id bigint REFERENCES contas (id) ON DELETE RESTRICT,
          conta_destino_id bigint REFERENCES contas (id) ON DELETE RESTRICT,

          parcela_num smallint,
          parcela_total smallint,
          grupo_parcelamento_id uuid,

          desconto_total numeric(12, 2) NOT NULL DEFAULT 0,
          observacao text,

          -- Coluna gerada: o Postgres só aceita expressão IMMUTABLE aqui, e
          -- duas armadilhas moram nesta linha.
          --
          -- 1. `data::text` depende de DateStyle e é apenas STABLE — daí a
          --    subtração de uma data fixa, que devolve inteiro.
          -- 2. `sha256()` precisa de bytea, e a única ponte text→bytea é
          --    `convert_to()`, que é STABLE porque depende da codificação do
          --    banco. Não há cast imutável de text para bytea, então sha256
          --    está fora de alcance aqui. `md5(text)` é IMMUTABLE e resolve:
          --    isto é impressão digital de deduplicação num banco doméstico,
          --    não fronteira de segurança.
          hash_dedup text GENERATED ALWAYS AS (
            md5(
              (data - DATE '1970-01-01')::text || '|' ||
              valor::text || '|' ||
              coalesce(descricao_original, '') || '|' ||
              coalesce(forma_pagamento_id::text, '') || '|' ||
              coalesce(parcela_num::text, '')
            )
          ) STORED,

          CONSTRAINT ck_transacoes_valor_positivo CHECK (valor > 0),
          CONSTRAINT ck_transacoes_desconto_nao_negativo CHECK (desconto_total >= 0),
          CONSTRAINT ck_transacoes_competencia_e_dia_primeiro
            CHECK (competencia = date_trunc('month', competencia)::date),
          CONSTRAINT ck_transacoes_transferencia_coerente CHECK (
            (tipo = 'transferencia'
             AND conta_origem_id IS NOT NULL
             AND conta_destino_id IS NOT NULL
             AND conta_origem_id <> conta_destino_id
             AND categoria_id IS NULL)
            OR
            (tipo <> 'transferencia'
             AND conta_origem_id IS NULL
             AND conta_destino_id IS NULL)
          ),
          CONSTRAINT ck_transacoes_parcela_coerente CHECK (
            (parcela_num IS NULL AND parcela_total IS NULL)
            OR (parcela_num >= 1 AND parcela_total >= 1 AND parcela_num <= parcela_total)
          )
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE orcamentos (
          {_BASE_COLS},
          categoria_id bigint NOT NULL REFERENCES categorias (id) ON DELETE RESTRICT,
          competencia date NOT NULL,
          valor_meta numeric(12, 2) NOT NULL,
          CONSTRAINT ck_orcamentos_meta_positiva CHECK (valor_meta > 0),
          CONSTRAINT ck_orcamentos_competencia_e_dia_primeiro
            CHECK (competencia = date_trunc('month', competencia)::date)
        )
        """
    )


# ---------------------------------------------------------------------------
# Índices
# ---------------------------------------------------------------------------


def _criar_indices() -> None:
    for tabela in ("pessoas", "contas", "categorias", "formas_pagamento", "locais", "orcamentos"):
        op.execute(f"CREATE INDEX ix_{tabela}_deleted_em ON {tabela} (deleted_em)")

    # Unique de categoria: NULL não colide com NULL no Postgres, então raiz e
    # subcategoria precisam de índices separados.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_categorias_pai_nome ON categorias (categoria_pai_id, nome)
        WHERE categoria_pai_id IS NOT NULL AND deleted_em IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_categorias_raiz_nome ON categorias (nome)
        WHERE categoria_pai_id IS NULL AND deleted_em IS NULL
        """
    )

    op.execute("CREATE INDEX ix_locais_nome_normalizado ON locais (nome_normalizado)")

    op.execute("CREATE INDEX ix_transacoes_data ON transacoes (data)")
    op.execute("CREATE INDEX ix_transacoes_competencia ON transacoes (competencia)")
    op.execute("CREATE INDEX ix_transacoes_categoria_id ON transacoes (categoria_id)")
    op.execute("CREATE INDEX ix_transacoes_pessoa_id ON transacoes (pessoa_id)")
    op.execute("CREATE INDEX ix_transacoes_local_id ON transacoes (local_id)")
    op.execute("CREATE INDEX ix_transacoes_forma_pagamento_id ON transacoes (forma_pagamento_id)")
    op.execute("CREATE INDEX ix_transacoes_tipo ON transacoes (tipo)")
    op.execute("CREATE INDEX ix_transacoes_deleted_em ON transacoes (deleted_em)")

    # O analytics quase sempre filtra competência de linha viva que não é
    # transferência — esse é o índice que segura a tela.
    op.execute(
        """
        CREATE INDEX ix_transacoes_analytics ON transacoes (competencia, tipo, pessoa_id)
        WHERE deleted_em IS NULL
        """
    )

    # O único parcial de deduplicação (D-07). Vale só para linha viva:
    # reimportar algo que foi excluído tem que passar.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_transacoes_dedup ON transacoes (hash_dedup)
        WHERE deleted_em IS NULL
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_orcamentos_categoria_competencia
        ON orcamentos (categoria_id, competencia)
        WHERE deleted_em IS NULL
        """
    )

    op.execute("CREATE INDEX ix_auditoria_tabela_registro ON auditoria (tabela, registro_id)")
    op.execute("CREATE INDEX ix_auditoria_ocorrido_em ON auditoria (ocorrido_em DESC)")


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------

_TABELAS_AUDITADAS = (
    "pessoas",
    "contas",
    "categorias",
    "formas_pagamento",
    "locais",
    "transacoes",
    "orcamentos",
)


def _criar_triggers() -> None:
    for tabela in _TABELAS_AUDITADAS:
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_atualizado_em
            BEFORE UPDATE ON {tabela}
            FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_auditoria
            AFTER INSERT OR UPDATE OR DELETE ON {tabela}
            FOR EACH ROW EXECUTE FUNCTION fn_auditoria()
            """
        )

    op.execute(
        """
        CREATE TRIGGER tg_categorias_sem_ciclo
        BEFORE INSERT OR UPDATE OF categoria_pai_id ON categorias
        FOR EACH ROW EXECUTE FUNCTION fn_categoria_sem_ciclo()
        """
    )

    # `descricao_original` é o texto cru do extrato (regra 11). Edição do
    # usuário vai em `descricao`; aqui o banco recusa a alteração em vez de
    # confiar que todo caminho de escrita lembrou disso.
    op.execute(
        """
        CREATE FUNCTION fn_descricao_original_imutavel() RETURNS trigger AS $$
        BEGIN
          IF OLD.descricao_original IS NOT NULL
             AND NEW.descricao_original IS DISTINCT FROM OLD.descricao_original THEN
            RAISE EXCEPTION 'descricao_original e imutavel (transacao id=%)', OLD.id;
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_transacoes_descricao_original_imutavel
        BEFORE UPDATE ON transacoes
        FOR EACH ROW EXECUTE FUNCTION fn_descricao_original_imutavel()
        """
    )


# ---------------------------------------------------------------------------
# Views de leitura
# ---------------------------------------------------------------------------


def _criar_views() -> None:
    # Transação com os nomes já resolvidos por join. É o que a listagem e os
    # filtros da tela de transações consomem.
    op.execute(
        """
        CREATE VIEW vw_transacoes_completa AS
        SELECT
          t.id,
          t.data,
          t.competencia,
          t.valor,
          t.tipo,
          t.descricao,
          t.descricao_original,
          t.observacao,
          t.parcela_num,
          t.parcela_total,
          t.desconto_total,
          t.criado_em,
          t.atualizado_em,

          t.pessoa_id,
          -- NULL vira o rótulo do balde conjunto, para o front não precisar
          -- decidir isso em cada tela.
          coalesce(p.nome, 'Conjunto') AS pessoa_nome,

          t.categoria_id,
          c.nome AS categoria_nome,
          c.categoria_pai_id,
          cp.nome AS categoria_pai_nome,
          coalesce(cp.nome || ' › ' || c.nome, c.nome) AS categoria_caminho,
          coalesce(cp.id, c.id) AS categoria_raiz_id,

          t.forma_pagamento_id,
          fp.apelido AS forma_pagamento_apelido,
          fp.tipo AS forma_pagamento_tipo,

          t.local_id,
          l.nome AS local_nome,

          t.conta_id,
          t.conta_origem_id,
          t.conta_destino_id
        FROM transacoes t
        LEFT JOIN pessoas p ON p.id = t.pessoa_id
        LEFT JOIN categorias c ON c.id = t.categoria_id
        LEFT JOIN categorias cp ON cp.id = c.categoria_pai_id
        LEFT JOIN formas_pagamento fp ON fp.id = t.forma_pagamento_id
        LEFT JOIN locais l ON l.id = t.local_id
        WHERE t.deleted_em IS NULL
        """
    )

    # Os três baldes que somam o total exato, sem sobreposição possível
    # (D-03). Transferência fica de fora: pagar fatura não é despesa nova.
    op.execute(
        """
        CREATE VIEW vw_gasto_por_pessoa AS
        SELECT
          t.competencia,
          coalesce(t.pessoa_id::text, 'conjunto') AS balde,
          coalesce(p.nome, 'Conjunto') AS balde_nome,
          sum(t.valor) AS total
        FROM transacoes t
        LEFT JOIN pessoas p ON p.id = t.pessoa_id
        WHERE t.deleted_em IS NULL
          AND t.tipo = 'despesa'
        GROUP BY t.competencia, coalesce(t.pessoa_id::text, 'conjunto'), coalesce(p.nome, 'Conjunto')
        """
    )

    # Meta contra realizado por categoria. O realizado soma a categoria raiz
    # inteira, incluindo as subcategorias.
    op.execute(
        """
        CREATE VIEW vw_orcamento_mes AS
        SELECT
          o.id AS orcamento_id,
          o.competencia,
          o.categoria_id,
          cat.nome AS categoria_nome,
          o.valor_meta,
          coalesce(r.realizado, 0) AS realizado,
          CASE
            WHEN o.valor_meta = 0 THEN 0
            ELSE round(coalesce(r.realizado, 0) / o.valor_meta * 100, 1)
          END AS percentual
        FROM orcamentos o
        JOIN categorias cat ON cat.id = o.categoria_id
        LEFT JOIN LATERAL (
          SELECT sum(t.valor) AS realizado
          FROM transacoes t
          JOIN categorias c ON c.id = t.categoria_id
          WHERE t.deleted_em IS NULL
            AND t.tipo = 'despesa'
            AND t.competencia = o.competencia
            AND coalesce(c.categoria_pai_id, c.id) = o.categoria_id
        ) r ON true
        WHERE o.deleted_em IS NULL
        """
    )
