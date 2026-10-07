"""A API atrás do nginx do painel, em /api (D-19).

O nginx repassa `/api/...` tirando o prefixo; a API não vê o `/api`. Com
`API_ROOT_PATH=/api`, o `/docs` aponta o `openapi.json` e o "Try it out"
para `/api/...`, e funciona em `/api/docs` pelo painel. Sem a variável, tudo
como antes, para o acesso direto em `127.0.0.1:8000`.

Em subprocesso: as configurações ficam em cache na primeira importação.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[1]

_SONDA = """
import json
from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)
docs = c.get("/docs")
openapi = c.get("/openapi.json")
print(json.dumps({
    "docs_status": docs.status_code,
    "docs_html": docs.text,
    "openapi_status": openapi.status_code,
    "servers": openapi.json().get("servers"),
}))
"""


def _sondar(root_path: str | None) -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k != "API_ROOT_PATH"}
    if root_path is not None:
        env["API_ROOT_PATH"] = root_path
    r = subprocess.run(
        [sys.executable, "-c", _SONDA],
        cwd=API,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    resultado: dict[str, object] = json.loads(r.stdout.strip().splitlines()[-1])
    return resultado


def test_atras_do_proxy_os_links_do_docs_levam_o_prefixo() -> None:
    r = _sondar("/api")
    assert r["docs_status"] == 200
    assert "'/api/openapi.json'" in str(r["docs_html"])
    # A API recebe o caminho já sem o prefixo, como o nginx entrega.
    assert r["openapi_status"] == 200
    assert r["servers"] == [{"url": "/api"}]


def test_sem_a_variavel_o_acesso_direto_fica_como_era() -> None:
    r = _sondar(None)
    assert r["docs_status"] == 200
    assert "'/openapi.json'" in str(r["docs_html"])
    assert "/api/" not in str(r["docs_html"])
    assert r["servers"] is None
