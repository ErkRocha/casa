"""Leitor da "Consulta Completa da NFC-e" da SEFAZ-RS.

É a página que a consulta pela chave devolve depois de enviar o formulário
(validada com uma nota real em 18/11/2026; amostra anonimizada em
``tests/amostras/nfce_rs_anonimizada.html``). A página vem em iso-8859-1.

* emitente: ``NFCCabecalho_SubTitulo`` (razão social) e, nas células
  ``NFCCabecalho_SubTitulo1``, "CNPJ: ..." e o endereço ("..., CIDADE, UF");
* emissão: "Data de Emissão: dd/mm/aaaa hh:mm:ss";
* itens: linhas ``<tr id="Item + N">`` com seis células ``NFCDetalhe_Item``
  (código, descrição, quantidade, unidade, valor unitário, valor total);
* totais: linhas de duas células ``NFCDetalhe_Item`` ("Valor total R$",
  "Valor descontos R$", "Valor a pagar R$" se houver) e, depois de "FORMA
  PAGAMENTO", a forma usada.

O código impresso é o interno do mercado (18 dígitos com zeros à esquerda): é
guardado sem os zeros. Não há GTIN nesta página. O CPF do consumidor nunca é
lido. O valor total da nota é "Valor a pagar R$" se a linha existir; senão,
"Valor total R$".
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from compras.nfce.html import FUSO, _Arvore, _decimal, _gtin, _No, decodificar
from compras.nfce.leitor import FormatoDesconhecido, ItemLido, NotaLida

VERSAO = "sefaz-rs-completa-1"
_CLASSE_CELULA = "NFCDetalhe_Item"


class LeitorConsultaCompleta:
    versao = VERSAO

    def ler(self, conteudo: bytes, tipo: str | None) -> NotaLida:
        if tipo and "html" not in tipo.lower():
            raise FormatoDesconhecido(f"Este leitor lê HTML, não {tipo}.")
        arvore = _Arvore()
        arvore.feed(decodificar(conteudo))
        arvore.close()
        raiz = arvore.raiz

        itens = self._itens(raiz)
        if not itens:
            raise FormatoDesconhecido("A Consulta Completa não tem linhas de itens.")
        razao, cnpj, endereco, cidade = self._emitente(raiz)
        total, desconto, forma = self._totais(raiz)
        return NotaLida(
            cnpj=cnpj,
            razao_social=razao,
            endereco=endereco,
            cidade=cidade,
            emitida_em=self._emissao(raiz),
            valor_total=total,
            desconto_total=desconto if desconto is not None else Decimal("0"),
            itens=itens,
            versao=VERSAO,
            forma_pagamento=forma,
        )

    @staticmethod
    def _celulas(linha: _No) -> list[str]:
        return [c.texto() for c in linha.todos() if c.tag == "td" and _CLASSE_CELULA in c.classes]

    def _itens(self, raiz: _No) -> list[ItemLido]:
        itens: list[ItemLido] = []
        for linha in (n for n in raiz.todos() if n.tag == "tr"):
            if not linha.attrs.get("id", "").startswith("Item"):
                continue
            celulas = self._celulas(linha)
            if len(celulas) < 6:
                continue
            codigo_bruto, descricao, qtd, un, unitario, total = celulas[:6]
            quantidade = _decimal(qtd)
            valor_total = _decimal(total)
            if valor_total is None or not quantidade or quantidade <= 0:
                raise FormatoDesconhecido(f"Item sem quantidade ou valor: {descricao!r}.")
            codigo = (codigo_bruto.lstrip("0") or None) if codigo_bruto.isdigit() else None
            itens.append(
                ItemLido(
                    linha_num=len(itens) + 1,
                    descricao=descricao,
                    quantidade=quantidade,
                    valor_total=valor_total,
                    unidade=un.upper() or None,
                    valor_unitario=_decimal(unitario),
                    codigo=codigo,
                    gtin=_gtin(codigo),
                )
            )
        return itens

    def _emitente(self, raiz: _No) -> tuple[str | None, str | None, str | None, str | None]:
        titulo = next(iter(raiz.por_classe("NFCCabecalho_SubTitulo")), None)
        razao = (titulo.texto() or None) if titulo else None
        cnpj = endereco = cidade = None
        for no in raiz.por_classe("NFCCabecalho_SubTitulo1"):
            t = no.texto()
            if cnpj is None and "CNPJ" in t.upper():
                achado = re.search(r"CNPJ:?\s*([\d./-]+)", t, re.IGNORECASE)
                digitos = re.sub(r"\D", "", achado.group(1)) if achado else ""
                cnpj = digitos if len(digitos) == 14 else None
            elif endereco is None and "," in t and "CNPJ" not in t.upper():
                endereco = t
                partes = [p.strip() for p in t.split(",") if p.strip()]
                # "..., BAIRRO, CIDADE, UF": a cidade vem antes da UF.
                if len(partes) >= 2 and re.fullmatch(r"[A-Z]{2}", partes[-1]):
                    cidade = partes[-2]
        return razao, cnpj, endereco, cidade

    def _totais(self, raiz: _No) -> tuple[Decimal | None, Decimal | None, str | None]:
        total = a_pagar = desconto = None
        forma = None
        depois_da_forma = False
        for linha in (n for n in raiz.todos() if n.tag == "tr"):
            if linha.attrs.get("id", "").startswith("Item"):
                continue
            celulas = self._celulas(linha)
            if len(celulas) != 2:
                continue
            rotulo = celulas[0].upper()
            if depois_da_forma:
                forma = celulas[0]
                depois_da_forma = False
            elif rotulo.startswith("FORMA PAGAMENTO"):
                depois_da_forma = forma is None
            elif "VALOR A PAGAR" in rotulo:
                a_pagar = _decimal(celulas[1])
            elif "VALOR TOTAL" in rotulo:
                total = _decimal(celulas[1])
            elif "DESCONTO" in rotulo:
                desconto = _decimal(celulas[1])
        return (a_pagar if a_pagar is not None else total), desconto, forma

    def _emissao(self, raiz: _No) -> datetime | None:
        achado = re.search(
            r"Data de Emiss[ãa]o:?\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})",
            raiz.texto(),
        )
        if not achado:
            return None
        dia, mes, ano, hora, minuto, segundo = (int(g) for g in achado.groups())
        return datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=FUSO)
