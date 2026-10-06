"""observação do item de staging

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06

`ItemExtraido.observacao` existia desde a fase 5 — é onde o parser diz "isto
merece o olho humano" —, mas `importacao_itens` não tinha onde guardá-la, e
ela se perdia entre o parser e a tela de revisão. Com a sync da Pluggy (fase
5b, passo 6) a nota passou a carregar decisão: possível duplicata vinda da
própria Pluggy, encargos de fatura deduzidos e competência estimada sem a
fatura. Sem ela, o usuário veria só uma confiança baixa, sem o porquê.

Coluna anulável e aditiva: item antigo fica sem observação, e nada que já
existe muda de significado. A role read-only enxerga a coluna pelo `GRANT`
que já tem sobre a tabela.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE importacao_itens ADD COLUMN observacao text")
    op.execute(
        "COMMENT ON COLUMN importacao_itens.observacao IS "
        "'Nota do parser ou da sync para a revisão: duplicata possível, "
        "encargo deduzido, competência estimada.'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE importacao_itens DROP COLUMN IF EXISTS observacao")
