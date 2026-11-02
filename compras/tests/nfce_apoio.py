"""Chaves e páginas de NFC-e **inventadas** para os testes.

Nada aqui vem de nota real: CNPJs, mercados e produtos são fictícios. A
página segue o layout presumido do portal SVRS (``compras/nfce/leitor_svrs.py``);
o teste contra uma nota real fica pendente em ``test_leitor_svrs.py`` até
haver uma amostra anonimizada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from compras.nfce.chave import digito_verificador
from compras.nfce.consulta import ConsultaFalhou, Resposta

#: CNPJs fictícios (só o formato importa aqui).
CNPJ_A = "11222333000181"
CNPJ_B = "44555666000172"


def chave(
    cnpj: str = CNPJ_A, numero: int = 1, uf: str = "43", modelo: str = "65", aamm: str = "2611"
) -> str:
    """Uma chave de 44 dígitos com o dígito verificador certo."""
    base = f"{uf}{aamm}{cnpj}{modelo}001{numero:09d}1{numero:08d}"
    assert len(base) == 43, base
    return base + digito_verificador(base)


def url_qr(chave_: str) -> str:
    """A URL do QR code versão 2, com um hash qualquer."""
    return f"https://www.sefaz.rs.gov.br/NFCE/NFCE-COM.aspx?p={chave_}|2|1|1|ABCDEF0123456789"


@dataclass(frozen=True)
class Item:
    descricao: str
    quantidade: str
    valor_total: str
    unidade: str = "UN"
    valor_unitario: str | None = None
    codigo: str = "123"


def _br(valor: str) -> str:
    """ "1234.5" -> "1.234,50" """
    d = Decimal(valor).quantize(Decimal("0.01"))
    inteiro, centavos = f"{d:.2f}".split(".")
    com_ponto = f"{int(inteiro):,}".replace(",", ".")
    return f"{com_ponto},{centavos}"


def pagina(
    itens: list[Item],
    *,
    cnpj: str = CNPJ_A,
    razao: str = "MERCADO FICTICIO DO BAIRRO LTDA",
    endereco: str = "RUA INVENTADA, 100, , CENTRO, PORTO ALEGRE, RS",
    emissao: str = "02/11/2026 10:15:30",
    desconto: str = "0",
    total: str | None = None,
) -> bytes:
    """A página da consulta, no layout presumido do portal SVRS."""
    soma = sum((Decimal(i.valor_total) for i in itens), Decimal("0"))
    a_pagar = Decimal(total) if total is not None else soma - Decimal(desconto)
    linhas = []
    for n, i in enumerate(itens, start=1):
        unit = i.valor_unitario or str(Decimal(i.valor_total) / Decimal(i.quantidade))
        linhas.append(
            f"""
            <tr id="Item + {n}">
              <td valign="top">
                <span class="txtTit">{i.descricao}</span>
                <span class="RCod">(Código: {i.codigo} )</span><br>
                <span class="Rqtd"><strong>Qtde.:</strong>{str(i.quantidade).replace(".", ",")}</span>
                <span class="RUN"><strong>UN: </strong>{i.unidade}</span>
                <span class="RvlUnit"><strong>Vl. Unit.:</strong>&nbsp;{_br(unit)}</span>
              </td>
              <td align="right" valign="top" class="txtTit noWrap">
                Vl. Total<br><span class="valor">{_br(i.valor_total)}</span>
              </td>
            </tr>"""
        )
    cnpj_fmt = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>NFC-e</title></head>
<body><div id="conteudo">
  <div class="txtCenter">
    <div id="u20" class="txtTopo">{razao}</div>
    <div class="text">CNPJ: {cnpj_fmt}</div>
    <div class="text">{endereco}</div>
  </div>
  <table border="0" align="center" cellpadding="0" cellspacing="0" id="tabResult">
    {"".join(linhas)}
  </table>
  <div id="totalNota" class="txtRight">
    <div id="linhaTotal"><label>Qtd. total de itens:</label><span class="totalNumb">{len(itens)}</span></div>
    <div id="linhaTotal"><label>Valor total R$:</label><span class="totalNumb">{_br(str(soma))}</span></div>
    <div id="linhaTotal"><label>Descontos R$:</label><span class="totalNumb">{_br(desconto)}</span></div>
    <div id="linhaTotal" class="linhaShade"><label>Valor a pagar R$:</label><span class="totalNumb txtMax">{_br(str(a_pagar))}</span></div>
    <div id="linhaForma"><label>Forma de pagamento:</label><span class="totalNumb txtTitR">Valor pago R$:</span></div>
  </div>
  <div id="infos" class="txtCenter">
    <ul><li><strong>Número: </strong>1 <strong> Série: </strong>1 <strong> Emissão: </strong>{emissao} - Via Consumidor</li></ul>
  </div>
</div></body></html>"""
    return html.encode("utf-8")


@dataclass
class ConsultaFalsa:
    """Responde o que estiver em `paginas` (por chave); conta as buscas."""

    paginas: dict[str, bytes] = field(default_factory=dict)
    tipo: str = "text/html"
    falhar: bool = False
    buscas: list[str] = field(default_factory=list)

    def buscar(self, url: str) -> Resposta:
        self.buscas.append(url)
        if self.falhar:
            raise ConsultaFalhou("A SEFAZ não respondeu: ConnectTimeout.")
        for chave_, conteudo in self.paginas.items():
            if chave_ in url:
                return Resposta(conteudo, self.tipo, url)
        raise ConsultaFalhou("A SEFAZ respondeu 404.")
