"""Identidade pelo Tailscale: o login da tailnet ligado ao nome exibido.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

Roadmap, Lista de compras, 3. O `tailscale serve` informa o login de quem
pede (`Tailscale-User-Login`); esta tabela diz como ele aparece no "quem"
("erik@exemplo.com" -> "Erik"). Login sem linha aqui aparece com o nome que
o Tailscale manda. Mesmas proteções das outras tabelas do schema.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE compras.identidades_tailscale (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          criado_em timestamptz NOT NULL DEFAULT now(),
          atualizado_em timestamptz NOT NULL DEFAULT now(),
          deleted_em timestamptz,
          -- Sempre em minúsculas: o Tailscale não garante a caixa do login.
          login text NOT NULL CHECK (login = lower(btrim(login)) AND login <> ''),
          nome text NOT NULL CHECK (btrim(nome) <> '' AND char_length(nome) <= 60)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_identidades_tailscale_login "
        "ON compras.identidades_tailscale (login) WHERE deleted_em IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_identidades_tailscale_atualizado_em "
        "ON compras.identidades_tailscale (atualizado_em)"
    )
    op.execute(
        """
        CREATE TRIGGER tg_identidades_tailscale_atualizado_em
        BEFORE UPDATE ON compras.identidades_tailscale
        FOR EACH ROW EXECUTE FUNCTION compras.fn_set_atualizado_em()
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_identidades_tailscale_auditoria
        AFTER INSERT OR UPDATE OR DELETE ON compras.identidades_tailscale
        FOR EACH ROW EXECUTE FUNCTION compras.fn_auditoria()
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_identidades_tailscale_somente_casa_compras
        BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON compras.identidades_tailscale
        FOR EACH STATEMENT EXECUTE FUNCTION compras.fn_somente_casa_compras()
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS compras.identidades_tailscale")
