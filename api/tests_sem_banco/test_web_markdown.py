"""O texto dos relatórios vem de um modelo: a tela trata como não confiável.

Guardas estruturais sobre os fontes do web. A renderização em si foi
conferida com o `MarkdownSeguro` recebendo script, HTML embutido, link
`javascript:`, imagem externa e iframe: nada disso sai como HTML.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[2] / "web"
SRC = WEB / "src"
MARKDOWN = SRC / "features" / "relatorios" / "components" / "markdown-seguro.tsx"
PAGINA = SRC / "features" / "relatorios" / "relatorios-page.tsx"

pytestmark = pytest.mark.skipif(
    not SRC.exists(), reason="o web fica fora do container; roda no host"
)


def _codigo(arquivo: Path) -> str:
    """O fonte sem comentários: um comentário pode citar o que é proibido."""
    texto = arquivo.read_text("utf-8")
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", texto)


def _fontes() -> list[Path]:
    fontes = [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx"}]
    assert len(fontes) > 10, "pasta de fontes vazia"
    return fontes


def test_nenhum_fonte_injeta_html() -> None:
    usam = [str(f.relative_to(WEB)) for f in _fontes() if "dangerouslySetInnerHTML" in _codigo(f)]
    assert not usam, f"dangerouslySetInnerHTML em: {usam}"


def test_sem_plugin_que_interpreta_html_bruto() -> None:
    pacote = json.loads((WEB / "package.json").read_text("utf-8"))
    dependencias = {**pacote.get("dependencies", {}), **pacote.get("devDependencies", {})}
    assert "react-markdown" in dependencias
    assert "rehype-raw" not in dependencias


def test_markdown_seguro_descarta_html_imagem_e_link() -> None:
    texto = _codigo(MARKDOWN)
    assert re.search(r"<Markdown\s[^>]*skipHtml", texto, re.S)
    proibidos = re.search(r"const PROIBIDOS = \[([^\]]*)\]", texto)
    assert proibidos
    for elemento in ("img", "a", "iframe", "script"):
        assert f'"{elemento}"' in proibidos.group(1), elemento
    assert "rehypeRaw" not in texto and "rehype-raw" not in texto


def test_conteudo_do_relatorio_so_passa_pelo_markdown_seguro() -> None:
    pagina = PAGINA.read_text("utf-8")
    assert "<MarkdownSeguro texto={relatorio.conteudo} />" in pagina
    usos = [m.start() for m in re.finditer(r"relatorio\.conteudo", pagina)]
    assert len(usos) == 1, "o conteúdo do modelo não pode ir para outro lugar da tela"


def test_tela_nao_gera_relatorio() -> None:
    """A geração continua pelo CLI no host: a tela só lê."""
    for arquivo in (SRC / "features" / "relatorios").rglob("*.ts*"):
        texto = arquivo.read_text("utf-8")
        assert "api.post" not in texto and "useMutation" not in texto, arquivo.name
    assert "make relatorio m=" in PAGINA.read_text("utf-8")
