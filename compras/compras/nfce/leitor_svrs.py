"""Leitor da página da consulta pública da NFC-e no portal SVRS (RS).

**Layout do QR code, validado com uma nota real em 20/11/2026**
(``tests/amostras/nfce_rs_qrcode_anonimizada.html``). A consulta pela chave
lê a "Consulta Completa" (``leitor_completa.py``). Este leitor lê a página
"DANFE NFC-e" do portal SVRS, que a URL do QR code mostra:

* emitente: ``.txtTopo`` (razão social), e no mesmo bloco ``.text`` com o
  CNPJ e outro com o endereço;
* itens: linhas de ``#tabResult``, cada uma com ``.txtTit`` (descrição),
  ``.RCod`` ("Código: ..."), ``.Rqtd``, ``.RUN``, ``.RvlUnit`` e ``.valor``;
* totais: ``#totalNota``, pares de rótulo e ``.totalNumb`` ("Valor a pagar
  R$:", "Descontos R$:");
* emissão: o texto "Emissão: dd/mm/aaaa hh:mm:ss" em ``#infos``;
* forma de pagamento: depois de ``#linhaForma``, cada linha com
  ``label.tx`` (o nome, "Cartão de Crédito") e ``.totalNumb`` (o valor);
  com mais de uma, a de maior valor. A página não traz bandeira nem cartão.

Se o layout mudar, troque este leitor por outro com outra ``VERSAO``:
as notas lidas por esta versão continuam com o conteúdo guardado e podem
ser relidas.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from compras.nfce.html import (
    FUSO,
    _Arvore,
    _decimal,
    _depois_do_rotulo,
    _gtin,
    _No,
    decodificar,
)
from compras.nfce.leitor import FormatoDesconhecido, ItemLido, NotaLida

__all__ = ["FUSO", "VERSAO", "LeitorSvrsHtml"]

VERSAO = "svrs-html-1"
# --- o leitor --------------------------------------------------------------------


class LeitorSvrsHtml:
    versao = VERSAO

    def ler(self, conteudo: bytes, tipo: str | None) -> NotaLida:
        if tipo and "html" not in tipo.lower():
            raise FormatoDesconhecido(f"Este leitor lê HTML, não {tipo}.")
        texto = decodificar(conteudo)
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
        forma = self._forma_pagamento(raiz)
        return NotaLida(
            cnpj=cnpj,
            razao_social=razao,
            endereco=endereco,
            cidade=cidade,
            emitida_em=self._emissao(raiz),
            valor_total=valor_total,
            desconto_total=desconto or Decimal("0"),
            itens=itens,
            versao=VERSAO,
            forma_pagamento=forma,
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

    def _forma_pagamento(self, raiz: _No) -> str | None:
        """A forma depois de ``#linhaForma``: ``label.tx`` e o valor pago.

        Com mais de uma, a de maior valor (empate: a primeira). Só o nome da
        forma, como a página mostra; nada de cartão.
        """
        bloco = raiz.por_id("totalNota")
        if bloco is None:
            return None
        formas: list[tuple[Decimal, str]] = []
        depois_da_forma = False
        for no in bloco.filhos:
            if not isinstance(no, _No) or no.tag != "div":
                continue
            if no.attrs.get("id") == "linhaForma":
                depois_da_forma = True
                continue
            if not depois_da_forma:
                continue
            rotulos = [r for r in no.todos() if r.tag == "label" and "tx" in r.classes]
            numeros = no.por_classe("totalNumb")
            if len(rotulos) != 1 or len(numeros) != 1:
                continue
            nome, valor = rotulos[0].texto(), _decimal(numeros[0].texto())
            if nome and valor is not None:
                formas.append((valor, nome))
        if not formas:
            return None
        return max(formas, key=lambda f: f[0])[1]

    def _emissao(self, raiz: _No) -> datetime | None:
        bloco = raiz.por_id("infos") or raiz
        achado = re.search(
            r"Emiss[ãa]o:?\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}):(\d{2}):(\d{2})", bloco.texto()
        )
        if not achado:
            return None
        dia, mes, ano, hora, minuto, segundo = (int(g) for g in achado.groups())
        return datetime(ano, mes, dia, hora, minuto, segundo, tzinfo=FUSO)
