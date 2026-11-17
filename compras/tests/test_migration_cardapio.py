"""A migration 0004 aplica e reverte (D-30).

O downgrade recria o enum `origem_item` sem `cardapio`; o que veio do
cardápio vira manual. O teste devolve o banco ao `head` no fim, de qualquer
jeito: os outros testes dependem dele.
"""

import os

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from compras.config import url_para_alembic
from compras.db import SessionLocal, engine

TABELAS = (
    "pessoas",
    "receitas",
    "receita_ingredientes",
    "semanas",
    "refeicoes",
    "refeicao_pessoas",
    "sessoes_preparo",
    "itens_lista_cardapio",
)


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["COMPRAS_DATABASE_URL"]))
    return config


def _tabelas_do_cardapio() -> set[str]:
    with engine.connect() as c:
        achadas = c.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'compras'")
        ).scalars()
        return {t for t in achadas if t in TABELAS}


def _colunas_de_produtos() -> set[str]:
    with engine.connect() as c:
        return set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'compras' AND table_name = 'produtos'"
                )
            ).scalars()
        )


def test_migration_0004_reverte_e_aplica_de_novo() -> None:
    with SessionLocal() as s:
        secao = s.execute(
            text("INSERT INTO compras.secoes (nome, ordem) VALUES ('Mig', 1) RETURNING id")
        ).scalar_one()
        produto = s.execute(
            text(
                "INSERT INTO compras.produtos (nome, nome_normalizado, secao_id) "
                "VALUES ('Mig', 'MIG', :s) RETURNING id"
            ),
            {"s": secao},
        ).scalar_one()
        s.execute(
            text(
                "INSERT INTO compras.itens_lista (produto_id, origem, adicionado_por) "
                "VALUES (:p, 'cardapio', 'teste')"
            ),
            {"p": produto},
        )
        s.commit()

    config = _config()
    try:
        command.downgrade(config, "0003")
        assert _tabelas_do_cardapio() == set()
        assert not {"medida_base", "medida_por_unidade"} & _colunas_de_produtos()
        with engine.connect() as c:
            origem = c.execute(text("SELECT origem::text FROM compras.itens_lista")).scalar_one()
            valores = set(
                c.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid "
                        "JOIN pg_namespace n ON n.oid = t.typnamespace "
                        "WHERE n.nspname = 'compras' AND t.typname = 'origem_item'"
                    )
                ).scalars()
            )
        assert origem == "manual"
        assert valores == {"manual", "despensa", "voz"}
    finally:
        command.upgrade(config, "head")

    assert _tabelas_do_cardapio() == set(TABELAS)
    assert {"medida_base", "medida_por_unidade"} <= _colunas_de_produtos()
    with engine.connect() as c:
        assert (
            c.execute(text("SELECT 'cardapio'::compras.origem_item::text")).scalar_one()
            == "cardapio"
        )
