"""tipo estorno e ligação com a compra original

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-19

D-34, item 1. O crédito no cartão que não é pagamento de fatura deixa de ser
receita: é um estorno, que abate o gasto na categoria e na pessoa da compra
original (ou na categoria sugerida e no titular do cartão, quando a original
não se acha).

* `tipo_transacao` ganha o valor `estorno`. O valor é sempre positivo, como
  nos outros tipos (`ck_transacoes_valor_positivo`); o sinal vem do tipo.
* `transacoes.estorno_de_id` liga o estorno à compra original, quando
  identificada. `ON DELETE RESTRICT`: não há DELETE físico (regra 2), e a
  restrição impede que um dia a compra suma deixando o estorno órfão. Só o
  estorno aponta (`ck_transacoes_estorno_de_so_estorno`).
* `ck_transacoes_transferencia_coerente` não muda: estorno é "tipo <>
  'transferencia'", logo sem conta de origem nem de destino, como despesa e
  receita. O estorno usa categoria de DESPESA (`categorias.tipo` segue
  despesa/receita).
* `vw_gasto_por_pessoa` e `vw_orcamento_mes` passam a somar o gasto líquido:
  despesa menos estorno. `CREATE OR REPLACE` mantém as permissões da role de
  insights (D-11); as colunas e os tipos são os mesmos. `vw_transacoes_completa`
  já expõe `tipo` e não precisa mudar.

**Postgres não usa um valor de enum recém-criado na transação que o criou.**
Por isso o `ADD VALUE` roda num `autocommit_block` e o resto, depois dele.

**Downgrade.** O Postgres não tem `DROP VALUE` para enum, e recriar o tipo
exige derrubar e refazer as views e o CHECK que dependem dele. O downgrade
escolhe o caminho seguro e documentado: recusa (erro, nada é alterado) se
existir estorno em `transacoes` ou em `importacao_itens.tipo_sugerido`; sem
nenhum, remove a coluna, o CHECK e o índice e devolve as views de 0001. O valor
`estorno` fica no tipo, sem uso e sem efeito; um novo `upgrade` o reaproveita
(`ADD VALUE IF NOT EXISTS`).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fora da transação: o valor novo só pode ser usado depois do commit.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE tipo_transacao ADD VALUE IF NOT EXISTS 'estorno'")

    op.execute(
        "ALTER TABLE transacoes ADD COLUMN estorno_de_id bigint "
        "REFERENCES transacoes (id) ON DELETE RESTRICT"
    )
    op.execute("CREATE INDEX ix_transacoes_estorno_de_id ON transacoes (estorno_de_id)")
    op.execute(
        "ALTER TABLE transacoes ADD CONSTRAINT ck_transacoes_estorno_de_so_estorno "
        "CHECK (estorno_de_id IS NULL OR tipo = 'estorno')"
    )
    _criar_views_liquidas()


def downgrade() -> None:
    conn = op.get_bind()
    usados = conn.exec_driver_sql(
        """
        SELECT (SELECT count(*) FROM transacoes WHERE tipo = 'estorno')
             + (SELECT count(*) FROM importacao_itens WHERE tipo_sugerido = 'estorno')
        """
    ).scalar()
    if usados:
        raise RuntimeError(
            f"Downgrade da 0009 recusado: há {usados} estorno(s) em transacoes ou "
            "importacao_itens. Converta-os (por exemplo, de volta a receita) ou "
            "restaure um backup antes."
        )

    _criar_views_brutas()
    op.execute(
        "ALTER TABLE transacoes DROP CONSTRAINT IF EXISTS ck_transacoes_estorno_de_so_estorno"
    )
    op.execute("DROP INDEX IF EXISTS ix_transacoes_estorno_de_id")
    op.execute("ALTER TABLE transacoes DROP COLUMN IF EXISTS estorno_de_id")
    # O valor 'estorno' permanece em tipo_transacao: o Postgres não remove
    # valor de enum. Sem linha que o use, é inerte.


def _criar_views_liquidas() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_gasto_por_pessoa AS
        SELECT
          t.competencia,
          coalesce(t.pessoa_id::text, 'conjunto') AS balde,
          coalesce(p.nome, 'Conjunto') AS balde_nome,
          sum(CASE t.tipo WHEN 'despesa' THEN t.valor WHEN 'estorno' THEN -t.valor END) AS total
        FROM transacoes t
        LEFT JOIN pessoas p ON p.id = t.pessoa_id
        WHERE t.deleted_em IS NULL
          AND t.tipo IN ('despesa', 'estorno')
        GROUP BY t.competencia, coalesce(t.pessoa_id::text, 'conjunto'), coalesce(p.nome, 'Conjunto')
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_orcamento_mes AS
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
          SELECT sum(CASE t.tipo WHEN 'despesa' THEN t.valor WHEN 'estorno' THEN -t.valor END)
                   AS realizado
          FROM transacoes t
          JOIN categorias c ON c.id = t.categoria_id
          WHERE t.deleted_em IS NULL
            AND t.tipo IN ('despesa', 'estorno')
            AND t.competencia = o.competencia
            AND coalesce(c.categoria_pai_id, c.id) = o.categoria_id
        ) r ON true
        WHERE o.deleted_em IS NULL
        """
    )


def _criar_views_brutas() -> None:
    """As views de 0001: só despesa, sem estorno."""
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_gasto_por_pessoa AS
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
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_orcamento_mes AS
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
