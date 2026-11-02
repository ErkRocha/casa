"""Lista e despensa: seções, produtos, itens da lista, despensa e auditoria.

Revision ID: 0001
Revises:
Create Date: 2026-11-02

Roda como `casa_compras`, dona do schema `compras` (D-25). O schema e a role
nascem antes, em `scripts/aplicar_role.py`, com a credencial dona do banco:
esta role não tem permissão para criar nenhum dos dois.

Tudo é qualificado com `compras.` em vez de depender do `search_path`.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Tabelas que o celular sincroniza: têm `atualizado_em`, auditoria e soft delete.
_TABELAS = ("secoes", "produtos", "itens_lista", "despensa")

_BASE = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  deleted_em timestamptz
"""


def _funcoes() -> None:
    op.execute(
        """
        CREATE FUNCTION compras.fn_set_atualizado_em() RETURNS trigger AS $$
        BEGIN
          NEW.atualizado_em := now();
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # A mesma auditoria de finanças (D-06), na tabela do próprio schema.
    op.execute(
        """
        CREATE FUNCTION compras.fn_auditoria() RETURNS trigger AS $$
        DECLARE
          v_autor text;
        BEGIN
          v_autor := coalesce(nullif(current_setting('app.autor', true), ''), 'desconhecido');

          IF TG_OP = 'INSERT' THEN
            INSERT INTO compras.auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, NEW.id, TG_OP, NULL, to_jsonb(NEW), v_autor);
            RETURN NEW;
          ELSIF TG_OP = 'UPDATE' THEN
            INSERT INTO compras.auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, NEW.id, TG_OP, to_jsonb(OLD), to_jsonb(NEW), v_autor);
            RETURN NEW;
          ELSE
            INSERT INTO compras.auditoria (tabela, registro_id, acao, dados_antes, dados_depois, autor)
            VALUES (TG_TABLE_NAME, OLD.id, TG_OP, to_jsonb(OLD), NULL, v_autor);
            RETURN OLD;
          END IF;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    # Só `casa_compras` escreve aqui (D-25). Para qualquer role comum o
    # privilégio já basta: sem USAGE no schema, o Postgres recusa antes. O
    # trigger existe por causa da role de finanças, que é superusuária (o
    # POSTGRES_USER do Docker, e o `casa` do modo local) e passa por cima de
    # todo GRANT. Trigger ela não pula sem querer: só desligando-o de
    # propósito. É barreira contra engano, não contra má-fé.
    #
    # Mesmo código de erro da falta de privilégio (42501), para quem chama
    # tratar os dois casos igual. Sem sinal de porcentagem no texto: o
    # psycopg o leria como placeholder.
    op.execute(
        """
        CREATE FUNCTION compras.fn_somente_casa_compras() RETURNS trigger AS $$
        BEGIN
          IF current_user <> 'casa_compras' THEN
            RAISE EXCEPTION USING
              ERRCODE = 'insufficient_privilege',
              MESSAGE = 'o schema compras só aceita escrita da role casa_compras, não de '
                        || current_user;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def _tipos() -> None:
    op.execute("CREATE TYPE compras.situacao_item AS ENUM ('pendente', 'comprado')")
    op.execute("CREATE TYPE compras.estado_despensa AS ENUM ('tem', 'acabando', 'acabou')")
    op.execute("CREATE TYPE compras.origem_item AS ENUM ('manual', 'despensa', 'voz')")


def _tabelas() -> None:
    # Log não se apaga: sem soft delete.
    op.execute(
        """
        CREATE TABLE compras.auditoria (
          id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
          tabela text NOT NULL,
          registro_id bigint NOT NULL,
          acao text NOT NULL,
          dados_antes jsonb,
          dados_depois jsonb,
          autor text NOT NULL,
          ocorrido_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_auditoria_tabela_registro ON compras.auditoria (tabela, registro_id)"
    )

    op.execute(
        f"""
        CREATE TABLE compras.secoes (
          {_BASE},
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          ordem integer NOT NULL
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_secoes_nome ON compras.secoes (lower(nome)) "
        "WHERE deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.produtos (
          {_BASE},
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          nome_normalizado text NOT NULL CHECK (nome_normalizado <> ''),
          secao_id bigint NOT NULL REFERENCES compras.secoes (id),
          unidade_padrao text,
          id_cliente uuid
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_produtos_nome_normalizado ON compras.produtos (nome_normalizado) "
        "WHERE deleted_em IS NULL"
    )
    # Único em qualquer estado: o reenvio de um produto já apagado não o recria.
    op.execute("CREATE UNIQUE INDEX uq_produtos_id_cliente ON compras.produtos (id_cliente)")
    op.execute("CREATE INDEX ix_produtos_secao_id ON compras.produtos (secao_id)")

    op.execute(
        f"""
        CREATE TABLE compras.itens_lista (
          {_BASE},
          produto_id bigint NOT NULL REFERENCES compras.produtos (id),
          quantidade numeric(12,3) CHECK (quantidade > 0),
          unidade text,
          observacao text,
          situacao compras.situacao_item NOT NULL DEFAULT 'pendente',
          origem compras.origem_item NOT NULL DEFAULT 'manual',
          adicionado_por text NOT NULL CHECK (btrim(adicionado_por) <> ''),
          comprado_por text,
          comprado_em timestamptz,
          id_cliente uuid,
          CONSTRAINT ck_itens_lista_compra_coerente CHECK (
            (situacao = 'comprado' AND comprado_por IS NOT NULL AND comprado_em IS NOT NULL)
            OR (situacao = 'pendente' AND comprado_por IS NULL AND comprado_em IS NULL)
          )
        )
        """
    )
    # Um pendente por produto: os dois pondo "leite" ao mesmo tempo não viram
    # dois itens. É a garantia; o service só escolhe a resposta.
    op.execute(
        "CREATE UNIQUE INDEX uq_itens_lista_pendente_por_produto ON compras.itens_lista "
        "(produto_id) WHERE situacao = 'pendente' AND deleted_em IS NULL"
    )
    op.execute("CREATE UNIQUE INDEX uq_itens_lista_id_cliente ON compras.itens_lista (id_cliente)")
    op.execute("CREATE INDEX ix_itens_lista_produto_id ON compras.itens_lista (produto_id)")
    op.execute("CREATE INDEX ix_itens_lista_comprado_em ON compras.itens_lista (comprado_em)")

    op.execute(
        f"""
        CREATE TABLE compras.despensa (
          {_BASE},
          produto_id bigint NOT NULL REFERENCES compras.produtos (id),
          estado compras.estado_despensa NOT NULL,
          estado_por text NOT NULL CHECK (btrim(estado_por) <> ''),
          estado_em timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_despensa_produto ON compras.despensa (produto_id) "
        "WHERE deleted_em IS NULL"
    )


def _triggers() -> None:
    for tabela in _TABELAS:
        # O relógio do `GET /mudancas`.
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

    # Por comando, e não por linha: pega também o TRUNCATE e o UPDATE que
    # não alcança linha nenhuma.
    for tabela in (*_TABELAS, "auditoria"):
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_somente_casa_compras
            BEFORE INSERT OR UPDATE OR DELETE OR TRUNCATE ON compras.{tabela}
            FOR EACH STATEMENT EXECUTE FUNCTION compras.fn_somente_casa_compras()
            """
        )


def upgrade() -> None:
    _funcoes()
    _tipos()
    _tabelas()
    _triggers()


def downgrade() -> None:
    for tabela in ("despensa", "itens_lista", "produtos", "secoes", "auditoria"):
        op.execute(f"DROP TABLE IF EXISTS compras.{tabela}")
    for tipo in ("origem_item", "estado_despensa", "situacao_item"):
        op.execute(f"DROP TYPE IF EXISTS compras.{tipo}")
    for funcao in ("fn_somente_casa_compras", "fn_auditoria", "fn_set_atualizado_em"):
        op.execute(f"DROP FUNCTION IF EXISTS compras.{funcao}()")
