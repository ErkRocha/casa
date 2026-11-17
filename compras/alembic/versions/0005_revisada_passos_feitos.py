"""Quantidades revisadas na receita e passos do roteiro feitos.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-17

D-30, telas aprovadas. Duas mudanças:

* `receitas` ganha `quantidades_revisadas`, `revisadas_por` e `revisadas_em`
  (o botão "Conferi, está certa"). A linha `[REVISAR QUANTIDADES]` que a
  carga inicial punha no `modo_preparo` vira o campo e some do texto: quem a
  tinha fica `false`; as demais receitas vivas ficam `true`, por `migracao`.
* `passos_feitos`: por sessão de preparo e receita, quem marcou e quando.
  Linha viva é passo feito; desfazer é soft delete.

Mesmas convenções da 0004: `atualizado_em` com índice e trigger, auditoria e
o trigger que recusa escrita de outra role.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "passos_feitos"

#: O texto da carga inicial (compras.carga_cardapio.MARCA_REVISAR em 0004).
_MARCA = "[REVISAR QUANTIDADES] Quantidades estimadas pela carga inicial."
_INICIA_COM_A_MARCA = r"^\[REVISAR QUANTIDADES\]"
_LINHA_DA_MARCA = r"^\[REVISAR QUANTIDADES\][^\n]*(\n|$)"


def _receitas() -> None:
    op.execute(
        """
        ALTER TABLE compras.receitas
          ADD COLUMN quantidades_revisadas boolean NOT NULL DEFAULT false,
          ADD COLUMN revisadas_por text,
          ADD COLUMN revisadas_em timestamptz
        """
    )
    op.execute(
        """
        ALTER TABLE compras.receitas ADD CONSTRAINT ck_receitas_revisadas_com_autor CHECK (
          CASE WHEN quantidades_revisadas
            THEN revisadas_por IS NOT NULL AND revisadas_em IS NOT NULL
            ELSE revisadas_por IS NULL AND revisadas_em IS NULL
          END
        )
        """
    )
    # Para a auditoria das linhas mexidas aqui não sair como "desconhecido".
    op.execute("SELECT set_config('app.autor', 'migracao_0005', true)")
    # As demais receitas vivas (as sem a marca) ficam revisadas.
    op.execute(
        f"""
        UPDATE compras.receitas
        SET quantidades_revisadas = true, revisadas_por = 'migracao', revisadas_em = now()
        WHERE deleted_em IS NULL AND coalesce(modo_preparo, '') !~ '{_INICIA_COM_A_MARCA}'
        """
    )
    # As com a marca ficam `false` (o padrão), sem a linha; sobrou vazio, nulo.
    op.execute(
        f"""
        UPDATE compras.receitas
        SET modo_preparo = CASE
          WHEN btrim(regexp_replace(modo_preparo, '{_LINHA_DA_MARCA}', '')) = '' THEN NULL
          ELSE regexp_replace(modo_preparo, '{_LINHA_DA_MARCA}', '')
        END
        WHERE modo_preparo ~ '{_INICIA_COM_A_MARCA}'
        """
    )


def _passos_feitos() -> None:
    op.execute(
        f"""
        CREATE TABLE compras.{_TABELA} (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          criado_em timestamptz NOT NULL DEFAULT now(),
          atualizado_em timestamptz NOT NULL DEFAULT now(),
          deleted_em timestamptz,
          sessao_id bigint NOT NULL REFERENCES compras.sessoes_preparo (id),
          receita_id bigint NOT NULL REFERENCES compras.receitas (id),
          feito_por text NOT NULL CHECK (btrim(feito_por) <> ''),
          feito_em timestamptz NOT NULL DEFAULT now(),
          id_cliente uuid
        )
        """
    )
    op.execute(
        f"CREATE UNIQUE INDEX uq_{_TABELA}_sessao_receita ON compras.{_TABELA} "
        "(sessao_id, receita_id) WHERE deleted_em IS NULL"
    )
    # Único em qualquer estado, como o de receitas: reenviar não recria.
    op.execute(f"CREATE UNIQUE INDEX uq_{_TABELA}_id_cliente ON compras.{_TABELA} (id_cliente)")
    op.execute(f"CREATE INDEX ix_{_TABELA}_receita_id ON compras.{_TABELA} (receita_id)")
    op.execute(f"CREATE INDEX ix_{_TABELA}_atualizado_em ON compras.{_TABELA} (atualizado_em)")
    op.execute(
        f"""
        CREATE TRIGGER tg_{_TABELA}_atualizado_em
        BEFORE UPDATE ON compras.{_TABELA}
        FOR EACH ROW EXECUTE FUNCTION compras.fn_set_atualizado_em()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER tg_{_TABELA}_auditoria
        AFTER INSERT OR UPDATE OR DELETE ON compras.{_TABELA}
        FOR EACH ROW EXECUTE FUNCTION compras.fn_auditoria()
        """
    )
    op.execute(
        f"""
        CREATE TRIGGER tg_{_TABELA}_somente_casa_compras
        BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON compras.{_TABELA}
        FOR EACH STATEMENT EXECUTE FUNCTION compras.fn_somente_casa_compras()
        """
    )


def upgrade() -> None:
    _receitas()
    _passos_feitos()


def downgrade() -> None:
    op.execute(f"DROP TABLE IF EXISTS compras.{_TABELA}")
    op.execute("SELECT set_config('app.autor', 'migracao_0005', true)")
    # A marca volta como primeira linha nas que ainda não foram conferidas.
    op.execute(
        f"""
        UPDATE compras.receitas
        SET modo_preparo = CASE
          WHEN modo_preparo IS NULL OR btrim(modo_preparo) = '' THEN '{_MARCA}'
          ELSE '{_MARCA}' || E'\n' || modo_preparo
        END
        WHERE NOT quantidades_revisadas
        """
    )
    op.execute(
        "ALTER TABLE compras.receitas DROP CONSTRAINT IF EXISTS ck_receitas_revisadas_com_autor"
    )
    op.execute(
        """
        ALTER TABLE compras.receitas
          DROP COLUMN IF EXISTS revisadas_em,
          DROP COLUMN IF EXISTS revisadas_por,
          DROP COLUMN IF EXISTS quantidades_revisadas
        """
    )
