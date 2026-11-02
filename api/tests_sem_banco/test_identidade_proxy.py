"""Identidade pelo Tailscale no proxy do painel (roadmap, Lista de compras, 3).

Estruturais: leem o template do nginx e o `vite.config.ts`. O comportamento
foi conferido em 02/11/2026 com a imagem real do web (nginx 1.30.5) e um eco
no lugar do compras: com `Tailscale-User-Login`, o `X-Quem` forjado chega
trocado pelo login; sem ele, chega o do aparelho; o `/api/` não muda.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
TEMPLATE = WEB / "nginx" / "default.conf.template"
VITE = WEB / "vite.config.ts"

pytestmark = pytest.mark.skipif(
    not TEMPLATE.exists(), reason="o web fica fora do container da API; roda no host"
)


def _template() -> str:
    return TEMPLATE.read_text("utf-8")


def _location(nome: str) -> str:
    casou = re.search(rf"location {re.escape(nome)} \{{(.*?)\n    \}}", _template(), re.S)
    assert casou, f"location {nome} não achada"
    return casou.group(1)


def test_map_da_identidade_prefere_o_tailscale() -> None:
    casou = re.search(
        r"map \$http_tailscale_user_login \$quem_compras \{(.*?)\}", _template(), re.S
    )
    assert casou, "map $quem_compras não achado"
    corpo = casou.group(1)
    # Sem login do Tailscale, o X-Quem do aparelho; com ele, o login.
    assert re.search(r'""\s+\$http_x_quem;', corpo)
    assert re.search(r"default\s+\$http_tailscale_user_login;", corpo)
    # No contexto http, antes do server (map não vale dentro de server).
    assert _template().index("map $http_tailscale_user_login") < _template().index("server {")


def test_compras_recebe_x_quem_do_map_e_os_cabecalhos_do_tailscale() -> None:
    corpo = _location("/api/compras/")
    assert "proxy_set_header X-Quem $quem_compras;" in corpo
    assert "proxy_set_header Tailscale-User-Login $http_tailscale_user_login;" in corpo
    assert "proxy_set_header Tailscale-User-Name $http_tailscale_user_name;" in corpo
    # Nenhum outro X-Quem que deixe passar o do cliente.
    assert len(re.findall(r"proxy_set_header X-Quem ", corpo)) == 1


def test_api_de_financas_nao_mexe_no_x_quem() -> None:
    assert "X-Quem" not in _location("/api/")


def test_vite_faz_o_mesmo_no_modo_local() -> None:
    texto = VITE.read_text("utf-8")
    funcao = re.search(r"export function quemParaCompras\(.*?\n\}", texto, re.S)
    assert funcao, "quemParaCompras não achada"
    assert '"tailscale-user-login"' in funcao.group(0)
    # A regra do /api/compras usa a função e sobrescreve o X-Quem.
    regra = re.search(r'"\^/api/compras\(/\|\$\)": \{(.*?)\n      \},', texto, re.S)
    assert regra, "regra do proxy de compras não achada"
    assert 'proxy.on("proxyReq"' in regra.group(1)
    assert 'pedido.setHeader("X-Quem", login)' in regra.group(1)
    # O /api de finanças não ganha a regra.
    financas = re.search(r'"/api": \{(.*?)\n      \},', texto, re.S)
    assert financas and "X-Quem" not in financas.group(1)
