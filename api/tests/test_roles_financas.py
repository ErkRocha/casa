"""D-26: a API de finanças roda como `casa_financas`, sem superusuário.

Provado tentando: ela lê, escreve e migra finanças; não cria role, não
altera a role de insights e não escreve no schema `compras`. Insights segue
só leitura, inclusive nas tabelas que `casa_financas` criar depois.
"""

from collections.abc import Iterator

import pytest
from alembic.config import Config
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from alembic import command
from app.config import get_settings, url_para_alembic
from app.db import engine
from scripts.aplicar_role_financas import (
    CONTAR_FORA_DE_POSSE,
    ROLE,
    aplicar,
    verificar,
)
from tests.conftest import SENHA_FINANCAS, URL_ADMIN

PRIVILEGIO_INSUFICIENTE = "42501"
SONDA = "_sonda_d26"


@pytest.fixture
def admin() -> Iterator[Engine]:
    e = create_engine(URL_ADMIN)
    yield e
    e.dispose()


@pytest.fixture
def insights() -> Iterator[Engine]:
    e = create_engine(get_settings().insights_database_url)
    yield e
    e.dispose()


def _recusado(c: Connection, sql: str) -> bool:
    try:
        with c.begin_nested():
            c.exec_driver_sql(sql)
    except DBAPIError as erro:
        codigo = getattr(erro.orig, "sqlstate", None)
        assert codigo == PRIVILEGIO_INSUFICIENTE, f"{sql}: falhou por {codigo}, não privilégio"
        return True
    return False


def test_api_conecta_como_casa_financas_sem_poderes(admin: Engine) -> None:
    with engine.connect() as c:
        assert c.execute(text("SELECT current_user")).scalar_one() == ROLE
    with admin.connect() as c:
        linha = c.execute(
            text(
                "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls, rolreplication, "
                "rolcanlogin FROM pg_roles WHERE rolname = :r"
            ),
            {"r": ROLE},
        ).one()
        assert tuple(linha) == (False, False, False, False, False, True)
        assert c.execute(text(CONTAR_FORA_DE_POSSE)).scalar_one() == 0


def test_casa_financas_le_e_escreve_financas() -> None:
    with engine.begin() as c:
        c.execute(text("INSERT INTO pessoas (nome) VALUES ('Sonda D-26')"))
        assert c.execute(text("SELECT count(*) FROM pessoas")).scalar_one() == 1
        c.execute(text("UPDATE pessoas SET nome = 'Sonda'"))
        c.execute(text("UPDATE pessoas SET deleted_em = now()"))


def test_casa_financas_roda_migrations() -> None:
    """Desce uma migration e sobe de novo: DROP e CREATE como ela."""
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(str(get_settings().database_url)))
    command.downgrade(config, "-1")
    command.upgrade(config, "head")
    with engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM categorias_pluggy")).scalar_one() == 0


def test_casa_financas_nao_cria_role_nem_altera_insights() -> None:
    with engine.connect() as c:
        assert _recusado(c, "CREATE ROLE sonda_d26 LOGIN")
        assert _recusado(c, "ALTER ROLE casa_insights PASSWORD 'tomada'")
        assert _recusado(c, "ALTER ROLE casa_insights SUPERUSER")
        assert _recusado(c, "DROP ROLE casa_insights")
        assert _recusado(c, f"ALTER ROLE {ROLE} SUPERUSER")


@pytest.fixture
def outro_schema(admin: Engine) -> Iterator[None]:
    """Um schema que não é de finanças, garantido mesmo num banco vazio."""
    with admin.begin() as c:
        c.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SONDA}"))
        c.execute(text(f"CREATE TABLE IF NOT EXISTS {SONDA}.t (id int)"))
    yield
    with admin.begin() as c:
        c.execute(text(f"DROP SCHEMA IF EXISTS {SONDA} CASCADE"))


@pytest.mark.usefixtures("outro_schema")
def test_casa_financas_nao_escreve_fora_de_financas(admin: Engine) -> None:
    with admin.connect() as c:
        tem_compras = c.execute(
            text("SELECT 1 FROM pg_namespace WHERE nspname = 'compras'")
        ).scalar()
    with engine.connect() as c:
        assert _recusado(c, f"INSERT INTO {SONDA}.t VALUES (1)")
        assert _recusado(c, f"SELECT * FROM {SONDA}.t")
        if tem_compras:
            # Por permissão, não pelo trigger: nem USAGE no schema ela tem.
            assert _recusado(c, "INSERT INTO compras.secoes (nome, ordem) VALUES ('sonda_d26', 1)")
            assert _recusado(c, "SELECT * FROM compras.itens_lista")
        alcancados = c.execute(
            text(
                """
                SELECT count(*) FROM pg_namespace n
                WHERE n.nspname NOT IN ('public', 'pg_catalog', 'information_schema')
                  AND n.nspname NOT LIKE 'pg_toast%'
                  AND n.nspname NOT LIKE 'pg_temp%'
                  AND has_schema_privilege(n.oid, 'USAGE, CREATE')
                """
            )
        ).scalar_one()
        assert alcancados == 0


def test_insights_continua_so_leitura(insights: Engine) -> None:
    with insights.connect() as c:
        assert c.execute(text("SELECT count(*) FROM transacoes")).scalar_one() == 0
        assert _recusado(c, "INSERT INTO pessoas (nome) VALUES ('intruso')")
        assert _recusado(c, "UPDATE transacoes SET valor = 1")
        assert _recusado(c, "CREATE TABLE intrusa (id int)")


def test_insights_le_o_que_casa_financas_criar_depois(insights: Engine) -> None:
    """O default privilege é de quem cria: agora, `casa_financas`."""
    with engine.begin() as c:
        c.execute(text("CREATE TABLE sonda_d26_nova (id int)"))
    try:
        with insights.connect() as c:
            assert c.execute(text("SELECT count(*) FROM sonda_d26_nova")).scalar_one() == 0
            assert _recusado(c, "INSERT INTO sonda_d26_nova VALUES (1)")
    finally:
        with engine.begin() as c:
            c.execute(text("DROP TABLE sonda_d26_nova"))


def test_script_e_idempotente_e_a_verificacao_passa() -> None:
    aplicar(URL_ADMIN, SENHA_FINANCAS)
    assert aplicar(URL_ADMIN, SENHA_FINANCAS) == 0
    assert verificar(URL_ADMIN, SENHA_FINANCAS) == []
