"""Nota fiscal e preços: mercados, notas, itens, apelidos e a view de preço.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02

As tabelas da seção "Nota fiscal e preços" de docs/compras/modelo-dados.md.
Mesmas convenções da 0001: tudo no schema `compras`, criado por
`casa_compras`, com `atualizado_em`, auditoria e o trigger que recusa escrita
de outra role. Nenhuma FK para finanças: `transacao_id` é id simples (D-25).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = ("mercados", "notas_fiscais", "nota_itens", "apelidos")

_BASE = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  deleted_em timestamptz
"""


def _tipos() -> None:
    op.execute("CREATE TYPE compras.origem_associacao AS ENUM ('apelido', 'gtin', 'usuario')")
    op.execute("CREATE TYPE compras.status_nota AS ENUM ('lida', 'erro')")


def _tabelas() -> None:
    op.execute(
        f"""
        CREATE TABLE compras.mercados (
          {_BASE},
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          razao_social text,
          cnpj text CHECK (cnpj ~ '^[0-9]{{14}}$'),
          endereco text,
          cidade text
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_mercados_cnpj ON compras.mercados (cnpj) WHERE deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.notas_fiscais (
          {_BASE},
          chave_acesso text NOT NULL CHECK (chave_acesso ~ '^[0-9]{{44}}$'),
          mercado_id bigint REFERENCES compras.mercados (id),
          emitida_em timestamptz,
          valor_total numeric(12,2),
          desconto_total numeric(12,2) NOT NULL DEFAULT 0,
          url_consulta text NOT NULL,
          conteudo_original bytea,
          conteudo_tipo text,
          leitor_versao text,
          status compras.status_nota NOT NULL,
          erro_mensagem text,
          transacao_id bigint,
          lida_por text NOT NULL CHECK (btrim(lida_por) <> ''),
          CONSTRAINT ck_notas_fiscais_erro_tem_mensagem CHECK (
            status <> 'erro' OR erro_mensagem IS NOT NULL
          )
        )
        """
    )
    # Em qualquer status: ler o mesmo QR code duas vezes devolve a nota que
    # já existe, inclusive a que deu erro.
    op.execute(
        "CREATE UNIQUE INDEX uq_notas_fiscais_chave ON compras.notas_fiscais (chave_acesso) "
        "WHERE deleted_em IS NULL"
    )
    op.execute("CREATE INDEX ix_notas_fiscais_mercado_id ON compras.notas_fiscais (mercado_id)")
    op.execute("CREATE INDEX ix_notas_fiscais_emitida_em ON compras.notas_fiscais (emitida_em)")

    op.execute(
        f"""
        CREATE TABLE compras.nota_itens (
          {_BASE},
          nota_fiscal_id bigint NOT NULL REFERENCES compras.notas_fiscais (id),
          linha_num integer NOT NULL CHECK (linha_num > 0),
          codigo text,
          gtin text,
          descricao_original text NOT NULL CHECK (btrim(descricao_original) <> ''),
          quantidade numeric(12,3) NOT NULL CHECK (quantidade > 0),
          unidade text,
          valor_unitario numeric(12,4),
          valor_total numeric(12,2) NOT NULL,
          desconto numeric(12,2) NOT NULL DEFAULT 0,
          produto_id bigint REFERENCES compras.produtos (id),
          origem_associacao compras.origem_associacao,
          CONSTRAINT ck_nota_itens_associacao_coerente CHECK (
            (produto_id IS NULL) = (origem_associacao IS NULL)
          ),
          CONSTRAINT uq_nota_itens_linha UNIQUE (nota_fiscal_id, linha_num)
        )
        """
    )
    op.execute("CREATE INDEX ix_nota_itens_produto_id ON compras.nota_itens (produto_id)")
    # A fila de "associar": itens vivos sem produto.
    op.execute(
        "CREATE INDEX ix_nota_itens_sem_produto ON compras.nota_itens (nota_fiscal_id) "
        "WHERE produto_id IS NULL AND deleted_em IS NULL"
    )

    # `descricao_original` é o texto cru da nota (regra 11): nunca muda.
    op.execute(
        """
        CREATE FUNCTION compras.fn_descricao_original_imutavel() RETURNS trigger AS $$
        BEGIN
          IF NEW.descricao_original IS DISTINCT FROM OLD.descricao_original THEN
            RAISE EXCEPTION USING
              MESSAGE = 'descricao_original é imutável (nota_itens ' || OLD.id || ')';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_nota_itens_descricao_imutavel
        BEFORE UPDATE ON compras.nota_itens
        FOR EACH ROW EXECUTE FUNCTION compras.fn_descricao_original_imutavel()
        """
    )

    op.execute(
        f"""
        CREATE TABLE compras.apelidos (
          {_BASE},
          produto_id bigint NOT NULL REFERENCES compras.produtos (id),
          texto_normalizado text CHECK (texto_normalizado <> ''),
          gtin text CHECK (gtin <> ''),
          mercado_id bigint REFERENCES compras.mercados (id),
          acertos integer NOT NULL DEFAULT 1 CHECK (acertos > 0),
          criado_por text NOT NULL CHECK (criado_por IN ('usuario', 'correcao')),
          CONSTRAINT ck_apelidos_texto_ou_gtin CHECK (
            texto_normalizado IS NOT NULL OR gtin IS NOT NULL
          )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_apelidos_texto_mercado ON compras.apelidos "
        "(texto_normalizado, mercado_id) NULLS NOT DISTINCT "
        "WHERE deleted_em IS NULL AND texto_normalizado IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_apelidos_gtin ON compras.apelidos (gtin) "
        "WHERE deleted_em IS NULL AND gtin IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_apelidos_produto_id ON compras.apelidos (produto_id)")


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


def _view() -> None:
    # Preço por produto, mercado e unidade, só de itens associados de notas
    # vivas e lidas. Unidades diferentes (KG e UN) não se misturam. Sem o
    # unitário na nota, vale o total da linha dividido pela quantidade.
    op.execute(
        """
        CREATE VIEW compras.vw_preco_produto AS
        WITH base AS (
          SELECT
            i.produto_id,
            n.mercado_id,
            upper(coalesce(nullif(btrim(i.unidade), ''), 'UN')) AS unidade,
            coalesce(i.valor_unitario, round(i.valor_total / i.quantidade, 4)) AS preco,
            n.emitida_em,
            n.id AS nota_fiscal_id
          FROM compras.nota_itens i
          JOIN compras.notas_fiscais n ON n.id = i.nota_fiscal_id
          WHERE i.produto_id IS NOT NULL
            AND i.deleted_em IS NULL
            AND n.deleted_em IS NULL
            AND n.status = 'lida'
            AND n.mercado_id IS NOT NULL
        )
        SELECT
          produto_id,
          mercado_id,
          unidade,
          (array_agg(preco ORDER BY emitida_em DESC NULLS LAST, nota_fiscal_id DESC))[1]
            AS ultimo_preco,
          max(emitida_em) AS ultima_compra_em,
          min(preco) AS preco_min,
          max(preco) AS preco_max,
          round(avg(preco), 4) AS preco_medio,
          count(*) AS compras
        FROM base
        GROUP BY produto_id, mercado_id, unidade
        """
    )


def upgrade() -> None:
    _tipos()
    _tabelas()
    _triggers()
    _view()


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS compras.vw_preco_produto")
    for tabela in ("apelidos", "nota_itens", "notas_fiscais", "mercados"):
        op.execute(f"DROP TABLE IF EXISTS compras.{tabela}")
    op.execute("DROP FUNCTION IF EXISTS compras.fn_descricao_original_imutavel()")
    for tipo in ("status_nota", "origem_associacao"):
        op.execute(f"DROP TYPE IF EXISTS compras.{tipo}")
