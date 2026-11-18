"""O leitor da consulta da SEFAZ-RS: escolhe o layout pelo conteúdo.

A consulta pela chave devolve a "Consulta Completa"; a URL do QR code pode
levar ao layout do portal SVRS. Os dois são lidos, cada um por seu leitor, e
a `NotaLida` carrega a `versao` do que leu.
"""

from __future__ import annotations

from compras.nfce.html import decodificar
from compras.nfce.leitor import FormatoDesconhecido, NotaLida
from compras.nfce.leitor_completa import LeitorConsultaCompleta
from compras.nfce.leitor_svrs import LeitorSvrsHtml

VERSAO = "sefaz-rs-1"


class LeitorSefazRs:
    versao = VERSAO

    def ler(self, conteudo: bytes, tipo: str | None) -> NotaLida:
        if tipo and "html" not in tipo.lower():
            raise FormatoDesconhecido(f"Este leitor lê HTML, não {tipo}.")
        texto = decodificar(conteudo)
        if 'id="tabResult"' in texto or "id='tabResult'" in texto:
            return LeitorSvrsHtml().ler(conteudo, tipo)
        if "NFCDetalhe_Item" in texto:
            return LeitorConsultaCompleta().ler(conteudo, tipo)
        raise FormatoDesconhecido(
            "A página não é a da nota: nem a Consulta Completa nem o layout do QR code."
        )
