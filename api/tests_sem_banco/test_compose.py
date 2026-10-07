"""O docker-compose.yml: senha da role read-only (D-11) e reinício (D-17)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

COMPOSE = Path(__file__).resolve().parents[2] / "docker-compose.yml"


def _bloco_do_servico(texto: str, servico: str) -> str:
    """As linhas do serviço, até o próximo serviço de mesmo nível."""
    casou = re.search(rf"^  {servico}:\n(.*?)(?=^  \S|^\S|\Z)", texto, re.M | re.S)
    assert casou, f"serviço {servico} não achado no compose"
    return casou.group(1)


@pytest.mark.skipif(
    not COMPOSE.exists(), reason="docker-compose.yml fica fora do container; roda no host"
)
def test_api_recebe_insights_password() -> None:
    """Sem isto, `make roles` gravava na role a senha de exemplo do código, e
    `make dossie` só conectava porque usava a mesma senha errada."""
    api = _bloco_do_servico(COMPOSE.read_text("utf-8"), "api")
    assert re.search(r"^\s+INSIGHTS_PASSWORD: \$\{INSIGHTS_PASSWORD", api, re.M)


@pytest.mark.skipif(
    not COMPOSE.exists(), reason="docker-compose.yml fica fora do container; roda no host"
)
@pytest.mark.parametrize("servico", ["db", "api", "web"])
def test_servicos_reiniciam_sozinhos(servico: str) -> None:
    """D-17: o sistema roda continuamente no PC de casa."""
    bloco = _bloco_do_servico(COMPOSE.read_text("utf-8"), servico)
    assert re.search(r"^\s+restart: unless-stopped$", bloco, re.M)


DEV = COMPOSE.with_name("docker-compose.dev.yml")


@pytest.mark.skipif(not COMPOSE.exists(), reason="roda no host")
def test_web_e_o_nginx_sem_codigo_montado() -> None:
    """D-19: produção é a imagem pronta; nada de volume nem de `npm run dev`."""
    web = _bloco_do_servico(COMPOSE.read_text("utf-8"), "web")
    assert "volumes:" not in web and "command:" not in web
    assert '"127.0.0.1:${WEB_PORT:-5173}:5173"' in web
    assert "API_UPSTREAM: http://api:8000" in web
    assert "WEB_ALLOWED_HOSTS: ${WEB_ALLOWED_HOSTS:-.ts.net}" in web


@pytest.mark.skipif(not COMPOSE.exists(), reason="roda no host")
def test_api_atras_do_proxy_em_api() -> None:
    api = _bloco_do_servico(COMPOSE.read_text("utf-8"), "api")
    assert re.search(r"^\s+API_ROOT_PATH: /api$", api, re.M)


@pytest.mark.skipif(not DEV.exists(), reason="roda no host")
def test_override_de_dev_volta_o_vite_com_recarga() -> None:
    web = _bloco_do_servico(DEV.read_text("utf-8"), "web")
    assert "target: dev" in web
    assert "./web:/app" in web and "web_node_modules:/app/node_modules" in web
    assert "command: npm run dev" in web
    assert "API_PROXY_TARGET: http://api:8000" in web
