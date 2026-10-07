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
