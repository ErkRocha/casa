"""O que o usuário cola ou o celular lê: a URL do QR code ou a chave.

A URL vem de fora, então só é aceita a de um endereço conhecido da SEFAZ-RS
(nada de o serviço buscar um endereço qualquer). Sem URL, a de consulta é
montada pela chave.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

from compras.nfce.chave import MODELO_NFCE, Chave, ChaveInvalida, validar

#: Hosts da consulta pública da NFC-e do RS. O QR code impresso aponta para
#: o primeiro; o portal SVRS é quem de fato mostra a nota.
HOSTS_PERMITIDOS = frozenset(
    {"www.sefaz.rs.gov.br", "sefaz.rs.gov.br", "dfe-portal.svrs.rs.gov.br"}
)

#: A consulta montada só com a chave, quando não há URL. É o parâmetro `p`
#: do QR code versão 2 sem o resto; **pendente de validação com uma nota
#: real** (roadmap, "Nota fiscal e preços").
URL_CONSULTA_POR_CHAVE = "https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?p={chave}"

#: UFs cuja consulta pública este serviço sabe buscar.
UFS_SUPORTADAS = frozenset({"RS"})


class EntradaInvalida(ValueError):
    """O texto não é URL de NFC-e nem chave válida, ou não é uma NFC-e do RS."""


@dataclass(frozen=True, slots=True)
class Entrada:
    chave: Chave
    url_consulta: str
    #: Veio a URL do QR code (True) ou só a chave (False)?
    do_qr_code: bool


def _chave_da_url(url: str) -> str:
    partes = urlsplit(url)
    parametros = parse_qs(partes.query)
    # QR code v2: p=CHAVE|versao|ambiente|...; v1: chNFe=CHAVE.
    for nome in ("p", "chNFe", "chave"):
        for valor in parametros.get(nome, []):
            candidata = unquote(valor).split("|")[0]
            if re.fullmatch(r"\d{44}", candidata):
                return candidata
    achadas = re.findall(r"(?<!\d)\d{44}(?!\d)", unquote(url))
    if len(achadas) == 1:
        return str(achadas[0])
    raise EntradaInvalida("Não achei a chave de acesso na URL.")


def interpretar(texto: str) -> Entrada:
    """URL do QR code ou chave de 44 dígitos (com ou sem espaços)."""
    bruto = texto.strip()
    if not bruto:
        raise EntradaInvalida("Cole a URL do QR code ou a chave de acesso.")
    do_qr = bool(re.match(r"https?://", bruto, re.IGNORECASE))
    try:
        if do_qr:
            host = (urlsplit(bruto).hostname or "").lower()
            if host not in HOSTS_PERMITIDOS:
                raise EntradaInvalida(
                    f"A URL é de {host or 'endereço nenhum'}, não da consulta da SEFAZ-RS."
                )
            chave = validar(_chave_da_url(bruto))
        else:
            chave = validar(bruto)
    except ChaveInvalida as exc:
        raise EntradaInvalida(str(exc)) from exc
    if chave.modelo != MODELO_NFCE:
        raise EntradaInvalida(
            f"A chave é de modelo {chave.modelo}; só a NFC-e (modelo 65), o cupom do "
            "mercado, é lida aqui."
        )
    if chave.uf not in UFS_SUPORTADAS:
        raise EntradaInvalida(f"Nota de {chave.uf}: por enquanto só a consulta do RS é lida.")
    url = (
        urlsplit(bruto)._replace(scheme="https").geturl()
        if do_qr
        else URL_CONSULTA_POR_CHAVE.format(chave=chave.numero)
    )
    return Entrada(chave=chave, url_consulta=url, do_qr_code=do_qr)
