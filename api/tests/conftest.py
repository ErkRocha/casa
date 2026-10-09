"""Fixtures de teste.

Postgres de verdade, não SQLite: metade do que importa neste schema — enum
nativo, coluna gerada, índice parcial, trigger, view — não existe em SQLite.
Testar contra outro banco daria confiança falsa.

De onde vem esse Postgres:

* por padrão, um container efêmero via testcontainers (o caminho do CI e do
  ``make test``);
* se ``TEST_DATABASE_URL`` estiver no ambiente, usa esse banco e não sobe
  container nenhum — serve para rodar os testes sem Docker, contra um
  Postgres local. **O banco apontado é truncado entre testes**, então nunca
  aponte para dados que você queira manter.

A resolução acontece no import deste módulo, antes de qualquer ``import app``,
porque ``app.db`` cria o engine na importação e precisa da URL já pronta.
"""

import atexit
import os
from collections.abc import Iterator

import pytest

_url_externa = os.environ.get("TEST_DATABASE_URL")

if _url_externa:
    os.environ["DATABASE_URL"] = _url_externa
else:
    from testcontainers.postgres import PostgresContainer

    _postgres = PostgresContainer("postgres:16-alpine")
    _postgres.start()
    atexit.register(_postgres.stop)
    os.environ["DATABASE_URL"] = _postgres.get_connection_url(driver="psycopg")

os.environ["APP_AUTOR_PADRAO"] = "teste"

#: Senha da role read-only nos testes. Precisa existir *antes* de qualquer
#: `import app`, porque `app.insights.db` monta a engine na importação e
#: deriva a URL desta variável.
os.environ.setdefault("INSIGHTS_PASSWORD", "insights_de_teste")

# Só depois das variáveis de ambiente.
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from alembic import command  # noqa: E402
from app.config import url_para_alembic  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import run as rodar_seed  # noqa: E402
from scripts.aplicar_roles import aplicar as aplicar_roles  # noqa: E402

#: Tabelas limpas entre testes. `auditoria` junto: ela é populada por trigger
#: e cresce a cada escrita.
_TABELAS = (
    "auditoria",
    "relatorios",
    # Ingestão antes de `transacoes`: `importacao_itens` referencia as duas.
    "importacao_itens",
    "importacoes",
    "regras_categorizacao",
    "transacoes",
    "orcamentos",
    "locais",
    # Antes de `formas_pagamento` e `contas`, que ela referencia.
    "contas_pluggy",
    "formas_pagamento",
    # Antes de `categorias`, que ela referencia.
    "categorias_pluggy",
    "categorias",
    "contas",
    "pessoas",
)


@pytest.fixture(scope="session", autouse=True)
def _migrar() -> None:
    """Aplica as migrations uma vez por sessão de teste.

    É a própria migration que roda — nunca `create_all()` (regra 4). Se o DDL
    quebrar, o teste quebra aqui, que é onde deve quebrar.
    """
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["DATABASE_URL"]))
    command.upgrade(config, "head")

    # A role read-only da fase 6 nasce aqui, e não num fixture sob demanda,
    # porque `app.insights.db` já abriu a engine com essa credencial no import.
    # Rodar o mesmo `init_roles.sql` que o Docker roda tem um efeito colateral
    # desejado: se aquele arquivo quebrar, quebra na suíte, e não no primeiro
    # boot de um banco novo meses depois.
    from app.config import get_settings

    cfg = get_settings()
    aplicar_roles(cfg.database_url, cfg.insights_password, cfg.insights_role)


def _truncar() -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(_TABELAS)} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _limpar_banco() -> Iterator[None]:
    """Cada teste começa do zero.

    Limpa **antes** e depois. Só depois não bastava: rodando contra um banco
    reaproveitado (`TEST_DATABASE_URL`), o primeiro teste da sessão herdava o
    que a execução anterior deixou — e um teste de ingestão esbarrava no hash
    único do arquivo importado da vez passada.

    `TRUNCATE ... RESTART IDENTITY CASCADE` é mais rápido que recriar o schema
    e mantém triggers e índices no lugar.
    """
    _truncar()
    yield
    _truncar()


@pytest.fixture
def session() -> Iterator[Session]:
    with SessionLocal() as s:
        s.execute(text("SELECT set_config('app.autor', 'teste', false)"))
        yield s


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def semeado(session: Session) -> None:
    """Banco com o seed aplicado: duas pessoas, contas, categorias, formas."""
    rodar_seed()
    session.expire_all()
