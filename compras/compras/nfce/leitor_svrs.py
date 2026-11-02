"""Leitor da página da consulta pública da NFC-e no portal SVRS (RS).

**Layout presumido, pendente de uma nota real.** Não havia amostra quando
este leitor foi escrito (02/11/2026). Ele segue o layout conhecido da página
"DANFE NFC-e" do portal SVRS, que o RS usa:

* emitente: ``.txtTopo`` (razão social), e no mesmo bloco ``.text`` com o
  CNPJ e outro com o endereço;
* itens: linhas de ``#tabResult``, cada uma com ``.txtTit`` (descrição),
  ``.RCod`` ("Código: ..."), ``.Rqtd``, ``.RUN``, ``.RvlUnit`` e ``.valor``;
* totais: ``#totalNota``, pares de rótulo e ``.totalNumb`` ("Valor a pagar
  R$:", "Descontos R$:");
* emissão: o texto "Emissão: dd/mm/aaaa hh:mm:ss" em ``#infos``.

Quando chegar uma nota de verdade (anonimizada, ver
``tests/amostras/README.md``), o teste pendente passa a rodar contra ela. Se
o layout real for outro, troque este leitor por outro com outra ``VERSAO``:
as notas lidas por esta versão continuam com o conteúdo guardado e podem
ser relidas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from compras.nfce.leitor import FormatoDesconhecido, ItemLido, NotaLida

VERSAO = "svrs-html-1"
FUSO = ZoneInfo("America/Sao_Paulo")

_VAZIOS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)


# --- uma árvore mínima, só com a biblioteca padrão ------------------------------


@dataclass
class _No:
    tag: str
    attrs: dict[str, str]
    filhos: list[_No | str] = field(default_factory=list)

    @property
    def classes(self) -> set[str]:
        return set(self.attrs.get("class", "").split())

    def texto(self) -> str:
        partes: list[str] = []
        for f in self.filhos:
            partes.append(f if isinstance(f, str) else f.texto())
        return " ".join(" ".join(partes).split())

    def todos(self) -> list[_No]:
        achados: list[_No] = []
        for f in self.filhos:
            if isinstance(f, _No):
                achados.append(f)
                achados.extend(f.todos())
        return achados

    def por_classe(self, classe: str) -> list[_No]:
        return [n for n in self.todos() if classe in n.classes]

    def por_id(self, id_: str) -> _No | None:
        return next((n for n in self.todos() if n.attrs.get("id") == id_), None)


class _Arvore(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raiz = _No("raiz", {})
        self._pilha = [self.raiz]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        no = _No(tag, {k: v or "" for k, v in attrs})
        self._pilha[-1].filhos.append(no)
        if tag not in _VAZIOS:
            self._pilha.append(no)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._pilha[-1].filhos.append(_No(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag: str) -> None:
        # HTML real fecha fora de ordem: volta até a tag aberta mais próxima.
        for i in range(len(self._pilha) - 1, 0, -1):
            if self._pilha[i].tag == tag:
                del self._pilha[i:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self._pilha[-1].filhos.append(data)


# --- números e datas no formato da página ---------------------------------------


def _decimal(texto: str | None) -> Decimal | None:
    """ "1.234,56" -> 1234.56; o primeiro número do texto."""
    if not texto:
        return None
    achado = re.search(r"-?\d[\d.]*(?:,\d+)?", texto)
    if not achado:
        return None
    try:
        return Decimal(achado.group(0).replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def _depois_do_rotulo(no: _No) -> str:
    """O texto de um campo como "Qtde.: 2", sem o rótulo."""
    return no.texto().split(":", 1)[-1].strip()


def _gtin(codigo: str | None) -> str | None:
    """O código vira GTIN só quando é, com certeza razoável, um código de
    barras brasileiro: 13 dígitos, prefixo GS1 Brasil (789/790) e dígito
    verificador certo. Código interno do mercado fica só em `codigo`."""
    if not codigo or not re.fullmatch(r"\d{13}", codigo) or codigo[:3] not in {"789", "790"}:
        return None
    soma = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(codigo[:12]))
    return codigo if (10 - soma % 10) % 10 == int(codigo[12]) else None


# --- o leitor --------------------------------------------------------------------


class LeitorSvrsHtml:
    versao = VERSAO

    def ler(self, conteudo: bytes, tipo: str | None) -> NotaLida:
        if tipo and "html" not in tipo.lower():
            raise FormatoDesconhecido(f"Este leitor lê HTML, não {tipo}.")
        texto = conteudo.decode("utf-8", errors="replace")
        arvore = _Arvore()
        arvore.feed(texto)
        arvore.close()
        raiz = arvore.raiz

        tabela = raiz.por_id("tabResult")
        if tabela is None:
            raise FormatoDesconhecido("A página não tem a tabela de itens (#tabResult).")
        itens = self._itens(tabela)
        if not itens:
            raise FormatoDesconhecido("A tabela de itens está vazia.")

        razao, cnpj, endereco, cidade = self._emitente(raiz)
        valor_total, desconto = self._totais(raiz)
        return NotaLida(
            cnpj=cnpj,
            razao_social=razao,
            endereco=endereco,
            cidade=cidade,
            emitida_em=self._emissao(raiz),
            valor_total=valor_total,
            desconto_total=desconto or Decimal("0"),
            itens=itens,
        )

    def _itens(self, tabela: _No) -> list[ItemLido]:
        itens: list[ItemLido] = []
        for linha in (n for n in tabela.todos() if n.tag == "tr"):
            titulo = next(iter(linha.por_classe("txtTit")), None)
            valor = next(iter(linha.por_classe("valor")), None)
            if titulo is None or valor is None:
                continue
            campos = {
                classe: next(iter(linha.por_classe(classe)), None)
                for classe in ("RCod", "Rqtd", "RUN", "RvlUnit")
            }
            total = _decimal(valor.texto())
            quantidade = _decimal(_depois_do_rotulo(campos["Rqtd"])) if campos["Rqtd"] else None
            if total is None or not quantidade or quantidade <= 0:
                raise FormatoDesconhecido(f"Item sem quantidade ou valor: {titulo.texto()!r}.")
            codigo = None
            if campos["RCod"] is not None:
                achado = re.search(r"\d+", campos["RCod"].texto())
                codigo = achado.group(0) if achado else None
            unidade = _depois_do_rotulo(campos["RUN"]).upper() if campos["RUN"] else None
            itens.append(
                ItemLido(
                    linha_num=len(itens) + 1,
                    descricao=titulo.texto(),
                    quantidade=quantidade,
                    valor_total=total,
                    unidade=unidade or None,
                    valor_unitario=(
                        _decimal(_depois_do_rotulo(campos["RvlUnit"]))
                        if campos["RvlUnit"]
                        else None
                    ),
                    codigo=codigo,
                    gtin=_gtin(codigo),
                )
            )
        return itens

    def _emitente(self, raiz: _No) -> tuple[str | None, str | None, str | None, str | None]:
        topo = next(iter(raiz.por_classe("txtTopo")), None)
        razao = (topo.texto() or None) if topo else None
        cnpj = endereco = cidade = None
        for no in raiz.por_classe("text"):
            t = no.texto()
            if cnpj is None and "CNPJ" in t.upper():
                digitos = re.sub(r"\D", "", t)
                cnpj = digitos if len(digitos) == 14 else None
            elif endereco is None and "," in t and "CNPJ" not in t.upper():
                endereco = t
                partes = [p.strip() for p in t.split(",") if p.strip()]
                # "..., BAIRRO, CIDADE, UF": a cidade vem antes da UF.
                if len(partes) >= 2 and re.fullmatch(r"[A-Z]{2}", partes[-1]):
                    cidade = partes[-2]
        return razao, cnpj, endereco, cidade

    def _totais(self, raiz: _No) -> tuple[Decimal | None, Decimal | None]:
        bloco = raiz.por_id("totalNota")
        if bloco is None:
            return None, None
        valores: dict[str, Decimal | None] = {}
        for no in bloco.todos():
            if no.tag != "div":
                continue
            numeros = no.por_classe("totalNumb")
            # Só a linha "rótulo + número"; um bloco que embrulha várias
            # linhas misturaria os rótulos.
            if len(numeros) != 1:
                continue
            numero = numeros[0]
            rotulo = no.texto().upper()
            valores[rotulo] = _decimal(numero.texto())
        a_pagar = next((v for r, v in valores.items() if "A PAGAR" in r), None)
        total = next((v for r, v in valores.items() if "VALOR TOTAL" in r), None)
        desconto = next((v for r, v in valores.items() if "DESCONTO" in r), None)
        return a_pagar if a_pagar is not None else total, desconto

    def _emissao(self, raiz: _No) -> datetime | None:
        bloco = raiz.por_id("infos") or raiz
        achado = re.search(
            r"Emiss[ãa]o:?\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", bloco.texto()
        )
        if not achado:
            return None
        dia, mes, ano, hora, minuto, segundo = (int(g) for g in achado.groups())
        return datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=FUSO)
