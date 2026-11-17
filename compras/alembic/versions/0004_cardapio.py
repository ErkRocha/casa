"""Cardápio: pessoas, receitas, semanas, refeições, preparo e a lista pelo cardápio.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17

D-30. As tabelas de docs/compras/modelo-cardapio.md para a v1, mais duas
colunas em `produtos` (`medida_base`, `medida_por_unidade`) e o valor
`cardapio` em `origem_item`. Sem metas nutricionais nem `produto_nutrientes`
(fora da v1). Mesmas convenções da 0001: tudo no schema `compras`, com
`atualizado_em`, auditoria e o trigger que recusa escrita de outra role.

`ALTER TYPE ... ADD VALUE` roda dentro da transação da migration (Postgres 12
em diante aceita). O valor novo só não pode ser *usado* nessa mesma
transação, e nenhum comando daqui o usa: ele é gravado pelo serviço, depois
do commit.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = (
    "pessoas",
    "receitas",
    "receita_ingredientes",
    "semanas",
    "refeicoes",
    "refeicao_pessoas",
    "sessoes_preparo",
    "itens_lista_cardapio",
)

_BASE = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  deleted_em timestamptz
"""


def _tipos() -> None:
    op.execute(
        "CREATE TYPE compras.tipo_refeicao AS ENUM ('cafe_da_manha', 'lanche', 'almoco', 'janta')"
    )
    op.execute(
        "CREATE TYPE compras.unidade_medida AS ENUM "
        "('g', 'kg', 'ml', 'l', 'un', 'colher_sopa', 'colher_cha', 'xicara', 'a_gosto')"
    )
    op.execute("CREATE TYPE compras.medida_base AS ENUM ('g', 'ml', 'un')")
    op.execute("ALTER TYPE compras.origem_item ADD VALUE IF NOT EXISTS 'cardapio'")


def _produtos() -> None:
    op.execute("ALTER TABLE compras.produtos ADD COLUMN medida_base compras.medida_base")
    op.execute("ALTER TABLE compras.produtos ADD COLUMN medida_por_unidade numeric(12,3)")
    op.execute(
        "ALTER TABLE compras.produtos ADD CONSTRAINT ck_produtos_medida_por_unidade_positiva "
        "CHECK (medida_por_unidade > 0)"
    )


