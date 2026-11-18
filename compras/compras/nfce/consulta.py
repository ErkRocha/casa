"""A busca na consulta pública da SEFAZ-RS.

Atrás de um protocolo, para os testes trocarem por uma consulta falsa: nenhum
teste fala com a SEFAZ. A resposta é guardada inteira, como veio.

A consulta pela chave tem dois passos: abrir o formulário da "Consulta
Completa" (GET, que também dá os cookies) e enviá-lo (POST). Se a página
buscada traz esse formulário, ele é enviado; senão a página é devolvida como
veio (layout do QR code).

Só busca hosts de `HOSTS_PERMITIDOS`, inclusive depois de redirecionamento,
e para de ler acima de `TAMANHO_MAX`: a URL vem do usuário.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode, urljoin, urlsplit

import httpx

from compras.nfce.entrada import HOSTS_PERMITIDOS
from compras.nfce.html import decodificar

TAMANHO_MAX = 3 * 1024 * 1024
TEMPO_LIMITE_S = 20.0
#: A página do QR code às vezes só embrulha a nota num iframe do portal SVRS.
_IFRAME = re.compile(r"<iframe[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
#: O formulário da Consulta Completa: o `action` e a chave já preenchida.
_FORM = re.compile(r"<form[^>]+action=[\"']([^\"']*SAT-WEB-NFE-NFC_2\.asp)[\"']", re.IGNORECASE)
_CAMPO_CHAVE = re.compile(
    r"<input[^>]+name=[\"']chaveNFe[\"'][^>]+value=[\"'](\d{44})[\"']", re.IGNORECASE
)


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

    def __init__(
        self,
        tempo_limite_s: float = TEMPO_LIMITE_S,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        self.tempo_limite_s = tempo_limite_s
        #: Só para os testes (`httpx.MockTransport`): nenhum fala com a SEFAZ.
        self.transporte = transporte

    def buscar(self, url: str) -> Resposta:
        with httpx.Client(
            timeout=self.tempo_limite_s,
            follow_redirects=False,
            transport=self.transporte,
            headers={"User-Agent": "controle-casa-compras/0.1 (leitura da propria NFC-e)"},
        ) as cliente:
            resposta = self._pedir(cliente, "GET", url)
            # Um nível de iframe, só para o portal permitido.
            if _e_html(resposta):
                achado = _IFRAME.search(decodificar(resposta.conteudo))
                if achado:
                    interna = urljoin(resposta.url_final, achado.group(1))
                    if _permitido(interna):
                        resposta = self._pedir(cliente, "GET", interna)
            # O formulário da Consulta Completa é enviado; o resultado é a nota.
            if _e_html(resposta):
                texto = decodificar(resposta.conteudo)
                form, campo = _FORM.search(texto), _CAMPO_CHAVE.search(texto)
                if form and campo:
                    destino = urljoin(resposta.url_final, form.group(1))
                    resposta = self._pedir(
                        cliente,
                        "POST",
                        destino,
                        {"HML": "false", "chaveNFe": campo.group(1), "Action": "Avançar"},
                    )
            return resposta

    def _pedir(
        self,
        cliente: httpx.Client,
        metodo: str,
        url: str,
        dados: dict[str, str] | None = None,
    ) -> Resposta:
        for _ in range(5):
            if not _permitido(url):
                raise ConsultaFalhou(f"Endereço fora da SEFAZ-RS: {url}")
            try:
                corpo_enviado = (
                    urlencode(dados, encoding="latin-1").encode("ascii") if dados else None
                )
                with cliente.stream(
                    metodo,
                    url,
                    content=corpo_enviado,
                    headers=(
                        {"Content-Type": "application/x-www-form-urlencoded"}
                        if corpo_enviado is not None
                        else None
                    ),
                ) as r:
                    if r.is_redirect:
                        url = urljoin(url, r.headers.get("location", ""))
                        # Depois do redirecionamento de um POST, segue com GET.
                        metodo, dados = "GET", None
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


def _e_html(resposta: Resposta) -> bool:
    return bool(resposta.tipo and "html" in resposta.tipo)
