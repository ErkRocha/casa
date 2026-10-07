"""URL do banco no Alembic com senha codificada."""

from __future__ import annotations

from urllib.parse import quote

from alembic.config import Config

from app.config import url_para_alembic


def test_senha_com_caracteres_especiais_chega_inteira_ao_alembic() -> None:
    """`%40` na URL fazia o `configparser` do Alembic levantar ValueError."""
    url = f"postgresql+psycopg://casa:{quote('s@nha:com/%', safe='')}@127.0.0.1:55432/casa"
    config = Config()
    config.set_main_option("sqlalchemy.url", url_para_alembic(url))
    assert config.get_main_option("sqlalchemy.url") == url


def test_url_sem_porcentagem_nao_muda() -> None:
    url = "postgresql+psycopg://casa:simples@db:5432/casa"
    assert url_para_alembic(url) == url
