"""Depois da sync, finanças avisa o `compras` para consolidar as ligações (D-33).

A nota ligada a uma compra pendente vira ligação com a transação quando a
Pluggy a confirma; a nota ligada a uma despesa lançada pela nota que a revisão
juntou com a do banco passa para a do banco. Quem decide e grava é o
`compras`: aqui só se bate na porta dele, por HTTP (D-25).

Nunca derruba a sync: sem URL configurada não faz nada, e qualquer falha vira
uma linha de log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

#: Segundos até desistir: a sync já terminou, ninguém espera por isto.
TEMPO_LIMITE_S = 5.0

CAMINHO = "/notas/consolidar-ligacoes"

Poster = Callable[..., httpx.Response]


def consolidar_ligacoes_das_notas(cfg: Settings, post: Poster | None = None) -> bool:
    """Pede ao `compras` que consolide as ligações. `True` se ele respondeu 2xx."""
    if not cfg.compras_api_url:
        return False
    enviar: Poster = post or httpx.post
    url = f"{cfg.compras_api_url.rstrip('/')}{CAMINHO}"
    try:
        resposta = enviar(url, timeout=TEMPO_LIMITE_S)
        resposta.raise_for_status()
    except Exception as exc:  # a sync não pode falhar por causa disto
        log.warning(
            "compras: não consegui consolidar as ligações das notas (%s: %s)",
            type(exc).__name__,
            exc,
        )
        return False
    log.info("compras: ligações das notas consolidadas: %s", resposta.text[:200])
    return True
