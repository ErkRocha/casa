"""A busca na consulta pública da SEFAZ-RS.

Atrás de um protocolo, para os testes trocarem por uma consulta falsa: nenhum
teste fala com a SEFAZ. A resposta é guardada inteira, como veio.

Só busca hosts de `HOSTS_PERMITIDOS`, inclusive depois de redirecionamento,
e para de ler acima de `TAMANHO_MAX`: a URL vem do usuário.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit

import httpx

from compras.nfce.entrada import HOSTS_PERMITIDOS

TAMANHO_MAX = 3 * 1024 * 1024
TEMPO_LIMITE_S = 20.0
#: A página do QR code às vezes só embrulha a nota num iframe do portal SVRS.
_IFRAME = re.compile(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)


class ConsultaFalhou(RuntimeError):
    """A SEFAZ não respondeu, respondeu erro ou respondeu algo grande demais."""


@dataclass(frozen=True, slots=True)
class Resposta:
    conteudo: bytes
    tipo: str | None
    url_final: str


class ConsultaPublica(Protocol):
    def buscar(self, url: str) -> Resposta: ...


def _permitido(url: str) -> bool:
    partes = urlsplit(url)
    return partes.scheme == "https" and (partes.hostname or "").lower() in HOSTS_PERMITIDOS


class ConsultaSefazRs:
    """A consulta de verdade, por HTTPS."""

    def __init__(self, tempo_limite_s: float = TEMPO_LIMITE_S) -> None:
        self.tempo_limite_s = tempo_limite_s

    def buscar(self, url: str) -> Resposta:
        with httpx.Client(
            timeout=self.tempo_limite_s,
            follow_redirects=False,
            headers={"User-Agent": "controle-casa-compras/0.1 (leitura da propria NFC-e)"},
        ) as cliente:
            resposta = self._get(cliente, url)
            # Um nível de iframe, só para o portal permitido.
            if resposta.tipo and "html" in resposta.tipo:
                achado = _IFRAME.search(resposta.conteudo.decode("utf-8", errors="replace"))
                if achado:
                    interna = urljoin(resposta.url_final, achado.group(1))
                    if _permitido(interna):
                        resposta = self._get(cliente, interna)
            return resposta

    def _get(self, cliente: httpx.Client, url: str) -> Resposta:
        for _ in range(5):
            if not _permitido(url):
                raise ConsultaFalhou(f"Endereço fora da SEFAZ-RS: {url}")
            try:
                with cliente.stream("GET", url) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("location", ""))
                        continue
                    if r.status_code != 200:
                        raise ConsultaFalhou(f"A SEFAZ respondeu {r.status_code}.")
                    corpo = bytearray()
                    for pedaco in r.iter_bytes():
                        corpo.extend(pedaco)
                        if len(corpo) > TAMANHO_MAX:
                            raise ConsultaFalhou("A resposta da SEFAZ passou do tamanho esperado.")
                    tipo = r.headers.get("content-type")
                    return Resposta(bytes(corpo), tipo.split(";")[0].strip() if tipo else None, url)
            except httpx.HTTPError as exc:
                raise ConsultaFalhou(f"A SEFAZ não respondeu: {type(exc).__name__}.") from exc
        raise ConsultaFalhou("Redirecionamentos demais na consulta.")
