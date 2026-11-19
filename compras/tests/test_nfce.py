"""Chave de acesso, entrada (URL ou chave) e os leitores da página da nota.

Nada aqui fala com a SEFAZ. O teste da amostra lê a Consulta Completa de
uma nota real, anonimizada (tests/amostras).
"""

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from compras.nfce.chave import ChaveInvalida, digito_verificador, validar
from compras.nfce.entrada import EntradaInvalida, interpretar, urls_de_consulta
from compras.nfce.leitor import FormatoDesconhecido
from compras.nfce.leitor_rs import LeitorSefazRs
from compras.nfce.leitor_svrs import FUSO, VERSAO, LeitorSvrsHtml
from tests.nfce_apoio import CNPJ_A, Item, chave, pagina, url_qr

AMOSTRA_REAL = Path(__file__).parent / "amostras" / "nfce_rs_anonimizada.html"

# --- chave ----------------------------------------------------------------------


def test_digito_verificador_modulo_11() -> None:
    # Conta à mão: 43 dígitos "1"; pesos 2..9 repetidos da direita somam
    # 5 ciclos completos (5 x 44 = 220) e mais 2+3+4 = 9 -> 229; 229 % 11 = 9;
    # 11 - 9 = 2.
    assert digito_verificador("1" * 43) == "2"
    # Resto 0 ou 1 vira 0: 43 zeros somam 0.
    assert digito_verificador("0" * 43) == "0"


def test_chave_valida_extrai_uf_cnpj_e_modelo() -> None:
    c = validar(chave(numero=42))
    assert c.uf == "RS"
    assert c.cnpj == CNPJ_A
    assert c.modelo == "65"
    assert c.ano_mes == "2611"
    assert c.numero_nota == "000000042"
    assert c.cnpj_formatado == "11.222.333/0001-81"


def test_chave_aceita_espacos_e_pontuacao() -> None:
    numero = chave()
    em_blocos = " ".join(numero[i : i + 4] for i in range(0, 44, 4))
    assert validar(em_blocos).numero == numero


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("123", "44 dígitos"),
        ("a" * 44, "44 dígitos"),
        (chave()[:43] + str((int(chave()[43]) + 1) % 10), "dígito verificador"),
    ],
)
def test_chave_invalida(texto: str, motivo: str) -> None:
    with pytest.raises(ChaveInvalida, match=motivo):
        validar(texto)


def test_chave_com_uf_inexistente() -> None:
    with pytest.raises(ChaveInvalida, match="código de UF"):
        validar(chave(uf="99"))


# --- entrada ----------------------------------------------------------------------


def test_entrada_pela_url_do_qr_code_v2() -> None:
    numero = chave()
    e = interpretar(url_qr(numero))
    assert e.chave.numero == numero
    assert e.do_qr_code
    assert e.url_consulta.startswith("https://www.sefaz.rs.gov.br/")


def test_entrada_pela_url_v1_e_por_http() -> None:
    numero = chave()
    e = interpretar(f"http://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?chNFe={numero}&nVersao=100")
    assert e.chave.numero == numero
    # Sempre por HTTPS.
    assert e.url_consulta.startswith("https://")


def test_entrada_pela_chave_monta_a_url() -> None:
    numero = chave()
    e = interpretar(f"  {numero}  ")
    assert not e.do_qr_code
    assert e.url_consulta == (
        f"https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE/SAT-WEB-NFE-NFC_1.asp?chaveNFe={numero}"
    )


def test_entrada_expoe_a_url_por_chave_nos_dois_casos() -> None:
    numero = chave()
    por_chave = interpretar(numero)
    do_qr = interpretar(url_qr(numero))
    esperada = (
        f"https://www.sefaz.rs.gov.br/ASP/AAE_ROOT/NFE/SAT-WEB-NFE-NFC_1.asp?chaveNFe={numero}"
    )
    assert por_chave.url_por_chave == esperada
    assert por_chave.url_consulta == por_chave.url_por_chave
    assert do_qr.url_por_chave == esperada
    assert do_qr.url_consulta != do_qr.url_por_chave


def test_urls_de_consulta_qr_primeiro_chave_de_reserva_sem_repetir() -> None:
    numero = chave()
    qr = interpretar(url_qr(numero))
    assert urls_de_consulta(qr.url_consulta, numero) == [qr.url_consulta, qr.url_por_chave]
    assert urls_de_consulta(qr.url_por_chave, numero) == [qr.url_por_chave]


def test_entrada_pela_url_publica_com_a_chave() -> None:
    numero = chave()
    url = f"https://www.sefaz.rs.gov.br/NFE/NFE-NFC.aspx?chaveNFe={numero}"
    e = interpretar(url)
    assert e.do_qr_code
    assert e.chave.numero == numero
    assert e.url_consulta == url


@pytest.mark.parametrize(
    ("texto", "motivo"),
    [
        ("", "Cole"),
        ("https://exemplo.com/NFCE?p=" + chave(), "não da consulta da SEFAZ-RS"),
        ("https://www.sefaz.rs.gov.br.exemplo.com/?p=" + chave(), "não da consulta"),
        ("https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?p=123", "Não achei a chave"),
        (chave(modelo="55"), "modelo 55"),
        (chave(uf="35"), "SP"),
        (chave()[:43] + "x", "44 dígitos"),
    ],
)
def test_entrada_recusada(texto: str, motivo: str) -> None:
    with pytest.raises(EntradaInvalida, match=motivo):
        interpretar(texto)


