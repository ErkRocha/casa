"""A consulta pela chave: GET do formulário e POST, sem rede (MockTransport)."""

from __future__ import annotations

import httpx
import pytest

from compras.nfce.consulta import ConsultaFalhou, ConsultaSefazRs
from tests.nfce_apoio import chave

BASE = "https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE"
CHAVE = chave()
FORMULARIO = (
    "<html><body>"
    '<form method="POST" name="form1" action=\'SAT-WEB-NFE-NFC_2.asp\'>'
    '<input type="radio" name="HML" value="false" checked />'
    f'<input id="chaveNFe" name="chaveNFe" value="{CHAVE}" />'
    '<input type="submit" name="Action" value="Avançar" />'
    "</form></body></html>"
).encode("latin-1")
COMPLETA = (
    '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
    "</head><body>Consulta Completa da NFC-e: Cartão</body></html>"
).encode("latin-1")
HTML = {"content-type": "text/html"}


def _consulta() -> tuple[ConsultaSefazRs, list[httpx.Request]]:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        url = str(pedido.url)
        if url.startswith(f"{BASE}/SAT-WEB-NFE-NFC_1.asp"):
            return httpx.Response(
                200,
                content=FORMULARIO,
                headers={**HTML, "set-cookie": "ASPSESSION=abc; path=/"},
            )
        if url == f"{BASE}/SAT-WEB-NFE-NFC_2.asp" and pedido.method == "POST":
            return httpx.Response(200, content=COMPLETA, headers=HTML)
        if url.startswith("https://www.sefaz.rs.gov.br/NFE/NFE-NFC.aspx"):
            iframe = (
                f'<iframe id="iframeConteudo" src="{BASE}/SAT-WEB-NFE-NFC_1.asp?chaveNFe={CHAVE}">'
            )
            return httpx.Response(200, content=iframe.encode(), headers=HTML)
        return httpx.Response(404)

    return ConsultaSefazRs(transporte=httpx.MockTransport(responder)), pedidos


def test_chave_pura_abre_o_formulario_e_o_envia() -> None:
    consulta, pedidos = _consulta()
    resposta = consulta.buscar(f"{BASE}/SAT-WEB-NFE-NFC_1.asp?chaveNFe={CHAVE}")
    assert [p.method for p in pedidos] == ["GET", "POST"]
    post = pedidos[1]
    corpo = post.content.decode("ascii")
    assert f"chaveNFe={CHAVE}" in corpo
    assert "HML=false" in corpo
    assert "Action=Avan%E7ar" in corpo
    assert "ASPSESSION=abc" in post.headers["cookie"]
    assert post.headers["content-type"] == "application/x-www-form-urlencoded"
    assert resposta.url_final == f"{BASE}/SAT-WEB-NFE-NFC_2.asp"
    assert resposta.conteudo == COMPLETA


def test_pagina_publica_com_iframe_chega_ao_formulario_e_o_envia() -> None:
    consulta, pedidos = _consulta()
    resposta = consulta.buscar(f"https://www.sefaz.rs.gov.br/NFE/NFE-NFC.aspx?chaveNFe={CHAVE}")
    assert [p.method for p in pedidos] == ["GET", "GET", "POST"]
    assert resposta.url_final == f"{BASE}/SAT-WEB-NFE-NFC_2.asp"
    assert resposta.conteudo == COMPLETA


def test_iframe_fora_dos_hosts_permitidos_nao_e_buscado() -> None:
    pedidos: list[httpx.Request] = []

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        corpo = b'<iframe src="https://exemplo.com/x"></iframe>'
        return httpx.Response(200, content=corpo, headers=HTML)

    consulta = ConsultaSefazRs(transporte=httpx.MockTransport(responder))
    resposta = consulta.buscar("https://www.sefaz.rs.gov.br/NFE/NFE-NFC.aspx?chaveNFe=1")
    assert len(pedidos) == 1
    assert resposta.url_final.startswith("https://www.sefaz.rs.gov.br/")


def test_formulario_apontando_para_fora_falha_sem_pedir() -> None:
    pedidos: list[httpx.Request] = []
    pagina = (
        '<form method="POST" action="https://exemplo.com/SAT-WEB-NFE-NFC_2.asp">'
        f'<input name="chaveNFe" value="{CHAVE}"></form>'
    ).encode()

    def responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        return httpx.Response(200, content=pagina, headers=HTML)

    consulta = ConsultaSefazRs(transporte=httpx.MockTransport(responder))
    with pytest.raises(ConsultaFalhou, match="fora da SEFAZ-RS"):
        consulta.buscar(f"{BASE}/SAT-WEB-NFE-NFC_1.asp?chaveNFe={CHAVE}")
    assert [p.url.host for p in pedidos] == ["www.sefaz.rs.gov.br"]


def test_pagina_sem_formulario_volta_como_veio() -> None:
    pagina = b'<html><table id="tabResult"></table></html>'

    def responder(pedido: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=pagina, headers=HTML)

    consulta = ConsultaSefazRs(transporte=httpx.MockTransport(responder))
    url = f"https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?p={CHAVE}|2|1|1|AB"
    resposta = consulta.buscar(url)
    assert resposta.conteudo == pagina
    assert resposta.url_final == url
