"""Variantes, preço comparável, fechamento do item da lista e marco da conferência.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-19

D-33, docs/compras/modelo-notas.md (mudanças aprovadas pelo usuário). Tudo do
schema `compras`:

* enums: `fechamento_item` (novo) e o valor `nota` em `origem_item`;
* `variantes` e `variante_codigos` (identidade `(mercado, código)` quando a
  nota não traz GTIN);
* `nota_itens.variante_id` e `item_lista_id`; `produto_id` passa a ser cópia
  do produto da variante, mantida por trigger; `apelidos.variante_id`;
* `notas_fiscais`: marco da conferência, ligação com a compra pendente,
  forma de pagamento da nota e a marca "despesa lançada pela nota";
* `itens_lista`: `fechamento`, `fechado_em`, `fechado_por`, `perguntado_em`;
* `secoes.categoria_id_financas` (id simples, sem FK: D-25);
* views `vw_preco_variante` (nova) e `vw_preco_produto` (refeita).

Migração de dados (autor `migracao_0006` na auditoria):

* o apelido de GTIN vira `variantes.gtin` e é apagado (soft delete);
* cada associação antiga, só com produto, vira uma variante por
  `(produto, descrição normalizada, mercado)`, com o código interno do item
  gravado em `variante_codigos` (sem zeros à esquerda). Grupo em que todos os
  itens vêm em `KG` nasce `pesada`; nenhuma medida é inventada;
* todo apelido de texto passa a apontar para uma variante;
* todo item já `comprado` recebe `fechamento = sem_nota`, `fechado_por =
  migracao`.

`ALTER TYPE ... ADD VALUE` roda na transação da migration (Postgres 12 em
diante); o valor `nota` só é gravado pelo serviço, depois do commit.

A role `casa_compras` é dona das tabelas e das views: não há GRANT a fazer.
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS_NOVAS = ("variantes", "variante_codigos")

_BASE = """
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  criado_em timestamptz NOT NULL DEFAULT now(),
  atualizado_em timestamptz NOT NULL DEFAULT now(),
  deleted_em timestamptz