# --- leitor (layout presumido) ------------------------------------------------------


def test_leitor_le_a_pagina_no_layout_presumido() -> None:
    conteudo = pagina(
        [
            Item("LEITE INTEG FICTICIO 1L", "2", "9.98", codigo="7891234567895"),
            Item("BANANA PRATA KG", "1.234", "8.63", unidade="KG", valor_unitario="6.99"),
        ],
        desconto="0.61",
        emissao="02/11/2026 10:15:30",
    )
    nota = LeitorSvrsHtml().ler(conteudo, "text/html")

    assert nota.cnpj == CNPJ_A
    assert nota.razao_social == "MERCADO FICTICIO DO BAIRRO LTDA"
    assert nota.cidade == "PORTO ALEGRE"
    assert nota.emitida_em == datetime(2026, 11, 2, 10, 15, 30, tzinfo=FUSO)
    assert nota.valor_total == Decimal("18.00")
    assert nota.desconto_total == Decimal("0.61")

    leite, banana = nota.itens
    assert (leite.linha_num, leite.descricao) == (1, "LEITE INTEG FICTICIO 1L")
    assert leite.quantidade == Decimal("2")
    assert leite.valor_total == Decimal("9.98")
    assert leite.valor_unitario == Decimal("4.99")
    assert leite.codigo == "7891234567895"
    # 13 dígitos, prefixo 789 e dígito certo: é código de barras.
    assert leite.gtin == "7891234567895"
    assert banana.unidade == "KG"
    assert banana.quantidade == Decimal("1.234")
    assert banana.valor_unitario == Decimal("6.99")
    # Código curto é do mercado, não GTIN.
    assert banana.codigo == "123"
    assert banana.gtin is None


def test_leitor_nao_toma_codigo_interno_por_gtin() -> None:
    # 13 dígitos com prefixo 789, mas dígito verificador errado.
    conteudo = pagina([Item("ARROZ FICTICIO 5KG", "1", "25.90", codigo="7891234567890")])
    assert LeitorSvrsHtml().ler(conteudo, "text/html").itens[0].gtin is None


def test_leitor_valores_com_milhar() -> None:
    conteudo = pagina([Item("TV FICTICIA", "1", "1234.56")])
    nota = LeitorSvrsHtml().ler(conteudo, "text/html")
    assert nota.itens[0].valor_total == Decimal("1234.56")
    assert nota.valor_total == Decimal("1234.56")


@pytest.mark.parametrize(
    ("conteudo", "tipo", "motivo"),
    [
        (b"<html><body>Captcha</body></html>", "text/html", "tabela de itens"),
        (b'<html><table id="tabResult"></table></html>', "text/html", "vazia"),
        (b"<nfeProc/>", "application/xml", "HTML"),
    ],
)
def test_leitor_recusa_o_que_nao_conhece(conteudo: bytes, tipo: str, motivo: str) -> None:
    with pytest.raises(FormatoDesconhecido, match=motivo):
        LeitorSvrsHtml().ler(conteudo, tipo)


def test_versao_do_leitor() -> None:
    assert LeitorSvrsHtml().versao == VERSAO


def test_leitor_com_amostra_real_anonimizada() -> None:
    """A Consulta Completa de uma nota real (Zaffari, 15/11/2026), anonimizada."""
    nota = LeitorSefazRs().ler(AMOSTRA_REAL.read_bytes(), "text/html")
    assert nota.versao == "sefaz-rs-completa-1"
    assert nota.cnpj == "93015006002914"
    assert nota.razao_social == "COMPANHIA ZAFFARI COMERCIO E INDUSTRIA"
    assert nota.cidade == "PASSO FUNDO"
    assert nota.emitida_em == datetime(2026, 11, 15, 19, 44, 33, tzinfo=FUSO)
    assert nota.valor_total == Decimal("398.56")
    assert nota.desconto_total == Decimal("0")
    assert nota.forma_pagamento == "Cartão de Crédito"
    assert len(nota.itens) == 24
    assert sum(i.valor_total for i in nota.itens) == Decimal("398.56")
    assert all(i.gtin is None for i in nota.itens)
    primeiro, segundo = nota.itens[0], nota.itens[1]
    assert primeiro.descricao == "PAO CACETINHO"
    assert primeiro.quantidade == Decimal("0.5119")
    assert primeiro.unidade == "KG"
    assert primeiro.valor_unitario == Decimal("15.9")
    assert primeiro.valor_total == Decimal("8.14")
    assert primeiro.codigo == "1077397"
    assert segundo.descricao == "IOG GREGO BATAVO TRAD 450G"
    assert segundo.quantidade == Decimal("2")
    assert segundo.unidade == "UN"
    assert segundo.valor_unitario == Decimal("11.98")
    assert segundo.valor_total == Decimal("23.96")


def test_composto_escolhe_o_leitor_do_qr_code() -> None:
    nota = LeitorSefazRs().ler(pagina([Item("ARROZ 5KG", "1", "25.90")]), "text/html")
    assert nota.versao == "svrs-html-1"
    assert LeitorSefazRs().versao == "sefaz-rs-1"


def test_composto_recusa_html_desconhecido() -> None:
    with pytest.raises(FormatoDesconhecido, match="nem a Consulta Completa"):
        LeitorSefazRs().ler(b"<html><body>902 - Parametros invalidos</body></html>", "text/html")
    with pytest.raises(FormatoDesconhecido, match="HTML"):
        LeitorSefazRs().ler(b"<nfeProc/>", "application/xml")