def _tabelas() -> None:
    op.execute(
        f"""
        CREATE TABLE compras.pessoas (
          {_BASE},
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          identidade_id bigint REFERENCES compras.identidades_tailscale (id),
          porcao_padrao numeric(4,2) NOT NULL DEFAULT 1 CHECK (porcao_padrao > 0)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pessoas_nome ON compras.pessoas (lower(nome)) "
        "WHERE deleted_em IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_pessoas_identidade_id ON compras.pessoas (identidade_id) "
        "WHERE deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.receitas (
          {_BASE},
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          nome_normalizado text NOT NULL CHECK (nome_normalizado <> ''),
          tipo compras.tipo_refeicao NOT NULL,
          rendimento_porcoes numeric(6,2) NOT NULL CHECK (rendimento_porcoes > 0),
          tempo_preparo_min integer CHECK (tempo_preparo_min >= 0),
          modo_preparo text,
          pode_antecipar boolean NOT NULL DEFAULT false,
          dura_dias integer,
          pode_congelar boolean NOT NULL DEFAULT false,
          id_cliente uuid,
          CONSTRAINT ck_receitas_antecipar_exige_validade CHECK (
            NOT pode_antecipar OR coalesce(dura_dias, 0) >= 1
          )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_receitas_nome_normalizado ON compras.receitas "
        "(nome_normalizado) WHERE deleted_em IS NULL"
    )
    # Único em qualquer estado, como o de produtos: reenviar não recria.
    op.execute("CREATE UNIQUE INDEX uq_receitas_id_cliente ON compras.receitas (id_cliente)")

    op.execute(
        f"""
        CREATE TABLE compras.receita_ingredientes (
          {_BASE},
          receita_id bigint NOT NULL REFERENCES compras.receitas (id),
          produto_id bigint NOT NULL REFERENCES compras.produtos (id),
          quantidade numeric(12,3) CHECK (quantidade > 0),
          unidade compras.unidade_medida NOT NULL,
          observacao text,
          ordem integer NOT NULL,
          CONSTRAINT ck_receita_ingredientes_a_gosto_sem_quantidade CHECK (
            (unidade = 'a_gosto') = (quantidade IS NULL)
          )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_receita_ingredientes_receita_id ON compras.receita_ingredientes "
        "(receita_id)"
    )
    op.execute(
        "CREATE INDEX ix_receita_ingredientes_produto_id ON compras.receita_ingredientes "
        "(produto_id)"
    )

    op.execute(
        f"""
        CREATE TABLE compras.semanas (
          {_BASE},
          inicio date NOT NULL CHECK (extract(isodow FROM inicio) = 1),
          observacao text
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_semanas_inicio ON compras.semanas (inicio) WHERE deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.refeicoes (
          {_BASE},
          semana_id bigint NOT NULL REFERENCES compras.semanas (id),
          dia date NOT NULL,
          tipo compras.tipo_refeicao NOT NULL,
          receita_id bigint REFERENCES compras.receitas (id),
          observacao text,
          ordem integer NOT NULL DEFAULT 0,
          CONSTRAINT ck_refeicoes_receita_ou_observacao CHECK (
            receita_id IS NOT NULL OR (observacao IS NOT NULL AND btrim(observacao) <> '')
          )
        )
        """
    )
    op.execute("CREATE INDEX ix_refeicoes_semana_id ON compras.refeicoes (semana_id)")
    op.execute("CREATE INDEX ix_refeicoes_receita_id ON compras.refeicoes (receita_id)")

    op.execute(
        f"""
        CREATE TABLE compras.refeicao_pessoas (
          {_BASE},
          refeicao_id bigint NOT NULL REFERENCES compras.refeicoes (id),
          pessoa_id bigint NOT NULL REFERENCES compras.pessoas (id),
          porcoes numeric(4,2) CHECK (porcoes > 0)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_refeicao_pessoas_refeicao_pessoa ON compras.refeicao_pessoas "
        "(refeicao_id, pessoa_id) WHERE deleted_em IS NULL"
    )
    op.execute("CREATE INDEX ix_refeicao_pessoas_pessoa_id ON compras.refeicao_pessoas (pessoa_id)")

    op.execute(
        f"""
        CREATE TABLE compras.sessoes_preparo (
          {_BASE},
          semana_id bigint NOT NULL REFERENCES compras.semanas (id),
          data date NOT NULL,
          rotulo text
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sessoes_preparo_semana_data ON compras.sessoes_preparo "
        "(semana_id, data) WHERE deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.itens_lista_cardapio (
          {_BASE},
          item_lista_id bigint NOT NULL REFERENCES compras.itens_lista (id),
          semana_id bigint NOT NULL REFERENCES compras.semanas (id),
          quantidade numeric(12,3),
          unidade text,
          gerado_por text NOT NULL CHECK (btrim(gerado_por) <> '')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_itens_lista_cardapio_item_semana ON compras.itens_lista_cardapio "
        "(item_lista_id, semana_id) WHERE deleted_em IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_itens_lista_cardapio_semana_id ON compras.itens_lista_cardapio (semana_id)"
    )


def _funcoes_de_data() -> None:
    # O dia da refeição e a data da sessão dependem de outra tabela (a semana),
    # o que um CHECK não alcança: trigger.
    op.execute(
        """
        CREATE FUNCTION compras.fn_refeicao_dia_na_semana() RETURNS trigger AS $$
        DECLARE
          v_inicio date;
        BEGIN
          SELECT inicio INTO v_inicio FROM compras.semanas WHERE id = NEW.semana_id;
          IF NEW.dia < v_inicio OR NEW.dia > v_inicio + 6 THEN
            RAISE EXCEPTION USING
              ERRCODE = 'check_violation',
              MESSAGE = 'o dia da refeição precisa estar dentro da semana';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_refeicoes_dia_na_semana
        BEFORE INSERT OR UPDATE ON compras.refeicoes
        FOR EACH ROW EXECUTE FUNCTION compras.fn_refeicao_dia_na_semana()
        """
    )
    op.execute(
        """
        CREATE FUNCTION compras.fn_sessao_data_na_semana() RETURNS trigger AS $$
        DECLARE
          v_inicio date;
        BEGIN
          SELECT inicio INTO v_inicio FROM compras.semanas WHERE id = NEW.semana_id;
          IF NEW.data < v_inicio - 2 OR NEW.data > v_inicio + 6 THEN
            RAISE EXCEPTION USING
              ERRCODE = 'check_violation',
              MESSAGE = 'a sessão de preparo vai do sábado anterior ao domingo da semana';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_sessoes_preparo_data_na_semana
        BEFORE INSERT OR UPDATE ON compras.sessoes_preparo
        FOR EACH ROW EXECUTE FUNCTION compras.fn_sessao_data_na_semana()
        """
    )


def _triggers() -> None:
    for tabela in _TABELAS:
        op.execute(f"CREATE INDEX ix_{tabela}_atualizado_em ON compras.{tabela} (atualizado_em)")
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_atualizado_em
            BEFORE UPDATE ON compras.{tabela}
            FOR EACH ROW EXECUTE FUNCTION compras.fn_set_atualizado_em()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_auditoria
            AFTER INSERT OR UPDATE OR DELETE ON compras.{tabela}
            FOR EACH ROW EXECUTE FUNCTION compras.fn_auditoria()
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_somente_casa_compras
            BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON compras.{tabela}
            FOR EACH STATEMENT EXECUTE FUNCTION compras.fn_somente_casa_compras()
            """
        )


def upgrade() -> None:
    _tipos()
    _produtos()
    _tabelas()
    _funcoes_de_data()
    _triggers()


def downgrade() -> None:
    for tabela in reversed(_TABELAS):
        op.execute(f"DROP TABLE IF EXISTS compras.{tabela}")
    op.execute("DROP FUNCTION IF EXISTS compras.fn_sessao_data_na_semana()")
    op.execute("DROP FUNCTION IF EXISTS compras.fn_refeicao_dia_na_semana()")

    op.execute(
        "ALTER TABLE compras.produtos DROP CONSTRAINT IF EXISTS "
        "ck_produtos_medida_por_unidade_positiva"
    )
    op.execute("ALTER TABLE compras.produtos DROP COLUMN IF EXISTS medida_por_unidade")
    op.execute("ALTER TABLE compras.produtos DROP COLUMN IF EXISTS medida_base")

    # Postgres não remove valor de enum: recria o tipo sem `cardapio`. Item
    # que veio do cardápio vira manual.
    op.execute("UPDATE compras.itens_lista SET origem = 'manual' WHERE origem::text = 'cardapio'")
    op.execute("ALTER TABLE compras.itens_lista ALTER COLUMN origem DROP DEFAULT")
    op.execute("ALTER TYPE compras.origem_item RENAME TO origem_item_com_cardapio")
    op.execute("CREATE TYPE compras.origem_item AS ENUM ('manual', 'despensa', 'voz')")
    op.execute(
        "ALTER TABLE compras.itens_lista ALTER COLUMN origem TYPE compras.origem_item "
        "USING origem::text::compras.origem_item"
    )
    op.execute("ALTER TABLE compras.itens_lista ALTER COLUMN origem SET DEFAULT 'manual'")
    op.execute("DROP TYPE compras.origem_item_com_cardapio")

    for tipo in ("medida_base", "unidade_medida", "tipo_refeicao"):
        op.execute(f"DROP TYPE IF EXISTS compras.{tipo}")
