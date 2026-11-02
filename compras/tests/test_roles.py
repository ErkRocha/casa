"""As fronteiras do schema `compras` (D-25), provadas tentando atravessá-las.

* `casa_compras` não lê nem escreve nada fora do schema dela;
* a role de finanças não escreve no schema `compras`.

O Postgres recusa nos dois sentidos com 42501 (`insufficient_privilege`). No
segundo, quem recusa é o trigger da migration 0001: a role de finanças é
superusuária, e superusuário passa por cima de todo GRANT.
"""

from collections.abc import Iterator

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from compras.config import ROLE, url_com_role
from scripts.aplicar_role import aplicar, verificar
from tests.conftest import SENHA

PRIVILEGIO_INSUFICIENTE = "42501"
SONDA = "_sonda_compras"


@pytest.fixture
def dono(url_dono: str) -> Iterator[Engine]:
    engine = create_engine(url_dono)
    yield engine
    engine.dispose()


@pytest.fixture
def role_compras(url_dono: str) -> Iterator[Engine]:
    engine = create_engine(url_com_role(url_dono, SENHA))
    yield engine
    engine.dispose()


@pytest.fixture
def sonda_em_public(dono: Engine) -> Iterator[None]:
    """Uma tabela de finanças garantida, mesmo num banco de teste vazio.

    No container efêmero o schema `public` não tem as tabelas de finanças;
    sem a sonda, "não alcança nenhuma" passaria sem testar nada.
    """
    with dono.begin() as c:
        c.execute(text(f"CREATE TABLE IF NOT EXISTS public.{SONDA} (id int, nome text)"))
        c.execute(text(f"INSERT INTO public.{SONDA} VALUES (1, 'finanças')"))
    yield
    with dono.begin() as c:
        c.execute(text(f"DROP TABLE IF EXISTS public.{SONDA}"))


def _recusado(conexao: Connection, sql: str) -> bool:
    """Roda `sql` num savepoint; True se o Postgres recusou por privilégio."""
    try:
        with conexao.begin_nested():
            conexao.execute(text(sql))
    except DBAPIError as erro:
        codigo = getattr(erro.orig, "sqlstate", None)
        assert codigo == PRIVILEGIO_INSUFICIENTE, f"{sql}: falhou por {codigo}, não privilégio"
        return True
    return False


def _objetos_de_financas(dono: Engine) -> list[tuple[str, str, bool]]:
    """(schema, nome, é tabela) de tudo fora de `compras` e dos schemas de sistema."""
    with dono.connect() as c:
        return [
            (str(s), str(n), bool(tabela))
            for s, n, tabela in c.execute(
                text(
                    """
                    SELECT n.nspname, c.relname, c.relkind IN ('r', 'p')
                    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                    WHERE c.relkind IN ('r', 'v', 'm', 'p')
                      AND n.nspname NOT IN ('compras', 'pg_catalog', 'information_schema')
                      AND n.nspname NOT LIKE 'pg_toast%'
                    ORDER BY 1, 2
                    """
                )
            )
        ]


@pytest.mark.usefixtures("sonda_em_public")
def test_casa_compras_nao_le_nem_escreve_fora_do_schema(
    dono: Engine, role_compras: Engine, url_dono: str
) -> None:
    objetos = _objetos_de_financas(dono)
    assert ("public", SONDA, True) in objetos

    with role_compras.connect() as c:
        for schema, nome, tabela in objetos:
            alvo = f'"{schema}"."{nome}"'
            assert _recusado(c, f"SELECT * FROM {alvo} LIMIT 1"), f"leu {alvo}"
            # View que não aceita escrita recusa por outro motivo (55000);
            # a escrita se prova nas tabelas.
            if tabela:
                assert _recusado(c, f"INSERT INTO {alvo} DEFAULT VALUES"), f"inseriu em {alvo}"
                assert _recusado(c, f"DELETE FROM {alvo}"), f"apagou de {alvo}"
        assert _recusado(c, f"UPDATE public.{SONDA} SET nome = 'x'")
        assert _recusado(c, f"TRUNCATE public.{SONDA}")
        assert _recusado(c, "CREATE TABLE public.criada_por_compras (id int)")

    # A mesma conta pelo catálogo, que o `make compras-role` imprime.
    assert verificar(url_com_role(url_dono, SENHA)) == 0


def test_role_de_financas_nao_escreve_em_compras(dono: Engine, role_compras: Engine) -> None:
    with role_compras.begin() as c:
        c.execute(text("INSERT INTO compras.secoes (nome, ordem) VALUES ('Padaria', 1)"))

    with dono.connect() as c:
        assert c.execute(
            text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
        ).scalar()
        assert _recusado(c, "INSERT INTO compras.secoes (nome, ordem) VALUES ('Intrusa', 2)")
        assert _recusado(c, "UPDATE compras.secoes SET nome = 'Outra'")
        assert _recusado(c, "DELETE FROM compras.secoes")
        assert _recusado(c, "TRUNCATE compras.despensa")
        assert _recusado(
            c,
            "INSERT INTO compras.auditoria (tabela, registro_id, acao, autor) "
            "VALUES ('x', 1, 'INSERT', 'intruso')",
        )
        # Ler pode: superusuário lê tudo, e a D-25 não pede o contrário.
        assert c.execute(text("SELECT nome FROM compras.secoes")).scalar_one() == "Padaria"


def test_role_sem_poderes_e_dona_do_schema(dono: Engine) -> None:
    with dono.connect() as c:
        linha = c.execute(
            text(
                "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolcanlogin "
                "FROM pg_roles WHERE rolname = :r"
            ),
            {"r": ROLE},
        ).one()
        assert tuple(linha) == (False, False, False, False, True)
        dona = c.execute(
            text("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'compras'")
        ).scalar_one()
        assert dona == ROLE
        versao = c.execute(text("SELECT version_num FROM compras.alembic_version")).scalar_one()
        # A última migration do serviço.
        head = ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        assert versao == head


def test_aplicar_role_e_idempotente(url_dono: str, role_compras: Engine) -> None:
    aplicar(url_dono, SENHA)
    aplicar(url_dono, SENHA)
    with role_compras.connect() as c:
        assert c.execute(text("SELECT current_user")).scalar_one() == ROLE
        assert c.execute(text("SHOW search_path")).scalar_one() == "compras"


def test_toda_tabela_do_schema_tem_o_trigger_de_protecao(dono: Engine) -> None:
    """Toda tabela de `compras`, inclusive as que vierem depois, recusa escrita
    de outra role. Pelo catálogo: tabela nova sem o trigger quebra aqui."""
    with dono.connect() as c:
        sem_trigger = (
            c.execute(
                text(
                    """
                SELECT cl.relname
                FROM pg_class cl
                JOIN pg_namespace n ON n.oid = cl.relnamespace
                WHERE n.nspname = 'compras' AND cl.relkind = 'r'
                  AND cl.relname <> 'alembic_version'
                  AND NOT EXISTS (
                    SELECT 1 FROM pg_trigger t
                    JOIN pg_proc p ON p.oid = t.tgfoid
                    WHERE t.tgrelid = cl.oid AND p.proname = 'fn_somente_casa_compras'
                  )
                """
                )
            )
            .scalars()
            .all()
        )
        tabelas = c.execute(
            text(
                "SELECT count(*) FROM pg_tables WHERE schemaname = 'compras' "
                "AND tablename <> 'alembic_version'"
            )
        ).scalar_one()
    assert sem_trigger == []
    assert tabelas == 10
