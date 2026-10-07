"""URL do banco no host para o `make relatorio` (D-17)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from scripts._host import preparar_ambiente_host, url_do_host

BASE = {"POSTGRES_USER": "casa", "POSTGRES_PASSWORD": "segredo", "POSTGRES_DB": "casa"}


def test_monta_pela_porta_publicada() -> None:
    url = url_do_host(BASE | {"POSTGRES_PORT": "5433"})
    assert url == "postgresql+psycopg://casa:segredo@127.0.0.1:5433/casa?connect_timeout=5"


def test_porta_padrao_do_compose() -> None:
    assert "@127.0.0.1:5432/" in url_do_host(BASE)


@pytest.mark.parametrize("senha", ["p@ss", "a:b", "c/d", "x@y:z/w%"])
def test_senha_com_caracteres_especiais(senha: str) -> None:
    partes = urlsplit(url_do_host(BASE | {"POSTGRES_PASSWORD": senha}))
    # A URL continua parseável e a senha volta inteira.
    assert partes.hostname == "127.0.0.1"
    assert partes.port == 5432
    assert unquote(partes.password or "") == senha
    assert partes.path == "/casa"


def test_falta_variavel_e_erro_claro() -> None:
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        url_do_host({"POSTGRES_USER": "casa", "POSTGRES_DB": "casa"})


def _env(tmp_path: Path, conteudo: str) -> Path:
    arquivo = tmp_path / ".env"
    arquivo.write_text(conteudo, encoding="utf-8")
    return arquivo


def test_sem_database_url_monta_do_env(tmp_path: Path) -> None:
    arquivo = _env(
        tmp_path,
        "POSTGRES_USER=casa\nPOSTGRES_PASSWORD=s@nha:1/2\nPOSTGRES_DB=casa\n"
        "POSTGRES_PORT=5432\nINSIGHTS_PASSWORD=ro\n",
    )
    ambiente: dict[str, str] = {}
    url = preparar_ambiente_host(arquivo, ambiente)
    assert url is not None and ambiente["DATABASE_URL"] == url
    assert unquote(urlsplit(url).password or "") == "s@nha:1/2"
    # O resto do .env chega junto: a senha da role read-only, por exemplo.
    assert ambiente["INSIGHTS_PASSWORD"] == "ro"


def test_database_url_ja_definida_manda(tmp_path: Path) -> None:
    """Modo local (`source scripts/local/ambiente.sh`) e container."""
    arquivo = _env(tmp_path, "POSTGRES_USER=casa\nPOSTGRES_PASSWORD=x\nPOSTGRES_DB=casa\n")
    ambiente = {"DATABASE_URL": "postgresql+psycopg://casa:local@127.0.0.1:55432/casa"}
    assert preparar_ambiente_host(arquivo, ambiente) is None
    assert ambiente["DATABASE_URL"].endswith(":55432/casa")


def test_ambiente_vence_o_arquivo(tmp_path: Path) -> None:
    arquivo = _env(
        tmp_path,
        "POSTGRES_USER=casa\nPOSTGRES_PASSWORD=do_arquivo\nPOSTGRES_DB=casa\n",
    )
    ambiente = {"POSTGRES_PASSWORD": "do_ambiente"}
    url = preparar_ambiente_host(arquivo, ambiente)
    assert url is not None and ":do_ambiente@" in url


def test_sem_env_e_sem_url_sai_com_mensagem(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match=r"ambiente.sh"):
        preparar_ambiente_host(tmp_path / "nao_existe.env", {})
