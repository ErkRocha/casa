"""Painel de produção servido por nginx (D-19): configuração e imagem.

Testes estruturais: leem o template, o snippet, o gerador de hosts e o
Dockerfile, sem nginx nem Docker. O comportamento de verdade (rota de SPA,
cache, gzip, /api, Host recusado, limite de upload) foi conferido com o nginx
para Windows na mesma versão; isto aqui impede a regressão silenciosa.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from app.routers.ingestao import TAMANHO_MAXIMO
from tests_sem_banco._falsos import BASH, sem_shell

WEB = Path(__file__).resolve().parents[2] / "web"
NGINX = WEB / "nginx"
TEMPLATE = NGINX / "default.conf.template"
SNIPPET = NGINX / "snippets" / "seguranca.conf"
HOSTS = NGINX / "hosts-permitidos.sh"
DOCKERFILE = WEB / "Dockerfile"

pytestmark = pytest.mark.skipif(
    not TEMPLATE.exists(), reason="o web fica fora do container da API; roda no host"
)


def _template() -> str:
    return TEMPLATE.read_text("utf-8")


def _location(nome: str) -> str:
    """O corpo de `location <nome> { ... }` (sem blocos aninhados)."""
    casou = re.search(rf"location {re.escape(nome)} \{{(.*?)\n    \}}", _template(), re.S)
    assert casou, f"location {nome} não achada"
    return casou.group(1)


# --- /api -------------------------------------------------------------------


def test_api_repassa_tirando_o_prefixo() -> None:
    corpo = _location("/api/")
    # A barra no fim do destino é o que tira o /api do caminho.
    assert re.search(r"proxy_pass \$\{API_UPSTREAM\}/;", corpo)
    assert "return 301 /api/;" in _location("= /api")


def test_api_tem_timeouts_explicitos() -> None:
    corpo = _location("/api/")
    for diretiva in ("proxy_connect_timeout", "proxy_send_timeout", "proxy_read_timeout"):
        assert re.search(rf"{diretiva} \d+s;", corpo), diretiva


def test_limite_de_corpo_cobre_o_upload_da_api() -> None:
    """Acima do limite da API, a mensagem dela tem que chegar, não um 413."""
    casou = re.search(r"client_max_body_size (\d+)m;", _location("/api/"))
    assert casou
    assert int(casou.group(1)) * 1024 * 1024 > TAMANHO_MAXIMO


# --- front ------------------------------------------------------------------


def test_spa_cai_no_index() -> None:
    assert "try_files $uri $uri/ /index.html;" in _location("/")


def test_cache_dos_assets_e_do_index() -> None:
    assert 'max-age=31536000, immutable"' in _location("/assets/")
    assert "try_files $uri =404;" in _location("/assets/")
    assert 'Cache-Control "no-cache"' in _location("= /index.html")


def test_gzip_para_texto_js_css_e_json() -> None:
    texto = _template()
    assert re.search(r"^\s*gzip on;", texto, re.M)
    tipos = re.search(r"gzip_types([^;]*);", texto)
    assert tipos
    for tipo in ("text/plain", "text/css", "application/javascript", "application/json"):
        assert tipo in tipos.group(1), tipo


def test_location_com_add_header_repete_os_de_seguranca() -> None:
    """No nginx, add_header na location descarta os herdados do server."""
    for nome in ("/assets/", "= /index.html"):
        assert "include snippets/seguranca.conf;" in _location(nome), nome


def test_cabecalhos_de_seguranca_sem_csp_que_quebre_o_recharts() -> None:
    snippet = SNIPPET.read_text("utf-8")
    assert 'X-Content-Type-Options "nosniff"' in snippet
    assert "Referrer-Policy" in snippet
    assert 'X-Frame-Options "DENY"' in snippet
    assert "frame-ancestors 'none'" in snippet
    assert "script-src" not in snippet and "style-src" not in snippet


# --- Host (DNS rebinding) -------------------------------------------------------


def test_host_desconhecido_recusado_antes_de_qualquer_location() -> None:
    texto = _template()
    recusa = texto.index("if ($host_permitido = 0)")
    assert recusa < texto.index("location "), "a recusa tem que valer também para /api"
    assert re.search(r"if \(\$host_permitido = 0\) \{\s*return 403;", texto)
    assert re.search(r"map \$host \$host_permitido \{\s*default 0;", texto)


def _gerar(tmp_path: Path, lista: str | None) -> str:
    assert BASH is not None
    destino = tmp_path / "hosts.map"
    env = {"HOSTS_MAP": destino.as_posix(), "PATH": os.environ["PATH"]}
    if lista is not None:
        env["WEB_ALLOWED_HOSTS"] = lista
    r = subprocess.run([BASH, HOSTS.as_posix()], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return destino.read_text("utf-8")


def _aceita(mapa: str, host: str) -> bool:
    """Avalia o map como o nginx: nome exato ou regex (~)."""
    for linha in mapa.splitlines():
        if linha.startswith("#") or not linha.strip():
            continue
        chave = linha.rsplit(" ", 1)[0].strip('"')
        if chave.startswith("~"):
            if re.search(chave[1:], host):
                return True
        elif chave == host:
            return True
    return False


@sem_shell
def test_padrao_aceita_localhost_e_tailscale(tmp_path: Path) -> None:
    mapa = _gerar(tmp_path, None)
    for host in ("localhost", "127.0.0.1", "[::1]", "pc-de-casa.tail1234.ts.net", "ts.net"):
        assert _aceita(mapa, host), host
    for host in ("exemplo.com", "evil-ts.net", "ts.net.evil.com", "tsxnet", "192.168.0.10"):
        assert not _aceita(mapa, host), host


@sem_shell
def test_lista_vazia_deixa_so_localhost(tmp_path: Path) -> None:
    mapa = _gerar(tmp_path, "")
    assert _aceita(mapa, "localhost")
    assert not _aceita(mapa, "pc.tail1234.ts.net")


@sem_shell
def test_entrada_com_sintaxe_do_nginx_e_ignorada(tmp_path: Path) -> None:
    mapa = _gerar(tmp_path, "pc.local, x{y;} 1;,Exemplo.COM")
    assert _aceita(mapa, "pc.local") and _aceita(mapa, "exemplo.com")
    assert "{" not in mapa and "x" not in [linha.split()[0] for linha in mapa.splitlines()]


# --- imagem ------------------------------------------------------------------


def _estagio_final() -> str:
    return DOCKERFILE.read_text("utf-8").split("\nFROM ")[-1]


def test_imagem_final_e_nginx_pinado_so_com_o_build() -> None:
    final = _estagio_final()
    assert re.match(r"nginx:\d+\.\d+\.\d+-alpine\n", final), "versão do nginx pinada"
    assert "COPY --from=build /app/dist /usr/share/nginx/html" in final
    assert "/etc/nginx/templates/default.conf.template" in final
    assert "/docker-entrypoint.d/" in final
    assert "node_modules" not in final and "npm" not in final


def test_build_usa_o_lockfile() -> None:
    texto = DOCKERFILE.read_text("utf-8")
    assert "COPY package.json package-lock.json ./" in texto
    assert "npm ci" in texto and "npm install" not in texto
    assert re.search(r"^FROM deps AS dev$", texto, re.M), "estágio de desenvolvimento"
    assert "node_modules" in (WEB / ".dockerignore").read_text("utf-8")
