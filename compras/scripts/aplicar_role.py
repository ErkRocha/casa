"""Cria (ou repara) a role `casa_compras` e o schema `compras`, e confere (D-25).

    COMPRAS_DONO_DATABASE_URL=... COMPRAS_DB_PASSWORD=... python -m scripts.aplicar_role

Roda com a credencial **dona do banco** (a de finanças), porque só ela cria
role e schema. Essa credencial vem por variável só desta execução e nunca
fica no serviço: o container do `compras` conhece apenas a própria role.

Idempotente. O que faz:

1. cria a role `casa_compras` (LOGIN, sem superusuário, sem criar banco nem
   role) ou repara os atributos e a senha;
2. dá CONNECT no banco, cria o schema `compras` com ela como dona e fixa o
   `search_path` dela neste banco;
3. conecta como a role e confere que ela não tem privilégio em nenhuma
   tabela fora do schema dela. Garantia que ninguém verifica é intenção.
"""

from __future__ import annotations

import os
import sys

from psycopg import sql as pgsql
from sqlalchemy import create_engine, text

from compras.config import ROLE, SCHEMA, com_connect_timeout, url_com_role


def aplicar(url_dono: str, senha: str) -> None:
    engine = create_engine(com_connect_timeout(url_dono), pool_pre_ping=True)
    try:
        with engine.begin() as conexao:
            existe = conexao.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
            ).scalar()
            banco = str(conexao.execute(text("SELECT current_database()")).scalar_one())

            # DDL não aceita bind parameter: quem monta identificador e
            # literal é o `sql` do psycopg, que escapa pelas regras do servidor.
            role = pgsql.Identifier(ROLE)
            comandos = [
                pgsql.SQL(
                    "{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(pgsql.SQL("ALTER" if existe else "CREATE"), role, pgsql.Literal(senha)),
                pgsql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    pgsql.Identifier(banco), role
                ),
                pgsql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION {}").format(
                    pgsql.Identifier(SCHEMA), role
                ),
                pgsql.SQL("ALTER SCHEMA {} OWNER TO {}").format(pgsql.Identifier(SCHEMA), role),
                pgsql.SQL("ALTER ROLE {} IN DATABASE {} SET search_path = {}").format(
                    role, pgsql.Identifier(banco), pgsql.Identifier(SCHEMA)
                ),
                # Explícito, mesmo que o padrão já seja este: no schema de
                # finanças ela não cria nada.
                pgsql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(role),
            ]
            bruta = conexao.connection.dbapi_connection
            with bruta.cursor() as cursor:  # type: ignore[union-attr]
                for comando in comandos:
                    cursor.execute(comando)
    finally:
        engine.dispose()


def verificar(url_role: str) -> int:
    """Conecta como a role; devolve quantos objetos fora de `compras` ela alcança.

    Tem que ser zero. Conta tabelas, views e sequências de todo schema que
    não seja o dela nem os de sistema.
    """
    engine = create_engine(com_connect_timeout(url_role), pool_pre_ping=True)
    try:
        with engine.connect() as conexao:
            return int(
                conexao.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE c.relkind IN ('r', 'v', 'm', 'p', 'S')
                          AND n.nspname NOT IN (:schema, 'pg_catalog', 'information_schema')
                          AND n.nspname NOT LIKE 'pg_toast%'
                          AND (
                            has_table_privilege(c.oid,
                              'SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER')
                          )
                        """
                    ),
                    {"schema": SCHEMA},
                ).scalar_one()
            )
    finally:
        engine.dispose()


def main() -> int:
    url_dono = os.environ.get("COMPRAS_DONO_DATABASE_URL")
    senha = os.environ.get("COMPRAS_DB_PASSWORD")
    if not url_dono or not senha:
        print(
            "Defina COMPRAS_DONO_DATABASE_URL (a URL dona do banco, a de finanças) e "
            "COMPRAS_DB_PASSWORD (a senha da role casa_compras).",
            file=sys.stderr,
        )
        return 2

    aplicar(url_dono, senha)
    alcancados = verificar(url_com_role(url_dono, senha))
    if alcancados:
        print(
            f"ABORTADO: a role {ROLE} tem privilégio em {alcancados} objeto(s) fora do "
            f"schema {SCHEMA}. Revogue antes de usar (D-25).",
            file=sys.stderr,
        )
        return 1
    print(f"role {ROLE} pronta: dona do schema {SCHEMA}, 0 objeto(s) alcançado(s) fora dele.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
