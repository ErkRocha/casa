"""Depois da sync, finanças pede ao `compras` que consolide as ligações (D-33).

Nenhum teste fala com a rede: o POST é trocado por um falso.
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.services import compras_notas
from app.services.compras_notas import consolidar_ligacoes_das_notas
from app.services.execucao_sync import executar
from tests.test_sync_pluggy import LeitorFalso


def _cfg(url: str | None) -> Settings:
    return Settings(
        pluggy_client_id="id", pluggy_client_secret=SecretStr("segredo"), compras_api_url=url
    )


class PostFalso:
    def __init__(self, status: int = 200, erro: Exception | None = None) -> None:
        self.chamadas: list[tuple[str, dict[str, Any]]] = []
        self.status = status
        self.erro = erro

    def __call__(self, url: str, **kwargs: Any) -> httpx.Response:
        self.chamadas.append((url, kwargs))
        if self.erro is not None:
            raise self.erro
        return httpx.Response(self.status, text='{"ok": true}', request=httpx.Request("POST", url))


def test_sem_url_nao_chama_nada() -> None:
    post = PostFalso()
    assert consolidar_ligacoes_das_notas(_cfg(None), post) is False
    assert post.chamadas == []


def test_chama_o_compras_com_tempo_curto() -> None:
    post = PostFalso()
    assert consolidar_ligacoes_das_notas(_cfg("http://compras:8000/"), post) is True
    url, kwargs = post.chamadas[0]
    assert url == "http://compras:8000/notas/consolidar-ligacoes"
    assert kwargs["timeout"] <= 10


@pytest.mark.parametrize(
    "post", [PostFalso(erro=httpx.ConnectError("fora")), PostFalso(status=500)]
)
def test_falha_vira_log_e_nao_levanta(post: PostFalso) -> None:
    assert consolidar_ligacoes_das_notas(_cfg("http://compras:8000"), post) is False


def test_sync_chama_depois_do_commit_e_nao_falha_se_o_compras_cai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = PostFalso(erro=httpx.ConnectError("fora"))
    monkeypatch.setattr(compras_notas.httpx, "post", post)

    r = executar(
        _cfg("http://compras:8000"), fabrica_de_leitor=lambda c, f: nullcontext(LeitorFalso())
    )
    assert r.itens_novos == 0
    assert len(post.chamadas) == 1


def test_simulacao_nao_chama(monkeypatch: pytest.MonkeyPatch) -> None:
    post = PostFalso()
    monkeypatch.setattr(compras_notas.httpx, "post", post)
    executar(
        _cfg("http://compras:8000"),
        simular=True,
        fabrica_de_leitor=lambda c, f: nullcontext(LeitorFalso()),
    )
    assert post.chamadas == []
