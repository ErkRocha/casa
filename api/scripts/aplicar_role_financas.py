"""Cria (ou repara) a role `casa_financas` e passa a ela os objetos de finanças (D-26).

    DATABASE_ADMIN_URL=... FINANCAS_DB_PASSWORD=... python -m scripts.aplicar_role_financas

Roda com a credencial de **administração** (o superusuário): só ela cria
role e transfere posse. Idempotente. O que faz, numa transação:

1. cria a role `casa_financas` (LOGIN, sem SUPERUSER, CREATEROLE, CREATEDB,
   REPLICATION nem BYPASSRLS) ou repara os atributos e a senha;
2. dá CONNECT no banco e USAGE e CREATE no schema `public`;
3. passa a ela a posse de todo objeto do schema `public`: tabelas, views,
   sequências soltas, funções e tipos;
4. refaz o SELECT da role de insights (D-11) e o default privilege dos
   objetos que `casa_financas` criar daqui em diante;
5. tira dela qualquer acesso ao schema `compras` (D-25).

Depois conecta **como** `casa_financas` e confere, tentando: lê finanças;
não cria role; não altera a role de insights; não escreve em `compras`.
Garantia que ninguém verifica é intenção.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import quote, urlsplit, urlunsplit

from psycopg import sql as pgsql
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.exc import DBAPIError

from app.config import com_connect_timeout

ROLE = "casa_financas"
INSIGHTS = "casa_insights"
PRIVILEGIO_INSUFICIENTE = "42501"

#: Objetos do schema `public` que não pertencem a `casa_financas`, com o
#: comando que muda o dono de cada um. Sequência de identidade ou de coluna
#: `serial` fica de fora: ela muda junto com a tabela, e o Postgres recusa
#: mudar só ela.
_FORA_DE_POSSE = """
SELECT format('ALTER %s %s OWNER TO casa_financas',
              CASE c.relkind
                WHEN 'v' THEN 'VIEW'
                WHEN 'm' THEN 'MATERIALIZED VIEW'
                WHEN 'S' THEN 'SEQUENCE'
                ELSE 'TABLE'
              END,
              c.oid::regclass)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
  AND pg_get_userbyid(c.relowner) <> 'casa_financas'
  AND NOT (c.relkind = 'S' AND EXISTS (
        SELECT 1 FROM pg_depend d
        WHERE d.objid = c.oid AND d.classid = 'pg_class'::regclass
          AND d.deptype IN ('a', 'i')))
UNION ALL
SELECT format('ALTER ROUTINE %s OWNER TO casa_financas', p.oid::regprocedure)
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) <> 'casa_financas'
UNION ALL
SELECT format('ALTER TYPE %s OWNER TO casa_financas', t.oid::regtype)
FROM pg_type t
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'public'
  AND t.typtype IN ('e', 'd', 'r', 'm')
  AND pg_get_userbyid(t.typowner) <> 'casa_financas'
