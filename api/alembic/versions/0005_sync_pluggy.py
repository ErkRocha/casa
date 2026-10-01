"""sync Pluggy — id externo no staging e mapeamento de contas

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-01

Fase 5b, passo 1 (D-16). A Pluggy entra como mais uma origem de ingestão, e
isso pede duas coisas que o PDF não pedia:

1. **`importacao_itens.id_externo`** — o id da transação na Pluggy. A sync roda
   todo dia sobre uma janela que se sobrepõe à anterior; sem barreira no
   staging, cada execução empilharia de novo os mesmos itens aguardando
   revisão. O índice único vale para **qualquer status**, de propósito: item
   rejeitado continua bloqueando, senão a rejeição desfaria a si mesma na sync
   seguinte. Nulo para item de PDF, que não tem id estável.

2. **`contas_pluggy`** — liga uma conta da Pluggy a uma `conta` daqui, à forma
   de pagamento padrão dela e à data a partir da qual a Pluggy é a origem
   daquela conta (antes dela vale o PDF; D-16, "uma origem por conta e
   período"). Não há `pessoa_id`: a pessoa sai de `contas.titular_id`, então
   mapear contas de outro titular depois não muda a estrutura.

   `forma_pagamento_id` é NOT NULL. Ela entra no `hash_dedup` de `transacoes`
   — a segunda barreira de deduplicação — e é o que separa compra no cartão de
   débito em conta. Um mapeamento sem forma geraria itens sem forma, que só
   seriam resolvidos à mão na revisão, um a um, todo dia. O cartão adicional
   continua sendo resolvido pelo final do cartão, por cima desta padrão.

O que **não** muda: a importação de origem `pluggy` grava como "arquivo" o
JSON bruto recebido (`arquivo_tipo = 'application/json'`), com o SHA-256 dele
em `hash_arquivo`. Nenhuma coluna de `importacoes` restringe tipo ou origem —
`arquivo_tipo` e `origem` são `text` livres (0002, 0004) e `arquivo_conteudo`
é `bytea` —, então a opção (b) da Fase 5b não exige DDL.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_COLS = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz,
  deleted_em timestamptz
"""


def upgrade() -> None:
    op.execute("ALTER TABLE importacao_itens ADD COLUMN id_externo text")
    op.execute(
        "COMMENT ON COLUMN importacao_itens.id_externo IS "
        "'Id da transação na origem externa (Pluggy). Nulo para item de PDF.'"
    )
    # Sem filtro de status: rejeitado e duplicado também bloqueiam (D-16).
    op.execute(
        """
        CREATE UNIQUE INDEX uq_importacao_itens_id_externo
        ON importacao_itens (id_externo)
        WHERE id_externo IS NOT NULL AND deleted_em IS NULL
        """
    )

    op.execute(
        f"""
        CREATE TABLE contas_pluggy (
          {_BASE_COLS},
          -- A conexão (item) na Pluggy. Uma conexão expõe várias contas.
          pluggy_item_id text NOT NULL,
          pluggy_account_id text NOT NULL,
          conta_id bigint NOT NULL REFERENCES contas (id) ON DELETE RESTRICT,
          -- A forma padrão dos itens desta conta. Entra no `hash_dedup`.
          forma_pagamento_id bigint NOT NULL
            REFERENCES formas_pagamento (id) ON DELETE RESTRICT,
          -- A partir desta data a Pluggy é a origem da conta; antes, o PDF.
          sincronizar_desde date NOT NULL,
          ultimo_sync_em timestamptz,
          ativo boolean NOT NULL DEFAULT true
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_contas_pluggy_pluggy_account_id
        ON contas_pluggy (pluggy_account_id)
        WHERE deleted_em IS NULL
        """
    )
    op.execute("CREATE INDEX ix_contas_pluggy_conta_id ON contas_pluggy (conta_id)")
    op.execute(
        "CREATE INDEX ix_contas_pluggy_forma_pagamento_id ON contas_pluggy (forma_pagamento_id)"
    )
    op.execute("CREATE INDEX ix_contas_pluggy_deleted_em ON contas_pluggy (deleted_em)")

    op.execute(
        """
        CREATE TRIGGER tg_contas_pluggy_atualizado_em
        BEFORE UPDATE ON contas_pluggy
        FOR EACH ROW EXECUTE FUNCTION fn_set_atualizado_em()
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_contas_pluggy_auditoria
        AFTER INSERT OR UPDATE OR DELETE ON contas_pluggy
        FOR EACH ROW EXECUTE FUNCTION fn_auditoria()
        """
    )

    # Mesmo motivo da 0003: o ALTER DEFAULT PRIVILEGES só alcança esta tabela
    # se a role nasceu antes. O GRANT explícito tira a dependência de ordem.
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'casa_insights') THEN
            GRANT SELECT ON contas_pluggy TO casa_insights;
          END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS tg_contas_pluggy_auditoria ON contas_pluggy")
    op.execute("DROP TRIGGER IF EXISTS tg_contas_pluggy_atualizado_em ON contas_pluggy")
    op.execute("DROP INDEX IF EXISTS ix_contas_pluggy_deleted_em")
    op.execute("DROP INDEX IF EXISTS ix_contas_pluggy_forma_pagamento_id")
    op.execute("DROP INDEX IF EXISTS ix_contas_pluggy_conta_id")
    op.execute("DROP INDEX IF EXISTS uq_contas_pluggy_pluggy_account_id")
    op.execute("DROP TABLE IF EXISTS contas_pluggy")

    op.execute("DROP INDEX IF EXISTS uq_importacao_itens_id_externo")
    op.execute("ALTER TABLE importacao_itens DROP COLUMN IF EXISTS id_externo")