"""

_UNIDADES_DE_CONTAGEM = "('UN', 'UND', 'UNID', 'PC', 'PCT')"


def _tipos() -> None:
    op.execute("CREATE TYPE compras.fechamento_item AS ENUM ('nota', 'sem_nota', 'nao_comprei')")
    op.execute("ALTER TYPE compras.origem_item ADD VALUE IF NOT EXISTS 'nota'")


def _tabelas() -> None:
    # `pesada` exige g e sem conteúdo; não pesada com medida exige conteúdo;
    # sem medida, sem conteúdo. O coalesce impede que um nulo passe no check.
    op.execute(
        f"""
        CREATE TABLE compras.variantes (
          {_BASE},
          produto_id bigint NOT NULL REFERENCES compras.produtos (id),
          nome text NOT NULL CHECK (btrim(nome) <> ''),
          nome_normalizado text NOT NULL CHECK (nome_normalizado <> ''),
          marca text,
          gtin text CHECK (gtin ~ '^([0-9]{{8}}|[0-9]{{12,14}})$'),
          medida_base compras.medida_base,
          conteudo numeric(12,3),
          pesada boolean NOT NULL DEFAULT false,
          criado_por text NOT NULL CHECK (btrim(criado_por) <> ''),
          CONSTRAINT ck_variantes_medida_coerente CHECK (coalesce(
            (pesada AND medida_base = 'g' AND conteudo IS NULL)
            OR (NOT pesada AND medida_base IS NOT NULL AND conteudo > 0)
            OR (NOT pesada AND medida_base IS NULL AND conteudo IS NULL),
            false
          ))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_variantes_gtin ON compras.variantes (gtin) "
        "WHERE deleted_em IS NULL AND gtin IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_variantes_produto_id ON compras.variantes (produto_id)")
    # A fila "sem medida".
    op.execute(
        "CREATE INDEX ix_variantes_sem_medida ON compras.variantes (id) "
        "WHERE medida_base IS NULL AND deleted_em IS NULL"
    )

    op.execute(
        f"""
        CREATE TABLE compras.variante_codigos (
          {_BASE},
          variante_id bigint NOT NULL REFERENCES compras.variantes (id),
          mercado_id bigint NOT NULL REFERENCES compras.mercados (id),
          codigo text NOT NULL CHECK (codigo <> '' AND codigo !~ '^0'),
          criado_por text NOT NULL CHECK (btrim(criado_por) <> '')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_variante_codigos_mercado_codigo ON compras.variante_codigos "
        "(mercado_id, codigo) WHERE deleted_em IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_variante_codigos_variante_id ON compras.variante_codigos (variante_id)"
    )


def _triggers_das_tabelas_novas() -> None:
    for tabela in _TABELAS_NOVAS:
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


def _colunas() -> None:
    op.execute(
        """
        ALTER TABLE compras.nota_itens
          ADD COLUMN variante_id bigint REFERENCES compras.variantes (id),
          ADD COLUMN item_lista_id bigint REFERENCES compras.itens_lista (id)
        """
    )
    op.execute("CREATE INDEX ix_nota_itens_variante_id ON compras.nota_itens (variante_id)")
    op.execute("CREATE INDEX ix_nota_itens_item_lista_id ON compras.nota_itens (item_lista_id)")

    # Nulo até a migração de dados; NOT NULL depois dela.
    op.execute(
        "ALTER TABLE compras.apelidos ADD COLUMN variante_id bigint "
        "REFERENCES compras.variantes (id)"
    )

    op.execute(
        """
        ALTER TABLE compras.notas_fiscais
          ADD COLUMN conferida_em timestamptz,
          ADD COLUMN conferida_por text,
          ADD COLUMN pendente_id_externo text,
          ADD COLUMN forma_pagamento_nota text,
          ADD COLUMN despesa_lancada_pela_nota boolean NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        ALTER TABLE compras.notas_fiscais ADD CONSTRAINT ck_notas_fiscais_ligacao_unica CHECK (
          transacao_id IS NULL OR pendente_id_externo IS NULL
        )
        """
    )
    op.execute(
        """
        ALTER TABLE compras.itens_lista
          ADD COLUMN fechamento compras.fechamento_item,
          ADD COLUMN fechado_em timestamptz,
          ADD COLUMN fechado_por text,
          ADD COLUMN perguntado_em timestamptz
        """
    )
    # `nota` e `sem_nota` só em item comprado; `nao_comprei` só em linha apagada;
    # fechamento preenchido diz quando e por quem.
    op.execute(
        """
        ALTER TABLE compras.itens_lista ADD CONSTRAINT ck_itens_lista_fechamento_coerente CHECK (
          fechamento IS NULL
          OR (fechamento IN ('nota', 'sem_nota') AND situacao = 'comprado')
          OR (fechamento = 'nao_comprei' AND deleted_em IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE compras.itens_lista ADD CONSTRAINT ck_itens_lista_fechamento_com_autor CHECK (
          fechamento IS NULL OR (fechado_em IS NOT NULL AND fechado_por IS NOT NULL)
        )
        """
    )
    # "Comprado, aguardando nota": comprado sem fechamento.
    op.execute(
        "CREATE INDEX ix_itens_lista_aguardando_nota ON compras.itens_lista (comprado_em) "
        "WHERE situacao = 'comprado' AND fechamento IS NULL AND deleted_em IS NULL"
    )
    op.execute("ALTER TABLE compras.secoes ADD COLUMN categoria_id_financas bigint")


# --- migração de dados --------------------------------------------------------


def _normalizar(texto: str) -> str:
    """O mesmo de `compras.normalizar.normalizar`, copiado: a migration não
    depende de código que pode mudar."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return " ".join(sem_acento.upper().split())


_GTIN = re.compile(r"^([0-9]{8}|[0-9]{12,14})$")


def _criar_variante(
    bind: Any,
    produto_id: int,
    nome: str,
    *,
    gtin: str | None = None,
    pesada: bool = False,
    apagada: bool = False,
) -> int:
    return int(
        bind.execute(
            text(
                """
                INSERT INTO compras.variantes
                  (produto_id, nome, nome_normalizado, gtin, medida_base, pesada, criado_por,
                   deleted_em)
                VALUES (:p, :nome, :norm, :gtin, CAST(:base AS compras.medida_base), :pesada,
                        'migracao', CASE WHEN :apagada THEN now() END)
                RETURNING id
                """
            ),
            {
                "p": produto_id,
                "nome": nome,
                "norm": _normalizar(nome),
                "gtin": gtin if gtin and _GTIN.match(gtin) else None,
                "base": "g" if pesada else None,
                "pesada": pesada,
                "apagada": apagada,
            },
        ).scalar_one()
    )


def _migrar_dados() -> None:
    bind = op.get_bind()
    bind.execute(text("SELECT set_config('app.autor', 'migracao_0006', true)"))

    # 1. Apelido de GTIN -> variante com o GTIN; o apelido é apagado.
    por_gtin: dict[str, tuple[int, int]] = {}
    for apelido_id, produto_id, gtin in bind.execute(
        text(
            "SELECT id, produto_id, gtin FROM compras.apelidos "
            "WHERE gtin IS NOT NULL AND deleted_em IS NULL ORDER BY id"
        )
    ).all():
        nome = bind.execute(
            text(
                """
                SELECT i.descricao_original
                FROM compras.nota_itens i
                JOIN compras.notas_fiscais n ON n.id = i.nota_fiscal_id
                WHERE i.gtin = :g AND i.deleted_em IS NULL
                ORDER BY n.emitida_em DESC NULLS LAST, i.id DESC
                LIMIT 1
                """
            ),
            {"g": gtin},
        ).scalar()
        variante_id = _criar_variante(bind, produto_id, nome or f"GTIN {gtin}", gtin=gtin)
        por_gtin[gtin] = (variante_id, produto_id)
        bind.execute(
            text("UPDATE compras.apelidos SET variante_id = :v, deleted_em = now() WHERE id = :a"),
            {"v": variante_id, "a": apelido_id},
        )

    # 2. Item associado -> variante por GTIN já migrado, ou por
    #    (produto, descrição normalizada, mercado).
    grupos: dict[tuple[int, str, int | None], int] = {}
    unidades: dict[int, set[str]] = {}
    votos: dict[tuple[int, str], Counter[int]] = {}
    atribuicoes: list[dict[str, int]] = []
    itens = bind.execute(
        text(
            """
            SELECT i.id, i.produto_id, i.descricao_original, i.codigo, i.gtin, i.unidade,
                   n.mercado_id
            FROM compras.nota_itens i
            JOIN compras.notas_fiscais n ON n.id = i.nota_fiscal_id
            WHERE i.produto_id IS NOT NULL
            ORDER BY i.id
            """
        )
    ).all()
    for item_id, produto_id, descricao, codigo, gtin, unidade, mercado_id in itens:
        achada = por_gtin.get(gtin) if gtin else None
        if achada is not None and achada[1] == produto_id:
            variante_id = achada[0]
        else:
            chave = (produto_id, _normalizar(descricao), mercado_id)
            if chave not in grupos:
                # `pesada` é acertado depois, pelas unidades do grupo inteiro.
                grupos[chave] = _criar_variante(bind, produto_id, descricao)
            variante_id = grupos[chave]
        unidades.setdefault(variante_id, set()).add((unidade or "UN").strip().upper())
        atribuicoes.append({"v": variante_id, "i": item_id})
        sem_zeros = (codigo or "").strip().lstrip("0")
        if mercado_id is not None and sem_zeros and not re.search(r"\s", sem_zeros):
            votos.setdefault((mercado_id, sem_zeros), Counter())[variante_id] += 1

    if atribuicoes:
        bind.execute(
            text("UPDATE compras.nota_itens SET variante_id = :v WHERE id = :i"), atribuicoes
        )
    for variante_id, siglas in unidades.items():
        if siglas == {"KG"}:
            bind.execute(
                text("UPDATE compras.variantes SET pesada = true, medida_base = 'g' WHERE id = :v"),
                {"v": variante_id},
            )
    # O mesmo código no mesmo mercado só pode ficar com uma variante: a que
    # mais itens teve (empate: a mais antiga).
    for (mercado_id, codigo), contagem in sorted(votos.items()):
        variante_id = sorted(contagem.items(), key=lambda par: (-par[1], par[0]))[0][0]
        bind.execute(
            text(
                "INSERT INTO compras.variante_codigos (variante_id, mercado_id, codigo, criado_por) "
                "VALUES (:v, :m, :c, 'migracao')"
            ),
            {"v": variante_id, "m": mercado_id, "c": codigo},
        )

    # 3. Os demais apelidos (de texto, e os de GTIN que já estavam apagados).
    for apelido_id, produto_id, texto, mercado_id, gtin, apagado in bind.execute(
        text(
            "SELECT id, produto_id, texto_normalizado, mercado_id, gtin, deleted_em IS NOT NULL "
            "FROM compras.apelidos WHERE variante_id IS NULL ORDER BY id"
        )
    ).all():
        variante_id = None
        if texto is not None:
            variante_id = grupos.get((produto_id, texto, mercado_id))
            if variante_id is None:
                variante_id = next(
                    (v for (p, t, _m), v in grupos.items() if p == produto_id and t == texto),
                    None,
                )
        if variante_id is None:
            variante_id = _criar_variante(
                bind, produto_id, texto or f"GTIN {gtin}", apagada=bool(apagado)
            )
        bind.execute(
            text("UPDATE compras.apelidos SET variante_id = :v WHERE id = :a"),
            {"v": variante_id, "a": apelido_id},
        )

    # 4. O que já estava comprado antes da D-33 não espera nota.
    bind.execute(
        text(
            """
            UPDATE compras.itens_lista
            SET fechamento = 'sem_nota', fechado_em = now(), fechado_por = 'migracao'
            WHERE situacao = 'comprado'
            """
        )
    )


def _restricoes_e_sincronia() -> None:
    op.execute("ALTER TABLE compras.apelidos ALTER COLUMN variante_id SET NOT NULL")
    op.execute("CREATE INDEX ix_apelidos_variante_id ON compras.apelidos (variante_id)")
    # Item sem variante não está associado.
    op.execute(
        """
        ALTER TABLE compras.nota_itens ADD CONSTRAINT ck_nota_itens_variante_se_produto CHECK (
          variante_id IS NOT NULL OR produto_id IS NULL
        )
        """
    )

    # `produto_id` de `nota_itens` e de `apelidos` é cópia do produto da
    # variante: o trigger a refaz em todo INSERT e UPDATE.
    op.execute(
        """
        CREATE FUNCTION compras.fn_produto_da_variante() RETURNS trigger AS $$
        BEGIN
          IF NEW.variante_id IS NULL THEN
            NEW.produto_id := NULL;
          ELSE
            NEW.produto_id := (
              SELECT v.produto_id FROM compras.variantes v WHERE v.id = NEW.variante_id
            );
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for tabela in ("nota_itens", "apelidos"):
        op.execute(
            f"""
            CREATE TRIGGER tg_{tabela}_produto_da_variante
            BEFORE INSERT OR UPDATE ON compras.{tabela}
            FOR EACH ROW EXECUTE FUNCTION compras.fn_produto_da_variante()
            """
        )
    # E o caminho inverso: trocar a variante de produto leva os itens e os
    # apelidos junto.
    op.execute(
        """
        CREATE FUNCTION compras.fn_variante_troca_produto() RETURNS trigger AS $$
        BEGIN
          IF NEW.produto_id IS DISTINCT FROM OLD.produto_id THEN
            UPDATE compras.nota_itens SET produto_id = NEW.produto_id
              WHERE variante_id = NEW.id;
            UPDATE compras.apelidos SET produto_id = NEW.produto_id
              WHERE variante_id = NEW.id;
          END IF;
          RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER tg_variantes_troca_produto
        AFTER UPDATE OF produto_id ON compras.variantes
        FOR EACH ROW EXECUTE FUNCTION compras.fn_variante_troca_produto()
        """
    )


# --- views -----------------------------------------------------------------------


def _views() -> None:
    op.execute("DROP VIEW IF EXISTS compras.vw_preco_produto")
    # Uma linha por item de nota lida e associada. O desconto da nota inteira
    # (desconto_total menos os descontos de linha) é rateado entre TODOS os
    # itens vivos da nota, associados ou não, proporcional ao valor_total; o
    # resto do arredondamento vai para a linha de maior valor, e a soma dos
    # preços pagos fecha com o valor da nota. É estimativa: a página só
    # mostra o desconto da nota inteira.
    op.execute(
        f"""
        CREATE VIEW compras.vw_preco_variante AS
        WITH itens AS (
          SELECT
            i.id AS nota_item_id, i.nota_fiscal_id, i.variante_id, i.quantidade, i.unidade,
            i.valor_total, i.desconto, n.mercado_id, n.emitida_em,
            sum(i.valor_total) OVER por_nota AS soma_total,
            greatest(n.desconto_total - sum(i.desconto) OVER por_nota, 0) AS desconto_nota,
            row_number() OVER (
              PARTITION BY i.nota_fiscal_id ORDER BY i.valor_total DESC, i.linha_num
            ) AS posicao
          FROM compras.nota_itens i
          JOIN compras.notas_fiscais n ON n.id = i.nota_fiscal_id
          WHERE i.deleted_em IS NULL AND n.deleted_em IS NULL AND n.status = 'lida'
          WINDOW por_nota AS (PARTITION BY i.nota_fiscal_id)
        ), parte AS (
          SELECT *,
            CASE WHEN soma_total > 0
              THEN round(desconto_nota * valor_total / soma_total, 2) ELSE 0 END AS rateio_base
          FROM itens
        ), rateado AS (
          SELECT *,
            rateio_base + CASE WHEN posicao = 1 AND soma_total > 0
              THEN desconto_nota - sum(rateio_base) OVER (PARTITION BY nota_fiscal_id)
              ELSE 0 END AS desconto_rateado
          FROM parte
        ), medido AS (
          SELECT r.*, v.produto_id, v.medida_base, v.pesada,
            -- pesada: a quantidade da nota é o peso; senão, quantidade x conteúdo.
            CASE
              WHEN v.pesada AND upper(btrim(coalesce(r.unidade, ''))) = 'KG'
                THEN r.quantidade * 1000
              WHEN v.pesada AND upper(btrim(coalesce(r.unidade, ''))) = 'G' THEN r.quantidade
              WHEN NOT v.pesada AND v.conteudo IS NOT NULL
                AND upper(coalesce(nullif(btrim(r.unidade), ''), 'UN'))
                  IN {_UNIDADES_DE_CONTAGEM}
                THEN r.quantidade * v.conteudo
            END AS quantidade_comparavel
          FROM rateado r
          JOIN compras.variantes v ON v.id = r.variante_id
          WHERE r.variante_id IS NOT NULL
        )
        SELECT
          nota_item_id, nota_fiscal_id, variante_id, produto_id, mercado_id, emitida_em,
          quantidade, unidade,
          valor_total AS preco_cheio,
          desconto AS desconto_linha,
          desconto_rateado,
          valor_total - desconto - desconto_rateado AS preco_pago,
          desconto_rateado > 0 AS preco_pago_estimado,
          medida_base,
          pesada,
          quantidade_comparavel,
          CASE WHEN quantidade_comparavel > 0 THEN
            round(
              (valor_total - desconto - desconto_rateado) / quantidade_comparavel
                * CASE WHEN medida_base IN ('g', 'ml') THEN 1000 ELSE 1 END,
              4)
          END AS preco_comparavel,
          CASE medida_base WHEN 'g' THEN 'kg' WHEN 'ml' THEN 'l' WHEN 'un' THEN 'un' END AS por
        FROM medido
        """
    )
    # Por produto, mercado e medida da variante. Linha sem quantidade
    # comparável fica fora das estatísticas e entra só em `sem_comparavel`.
    op.execute(
        """
        CREATE VIEW compras.vw_preco_produto AS
        SELECT
          produto_id,
          mercado_id,
          medida_base,
          por,
          (array_agg(preco_comparavel
             ORDER BY emitida_em DESC NULLS LAST, nota_fiscal_id DESC, nota_item_id DESC)
             FILTER (WHERE preco_comparavel IS NOT NULL))[1] AS ultimo_comparavel,
          (array_agg(variante_id
             ORDER BY emitida_em DESC NULLS LAST, nota_fiscal_id DESC, nota_item_id DESC)
             FILTER (WHERE preco_comparavel IS NOT NULL))[1] AS ultima_variante_id,
          max(emitida_em) FILTER (WHERE preco_comparavel IS NOT NULL) AS ultima_compra_em,
          min(preco_comparavel) AS preco_min,
          max(preco_comparavel) AS preco_max,
          round(avg(preco_comparavel), 4) AS preco_medio,
          count(preco_comparavel) AS compras,
          count(*) FILTER (WHERE preco_comparavel IS NULL) AS sem_comparavel
        FROM compras.vw_preco_variante
        GROUP BY produto_id, mercado_id, medida_base, por
        """
    )


def upgrade() -> None:
    _tipos()
    _tabelas()
    _triggers_das_tabelas_novas()
    _colunas()
    _migrar_dados()
    _restricoes_e_sincronia()
    _views()


def _view_antiga() -> None:
    # A da 0002: preço por produto, mercado e unidade da nota.
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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS compras.vw_preco_produto")
    op.execute("DROP VIEW IF EXISTS compras.vw_preco_variante")
    _view_antiga()

    op.execute("SELECT set_config('app.autor', 'migracao_0006', true)")
    op.execute("DROP TRIGGER IF EXISTS tg_variantes_troca_produto ON compras.variantes")
    for tabela in ("nota_itens", "apelidos"):
        op.execute(f"DROP TRIGGER IF EXISTS tg_{tabela}_produto_da_variante ON compras.{tabela}")
    op.execute("DROP FUNCTION IF EXISTS compras.fn_variante_troca_produto()")
    op.execute("DROP FUNCTION IF EXISTS compras.fn_produto_da_variante()")

    # Os apelidos de GTIN que a subida apagou voltam; `produto_id` já é o certo.
    op.execute(
        """
        UPDATE compras.apelidos SET deleted_em = NULL
        WHERE gtin IS NOT NULL AND deleted_em IS NOT NULL
          AND variante_id IN (SELECT id FROM compras.variantes WHERE criado_por = 'migracao')
        """
    )
    op.execute("DROP INDEX IF EXISTS compras.ix_apelidos_variante_id")
    op.execute("ALTER TABLE compras.apelidos DROP COLUMN IF EXISTS variante_id")
    op.execute(
        "ALTER TABLE compras.nota_itens DROP CONSTRAINT IF EXISTS ck_nota_itens_variante_se_produto"
    )
    op.execute(
        "ALTER TABLE compras.nota_itens DROP COLUMN IF EXISTS item_lista_id, "
        "DROP COLUMN IF EXISTS variante_id"
    )
    for tabela in ("variante_codigos", "variantes"):
        op.execute(f"DROP TABLE IF EXISTS compras.{tabela}")

    op.execute("ALTER TABLE compras.secoes DROP COLUMN IF EXISTS categoria_id_financas")
    op.execute("DROP INDEX IF EXISTS compras.ix_itens_lista_aguardando_nota")
    op.execute(
        "ALTER TABLE compras.itens_lista DROP CONSTRAINT IF EXISTS ck_itens_lista_fechamento_com_autor"
    )
    op.execute(
        "ALTER TABLE compras.itens_lista DROP CONSTRAINT IF EXISTS ck_itens_lista_fechamento_coerente"
    )
    op.execute(
        """
        ALTER TABLE compras.itens_lista
          DROP COLUMN IF EXISTS perguntado_em,
          DROP COLUMN IF EXISTS fechado_por,
          DROP COLUMN IF EXISTS fechado_em,
          DROP COLUMN IF EXISTS fechamento
        """
    )
    op.execute(
        "ALTER TABLE compras.notas_fiscais DROP CONSTRAINT IF EXISTS ck_notas_fiscais_ligacao_unica"
    )
    op.execute(
        """
        ALTER TABLE compras.notas_fiscais
          DROP COLUMN IF EXISTS despesa_lancada_pela_nota,
          DROP COLUMN IF EXISTS forma_pagamento_nota,
          DROP COLUMN IF EXISTS pendente_id_externo,
          DROP COLUMN IF EXISTS conferida_por,
          DROP COLUMN IF EXISTS conferida_em
        """
    )
    op.execute("DROP TYPE IF EXISTS compras.fechamento_item")

    # O Postgres não remove valor de enum: recria `origem_item` sem `nota`
    # (o que a conferência criou vira manual), como a 0004 faz com `cardapio`.
    op.execute("UPDATE compras.itens_lista SET origem = 'manual' WHERE origem::text = 'nota'")
    op.execute("ALTER TABLE compras.itens_lista ALTER COLUMN origem DROP DEFAULT")
    op.execute("ALTER TYPE compras.origem_item RENAME TO origem_item_com_nota")
    op.execute("CREATE TYPE compras.origem_item AS ENUM ('manual', 'despensa', 'voz', 'cardapio')")
    op.execute(
        "ALTER TABLE compras.itens_lista ALTER COLUMN origem TYPE compras.origem_item "
        "USING origem::text::compras.origem_item"
    )
    op.execute("ALTER TABLE compras.itens_lista ALTER COLUMN origem SET DEFAULT 'manual'")
    op.execute("DROP TYPE compras.origem_item_com_nota")
