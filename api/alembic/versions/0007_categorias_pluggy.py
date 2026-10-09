"""mapeamento de categorias da Pluggy

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-09

D-21. A Pluggy entrega cada transação com uma categoria própria (`categoryId`
de 8 dígitos e o nome, ex. `11000000` "Groceries"). Esta tabela liga a
categoria da Pluggy a uma `categoria` daqui, e o enriquecimento a usa depois
das regras do usuário e antes do local conhecido.

Uma linha por categoria da Pluggy entre as vivas: o id dela é único
enquanto `deleted_em` é nulo, como o `pluggy_account_id` de `contas_pluggy`.
O nome fica junto porque o id sozinho não diz nada a quem lê a tabela — e
porque a proposta inicial sai do nome, que a documentação da Pluggy publica
para os três níveis da árvore (os ids, só para o primeiro).

Caso ambíguo não ganha linha: sem mapeamento, o item vai para a revisão sem
categoria. Por isso `categoria_id` é NOT NULL — "mapeado para nada" não é um
estado que precise existir.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLS = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz,
  deleted_em timestamptz
"""


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE categorias_pluggy (
          {_BASE_COLS},
          -- `categoryId` da Pluggy: 8 dígitos, o nível no par de dígitos.
          pluggy_categoria_id text NOT NULL,
          -- `category`: a descrição em inglês que a Pluggy publica.
          pluggy_categoria_nome text NOT NULL,
          categoria_id bigint NOT NULL REFERENCES categorias (id) ON DELETE RESTRICT,
          ativo boolean NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_categorias_pluggy_pluggy_categoria_id
        ON categorias_pluggy (pluggy_categoria_id)
        WHERE deleted_em IS NULL
        """
    )
    op.execute("CREATE INDEX ix_categorias_pluggy_categoria_id ON categorias_pluggy (categoria_id)")
    op.execute("CREATE INDEX ix_categorias_pluggy_deleted_em ON categorias_pluggy (deleted_em)")

    op.execute(
        """
        CREATE TRIGGER tg_categorias_pluggy_atualizado_em
        BEFORE UPDATE ON categorias_pluggy
        FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em()
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_categorias_pluggy_auditoria
        AFTER INSERT OR UPDATE OR DELETE ON categorias_pluggy
        FOR EACH ROW EXECUTE FUNCTION fn_auditoria()
        """
    )

    # Mesmo motivo da 0003 e da 0005: o ALTER DEFAULT PRIVILEGES só alcança
    # a tabela se a role nasceu antes. O GRANT explícito tira a dependência.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'casa_insights') THEN
            GRANT SELECT ON categorias_pluggy TO casa_insights;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tg_categorias_pluggy_auditoria ON categorias_pluggy")
    op.execute("DROP TRIGGER IF EXISTS tg_categorias_pluggy_atualizado_em ON categorias_pluggy")
    op.execute("DROP INDEX IF EXISTS ix_categorias_pluggy_deleted_em")
    op.execute("DROP INDEX IF EXISTS ix_categorias_pluggy_categoria_id")
    op.execute("DROP INDEX IF EXISTS uq_categorias_pluggy_pluggy_categoria_id")
    op.execute("DROP TABLE IF EXISTS categorias_pluggy")
