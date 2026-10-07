"""O front chama a API por caminho relativo, na mesma origem (D-18).

URL absoluta fixa para a API no código do web quebra o acesso pelo Tailscale:
o navegador do celular tentaria `127.0.0.1`, que é ele mesmo. Este teste lê
os fontes do web e falha se aparecer alguma.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
SRC = WEB / "src"
CLIENTE = SRC / "lib" / "api.ts"

pytestmark = pytest.mark.skipif(
    not SRC.exists(), reason="o web fica fora do container da API; roda no host"
)

#: Qualquer URL com esquema: o front não tem motivo para falar com outra
#: origem — nem a API, nem serviço de fora (o sistema não vai à internet).
URL_ABSOLUTA = re.compile(r"""["'`]\s*(?:https?:)?//""")


def _fontes() -> list[Path]:
    fontes = sorted(p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"})
    # Pasta vazia faria os testes passarem sem olhar nada.
    assert len(fontes) > 10, f"poucos fontes em {SRC}: {len(fontes)}"
    return fontes


def test_nenhum_fonte_tem_url_absoluta() -> None:
    achados = []
    for fonte in _fontes():
        for numero, linha in enumerate(fonte.read_text("utf-8").splitlines(), start=1):
            if linha.strip().startswith(("//", "*", "/*")):
                continue  # comentário pode citar URL
            if URL_ABSOLUTA.search(linha):
                achados.append(f"{fonte.relative_to(WEB)}:{numero}: {linha.strip()}")
    assert not achados, "URL absoluta no front:\n" + "\n".join(achados)


def test_override_da_api_so_no_cliente() -> None:
    """`VITE_API_URL` é lido num lugar só; o resto usa `urlDaApi` ou o cliente."""
    fora = [
        str(f.relative_to(WEB))
        for f in _fontes()
        if f != CLIENTE and "VITE_API_URL" in f.read_text("utf-8")
    ]
    assert not fora, f"VITE_API_URL lido fora de lib/api.ts: {fora}"


def test_base_padrao_e_api_relativa() -> None:
    texto = CLIENTE.read_text("utf-8")
    assert re.search(r'\|\|\s*"/api"\s*\)', texto), "a base padrão da API tem que ser /api"


def test_vite_repassa_api_sem_o_prefixo() -> None:
    config = (WEB / "vite.config.ts").read_text("utf-8")
    assert '"/api"' in config and "API_PROXY_TARGET" in config
    assert re.search(r"replace\(/\^\\/api/", config), "o proxy tem que tirar o prefixo /api"
    assert "WEB_ALLOWED_HOSTS" in config and '".ts.net"' in config
    assert "allowedHosts: true" not in config
