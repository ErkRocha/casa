"""Toda URL de banco montada pelo projeto leva connect_timeout.

Sem ele, banco fora do ar (Docker parado, porta fechada) prendia a API e os
scripts por minutos — no Windows, conectar numa porta local fechada não é
recusado na hora. Com ele, falha em segundos com erro claro.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from app.config import CONNECT_TIMEOUT_S, Settings, com_connect_timeout, url_para_alembic
from scripts._host import url_do_host
from tests_sem_banco._falsos import CONFIG, montar_ambiente, sem_shell

BASE = "postgresql+psycopg://casa:s%40nha%3A1%2F2@127.0.0.1:5432/casa"


def _parametros(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_acrescenta_quando_falta() -> None:
    url = com_connect_timeout(BASE)
    assert _parametros(url) == {"connect_timeout": [str(CONNECT_TIMEOUT_S)]}
    # Credencial, host e banco intactos.
    partes = urlsplit(url)
    assert unquote(partes.password or "") == "s@nha:1/2"
    assert (partes.hostname, partes.port, partes.path) == ("127.0.0.1", 5432, "/casa")


def test_nao_duplica_e_respeita_o_valor_existente() -> None:
    url = f"{BASE}?connect_timeout=30"
    assert com_connect_timeout(url) == url
    assert com_connect_timeout(com_connect_timeout(BASE)) == com_connect_timeout(BASE)


def test_preserva_outros_parametros() -> None:
    url = com_connect_timeout(f"{BASE}?sslmode=disable&application_name=casa")
    assert _parametros(url) == {
        "sslmode": ["disable"],
        "application_name": ["casa"],
        "connect_timeout": [str(CONNECT_TIMEOUT_S)],
    }


def test_settings_da_api_e_dos_scripts() -> None:
    """API, sync, relatório, roles e Alembic leem o banco por aqui."""
    cfg = Settings(database_url=BASE, insights_password="ro")
    assert _parametros(cfg.database_url)["connect_timeout"] == [str(CONNECT_TIMEOUT_S)]
    # A do insights deriva da principal e herda, uma vez só.
    assert _parametros(cfg.insights_database_url)["connect_timeout"] == [str(CONNECT_TIMEOUT_S)]


def test_settings_nao_duplica_quando_o_ambiente_ja_tem() -> None:
    cfg = Settings(database_url=f"{BASE}?connect_timeout=9")
    assert cfg.database_url.count("connect_timeout") == 1
    assert _parametros(cfg.database_url)["connect_timeout"] == ["9"]


def test_override_do_insights_tambem_leva() -> None:
    cfg = Settings(database_url=BASE, insights_database_url_override=BASE)
    assert "connect_timeout=" in cfg.insights_database_url


def test_url_do_host_do_make_relatorio() -> None:
    url = url_do_host({"POSTGRES_USER": "casa", "POSTGRES_PASSWORD": "x", "POSTGRES_DB": "casa"})
    assert _parametros(url)["connect_timeout"] == [str(CONNECT_TIMEOUT_S)]


def test_alembic_continua_lendo_a_url_inteira() -> None:
    from alembic.config import Config

    url = com_connect_timeout(BASE)
    config = Config()
    config.set_main_option("sqlalchemy.url", url_para_alembic(url))
    assert config.get_main_option("sqlalchemy.url") == url


@sem_shell
def test_modo_local_exporta_com_timeout(tmp_path: Path) -> None:
    """scripts/local/_config.sh: as URLs e o PGCONNECT_TIMEOUT de psql e pg_dump."""
    amb = montar_ambiente(tmp_path)
    r = amb.rodar(
        "-c",
        f'source "{CONFIG.as_posix()}" && casa_exportar_ambiente && '
        'echo "$DATABASE_URL" && echo "$TEST_DATABASE_URL" && echo "$PGCONNECT_TIMEOUT"',
    )
    assert r.returncode == 0, r.stderr
    url, url_teste, pg = r.stdout.split()
    for u in (url, url_teste):
        assert _parametros(u) == {"connect_timeout": ["5"]}
    assert pg == "5"


@pytest.mark.parametrize("segundos", [2, 5, 10])
def test_valor_configuravel(segundos: int) -> None:
    assert _parametros(com_connect_timeout(BASE, segundos))["connect_timeout"] == [str(segundos)]
