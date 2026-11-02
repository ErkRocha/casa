"""Fixtures de teste do `compras`.

Postgres de verdade, como em finanças. De onde ele vem:

* com ``TEST_DATABASE_URL`` no ambiente (o modo local exporta), esse banco,
  com a credencial **dona**; os testes criam nele a role e o schema;
* sem ela, um container efêmero via testcontainers.

O serviço em si conecta só como ``casa_compras``. A URL dele é derivada da
dona com a credencial trocada, e precisa estar no ambiente **antes** de
qualquer ``import compras.db``, que monta o engine na importação.

A role é do cluster, não do banco: no modo local o banco de teste divide a
role com o de verdade. Por isso a senha vem de ``COMPRAS_DB_PASSWORD`` quando
existe; inventar outra aqui trocaria a senha do serviço que está no ar.
"""

import atexit
import os
from collections.abc import Iterator

import pytest

_url_externa = os.environ.get("TEST_DATABASE_URL")
if _url_externa:
    URL_DONO = _url_externa
else:
    from testcontainers.postgres import PostgresContainer

    _postgres = PostgresContainer("postgres:16-alpine")
    _postgres.start()
    atexit.register(_postgres.stop)
    URL_DONO = _postgres.get_connection_url(driver="psycopg")

SENHA = os.environ.get("COMPRAS_DB_PASSWORD") or "compras_de_teste"

from compras.config import url_com_role, url_para_alembic  # noqa: E402

os.environ["COMPRAS_DATABASE_URL"] = url_com_role(URL_DONO, SENHA)
os.environ["COMPRAS_ROOT_PATH"] = ""

from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from compras.db import SessionLocal, definir_autor, engine  # noqa: E402
from compras.main import app  # noqa: E402
from compras.seed import run as rodar_seed  # noqa: E402
from scripts.aplicar_role import aplicar as aplicar_role  # noqa: E402

_TABELAS = (
    "auditoria",
    "identidades_tailscale",
    "apelidos",
    "nota_itens",
    "notas_fiscais",
    "mercados",
    "despensa",
    "itens_lista",
    "produtos",
    "secoes",
)


@pytest.fixture(scope="session", autouse=True)
def _preparar() -> None:
    """Role e schema pelo mesmo script da produção, e as migrations como a role.

    Se o script ou a migration quebrar, quebra aqui, e não no primeiro
    `make compras-role` de um banco novo.
    """
    aplicar_role(URL_DONO, SENHA)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["COMPRAS_DATABASE_URL"]))
    command.upgrade(config, "head")


def _truncar() -> None:
    # Como `casa_compras`: o trigger do schema recusaria qualquer outra role.
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE "
                + ", ".join(f"compras.{t}" for t in _TABELAS)
                + " RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture(autouse=True)
def _limpar_banco() -> Iterator[None]:
    _truncar()
    yield
    _truncar()


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as s:
        definir_autor(s, "teste")
        yield s


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def semeado() -> None:
    rodar_seed()


@pytest.fixture
def url_dono() -> str:
    return URL_DONO