"""

#: Quantos objetos do `public` ainda não são dela (tem que dar zero).
CONTAR_FORA_DE_POSSE = f"SELECT count(*) FROM ({_FORA_DE_POSSE}) AS fora"


def url_com_role(url: str, senha: str, role: str = ROLE) -> str:
    """A mesma URL (host, porta, banco) com a credencial trocada."""
    partes = urlsplit(url)
    hospedeiro = partes.hostname or "localhost"
    if partes.port:
        hospedeiro = f"{hospedeiro}:{partes.port}"
    credencial = f"{role}:{quote(senha, safe='')}"
    return urlunsplit((partes.scheme, f"{credencial}@{hospedeiro}", partes.path, partes.query, ""))


def aplicar(url_admin: str, senha: str) -> int:
    """Aplica tudo; devolve quantos objetos mudaram de dono."""
    engine = create_engine(com_connect_timeout(url_admin), pool_pre_ping=True)
    try:
        with engine.begin() as c:
            existe = c.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE}
            ).scalar()
            banco = str(c.execute(text("SELECT current_database()")).scalar_one())
            role = pgsql.Identifier(ROLE)
            comandos: list[pgsql.Composable] = [
                pgsql.SQL(
                    "{} ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(pgsql.SQL("ALTER" if existe else "CREATE"), role, pgsql.Literal(senha)),
                pgsql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    pgsql.Identifier(banco), role
                ),
                pgsql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(role),
            ]
            _executar(c, comandos)

            transferencias = [str(linha[0]) for linha in c.execute(text(_FORA_DE_POSSE))]
            for comando in transferencias:
                c.exec_driver_sql(comando)

            # D-11: insights lê tudo de finanças, agora e no futuro. O default
            # privilege é por quem cria; quem cria passa a ser casa_financas.
            tem_insights = c.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": INSIGHTS}
            ).scalar()
            if tem_insights:
                ins = pgsql.Identifier(INSIGHTS)
                _executar(
                    c,
                    [
                        pgsql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(ins),
                        pgsql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(ins),
                        pgsql.SQL(
                            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
                            "GRANT SELECT ON TABLES TO {}"
                        ).format(role, ins),
                    ],
                )

            # D-25: nenhum acesso ao schema do compras. Sem GRANT ela já não
            # tem; o REVOKE desfaz um GRANT antigo que alguém tenha dado.
            tem_compras = c.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname = 'compras'")
            ).scalar()
            if tem_compras:
                _executar(
                    c,
                    [
                        pgsql.SQL("REVOKE ALL ON SCHEMA compras FROM {}").format(role),
                        pgsql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA compras FROM {}").format(
                            role
                        ),
                    ],
                )
            return len(transferencias)
    finally:
        engine.dispose()


def _executar(c: Connection, comandos: list[pgsql.Composable]) -> None:
    # DDL não aceita bind parameter: o `sql` do psycopg escapa identificador
    # e literal pelas regras do servidor.
    bruta = c.connection.dbapi_connection
    with bruta.cursor() as cursor:  # type: ignore[union-attr]
        for comando in comandos:
            cursor.execute(comando)


def _recusado(c: Connection, comando: str) -> bool:
    """Roda num savepoint; True se o Postgres recusou por privilégio."""
    try:
        with c.begin_nested():
            c.exec_driver_sql(comando)
    except DBAPIError as erro:
        codigo = getattr(erro.orig, "sqlstate", None)
        if codigo != PRIVILEGIO_INSUFICIENTE:
            raise SystemExit(
                f"ABORTADO: '{comando}' falhou por {codigo}, não por privilégio."
            ) from erro
        return True
    return False


def verificar(url_admin: str, senha: str) -> list[str]:
    """Problemas encontrados (lista vazia = tudo certo)."""
    problemas: list[str] = []
    admin = create_engine(com_connect_timeout(url_admin))
    financas = create_engine(com_connect_timeout(url_com_role(url_admin, senha)))
    try:
        with admin.connect() as c:
            fora = int(c.execute(text(CONTAR_FORA_DE_POSSE)).scalar_one())
            if fora:
                problemas.append(f"{fora} objeto(s) do public ainda não são de {ROLE}")
            atributos = c.execute(
                text(
                    "SELECT rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls "
                    "OR rolreplication FROM pg_roles WHERE rolname = :r"
                ),
                {"r": ROLE},
            ).scalar_one()
            if atributos:
                problemas.append(f"{ROLE} tem atributo de administração")
            tem_insights = c.execute(
                text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": INSIGHTS}
            ).scalar()
            tem_compras = c.execute(
                text("SELECT 1 FROM pg_namespace WHERE nspname = 'compras'")
            ).scalar()

        with financas.connect() as c:
            if c.execute(text("SELECT current_user")).scalar_one() != ROLE:
                problemas.append("a conexão não é como casa_financas")
            c.execute(text("SELECT count(*) FROM alembic_version")).scalar_one()
            if not _recusado(c, "CREATE ROLE sonda_d26"):
                problemas.append(f"{ROLE} criou uma role")
            if tem_insights and not _recusado(c, f"ALTER ROLE {INSIGHTS} CONNECTION LIMIT 1"):
                problemas.append(f"{ROLE} alterou a role de insights")
            if tem_compras and not _recusado(
                c, "INSERT INTO compras.secoes (nome, ordem) VALUES ('sonda_d26', 1)"
            ):
                problemas.append(f"{ROLE} escreveu em compras")
            c.rollback()
    finally:
        admin.dispose()
        financas.dispose()
    return problemas


def main() -> int:
    url_admin = os.environ.get("DATABASE_ADMIN_URL")
    senha = os.environ.get("FINANCAS_DB_PASSWORD")
    if not url_admin or not senha:
        print(
            "Defina DATABASE_ADMIN_URL (superusuário) e FINANCAS_DB_PASSWORD "
            "(a senha da role casa_financas).",
            file=sys.stderr,
        )
        return 2
    transferidos = aplicar(url_admin, senha)
    problemas = verificar(url_admin, senha)
    if problemas:
        for p in problemas:
            print(f"ABORTADO: {p}.", file=sys.stderr)
        return 1
    print(
        f"role {ROLE} pronta: {transferidos} objeto(s) mudaram de dono; não cria role, "
        "não altera a de insights, não escreve em compras (42501). D-26 satisfeita."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
