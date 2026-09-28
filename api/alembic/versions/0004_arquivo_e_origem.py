"""guarda o PDF importado e expõe a origem da transação

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-16

Duas lacunas que só aparecem quando alguém pergunta "de onde veio este
lançamento?":

1. **O arquivo não era guardado.** `importacoes` tinha o nome e o SHA-256, o
   que prova *qual* arquivo originou a transação, mas não permite reabri-lo.
   Agora o PDF inteiro fica em `arquivo_conteudo`.

   Bytes no banco, e não caminho para o disco: são uns 200 KB por fatura, ~5 MB
   por ano de uso. Guardar o caminho economizaria isso e criaria a classe de
   bug que não tem conserto — mover a pasta `faturas/` deixaria o histórico
   apontando para o nada, em silêncio, e sem forma de recuperar. Dentro do
   banco, o backup do banco já leva o comprovante junto.

2. **A view não expunha `importacao_id`.** O vínculo existia na tabela desde a
   0002, mas `vw_transacoes_completa` não o selecionava, então nem a API nem a
   tela conseguiam mostrar a origem. Some agora `importacao_id`,
   `importacao_arquivo` e `importacao_em`.

`arquivo_conteudo` é nullable de propósito: as importações que já existiam
foram feitas antes desta coluna e não têm como recuperar o arquivo.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE importacoes ADD COLUMN arquivo_conteudo bytea")
    op.execute("ALTER TABLE importacoes ADD COLUMN arquivo_tipo text")
    op.execute(
        "COMMENT ON COLUMN importacoes.arquivo_conteudo IS "
        "'O PDF original. Nulo em importações anteriores à migration 0004.'"
    )

    # `CREATE OR REPLACE` mantém as permissões já concedidas à role de
    # insights; um DROP + CREATE as perderia sem avisar, e o relatório mensal
    # quebraria na próxima execução com "permission denied".
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_transacoes_completa AS
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
          t.conta_destino_id,

          -- Origem: de qual arquivo importado esta linha nasceu.
          t.importacao_id,
          imp.arquivo_nome AS importacao_arquivo,
          imp.criado_em AS importacao_em,
          (imp.arquivo_conteudo IS NOT NULL) AS importacao_tem_arquivo
        FROM transacoes t
        LEFT JOIN pessoas p ON p.id = t.pessoa_id
        LEFT JOIN categorias c ON c.id = t.categoria_id
        LEFT JOIN categorias cp ON cp.id = c.categoria_pai_id
        LEFT JOIN formas_pagamento fp ON fp.id = t.forma_pagamento_id
        LEFT JOIN locais l ON l.id = t.local_id
        LEFT JOIN importacoes imp ON imp.id = t.importacao_id
        WHERE t.deleted_em IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW vw_transacoes_completa AS
        SELECT
          t.id, t.data, t.competencia, t.valor, t.tipo, t.descricao,
          t.descricao_original, t.observacao, t.parcela_num, t.parcela_total,
          t.desconto_total, t.criado_em, t.atualizado_em,
          t.pessoa_id, coalesce(p.nome, 'Conjunto') AS pessoa_nome,
          t.categoria_id, c.nome AS categoria_nome, c.categoria_pai_id,
          cp.nome AS categoria_pai_nome,
          coalesce(cp.nome || ' › ' || c.nome, c.nome) AS categoria_caminho,
          coalesce(cp.id, c.id) AS categoria_raiz_id,
          t.forma_pagamento_id, fp.apelido AS forma_pagamento_apelido,
          fp.tipo AS forma_pagamento_tipo,
          t.local_id, l.nome AS local_nome,
          t.conta_id, t.conta_origem_id, t.conta_destino_id
        FROM transacoes t
        LEFT JOIN pessoas p ON p.id = t.pessoa_id
        LEFT JOIN categorias c ON c.id = t.categoria_id
        LEFT JOIN categorias cp ON cp.id = c.categoria_pai_id
        LEFT JOIN formas_pagamento fp ON fp.id = t.forma_pagamento_id
        LEFT JOIN locais l ON l.id = t.local_id
        WHERE t.deleted_em IS NULL
        """
    )
    op.execute("ALTER TABLE importacoes DROP COLUMN IF EXISTS arquivo_tipo")
    op.execute("ALTER TABLE importacoes DROP COLUMN IF EXISTS arquivo_conteudo")
