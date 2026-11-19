"""marca de despesa lançada pela nota e ponteiro de substituição

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-19

D-33, "Lançar despesa pela nota". Duas colunas em `transacoes`:

* `lancada_pela_nota boolean NOT NULL DEFAULT false`: a despesa foi criada
  pelo `compras` ("lançar despesa pela nota"), e não veio de extrato nem do
  banco. A sync a usa para pôr na revisão, como possível duplicata, o item da
  Pluggy com a mesma data, valor e forma de pagamento.
* `substituida_por_id bigint NULL REFERENCES transacoes (id) ON DELETE
  RESTRICT`: na lançada pela nota que a revisão juntou com a do banco, aponta
  para a do banco. A transação continua apagada (soft delete); o ponteiro
  deixa o `compras` passar a ligação da nota para a substituta.

Nenhuma view muda: `vw_transacoes_completa` não expõe as colunas novas.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE transacoes ADD COLUMN lancada_pela_nota boolean NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE transacoes ADD COLUMN substituida_por_id bigint "
        "REFERENCES transacoes (id) ON DELETE RESTRICT"
    )
    op.execute("CREATE INDEX ix_transacoes_substituida_por_id ON transacoes (substituida_por_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_transacoes_substituida_por_id")
    op.execute("ALTER TABLE transacoes DROP COLUMN IF EXISTS substituida_por_id")
    op.execute("ALTER TABLE transacoes DROP COLUMN IF EXISTS lancada_pela_nota")
