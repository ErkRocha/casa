"""compras pendentes do cartão, só para exibição

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05

D-28. A compra de cartão que a Pluggy ainda entrega `PENDING` deixa de entrar
em `importacao_itens` e `transacoes` (D-23) e passa a ser só exibida. Esta
tabela guarda a cópia do que a Pluggy mostra agora: a cada sync, as linhas de
cada conta lida sem erro são substituídas inteiras.

Exceção explícita à regra 2 (sem DELETE físico): é uma cópia descartável, não
um registro da casa. Por isso não tem `deleted_em`, `atualizado_em` nem
trigger de auditoria. O que a sync leu fica no comprovante da importação.

`id_externo` é único: é o id da transação na Pluggy, que se mantém quando o
banco confirma (a compra chega `POSTED` com o mesmo id e a linha daqui sai).

Sem GRANT para a role de insights: a pendente não entra em insights (D-28).
O default privilege de `casa_financas` já cobre o que for preciso.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE pluggy_pendentes (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          criado_em timestamptz NOT NULL DEFAULT now(),
          -- Id da transação na Pluggy; igual ao `id_externo` da versão POSTED.
          id_externo text NOT NULL,
          conta_pluggy_id bigint NOT NULL REFERENCES contas_pluggy (id) ON DELETE CASCADE,
          forma_pagamento_id bigint NOT NULL REFERENCES formas_pagamento (id) ON DELETE RESTRICT,
          data date NOT NULL,
          valor numeric(12,2) NOT NULL,
          descricao text NOT NULL,
          -- Competência estimada pelos dias do cartão (D-27): dia 1 do mês.
          fatura_prevista date,
          CONSTRAINT ck_pluggy_pendentes_valor_positivo CHECK (valor > 0),
          CONSTRAINT ck_pluggy_pendentes_fatura_dia_1
            CHECK (fatura_prevista IS NULL OR extract(day FROM fatura_prevista) = 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pluggy_pendentes_id_externo ON pluggy_pendentes (id_externo)"
    )
    op.execute(
        "CREATE INDEX ix_pluggy_pendentes_conta_pluggy_id ON pluggy_pendentes (conta_pluggy_id)"
    )
    op.execute(
        "CREATE INDEX ix_pluggy_pendentes_forma_pagamento_id ON pluggy_pendentes (forma_pagamento_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pluggy_pendentes_forma_pagamento_id")
    op.execute("DROP INDEX IF EXISTS ix_pluggy_pendentes_conta_pluggy_id")
    op.execute("DROP INDEX IF EXISTS uq_pluggy_pendentes_id_externo")
    op.execute("DROP TABLE IF EXISTS pluggy_pendentes")
