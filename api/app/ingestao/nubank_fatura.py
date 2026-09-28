"""Parser da fatura de cartão do Nubank.

Layout confirmado em três faturas reais (jun, jul e ago/2026). A soma das
linhas extraídas bate exatamente com o "Total a pagar" declarado nas três — é
esse o teste que vale, e ele roda em `tests/test_ingestao.py`.

Formato das linhas, dentro do bloco `TRANSAÇÕES DE ... A ...`:

    04 JUN •••• 7704 Pico                     R$ 50,00
    10 JUN Recarga de celular                 R$ 25,00

O bloco `•••• NNNN` é o final do cartão e só aparece em compra. A ausência
dele marca "outros lançamentos" (recarga, anuidade, juros) — que também são
gasto de verdade e por isso entram.

A linha **não traz o ano**. Ele é inferido do período vigente, com cuidado na
virada de dezembro para janeiro.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.enums import TipoTransacao
from app.ingestao.base import (
    MESES_PT,
    DocumentoExtraido,
    ItemExtraido,
    limpar_descricao,
    primeiro_dia,
    sem_acento,
    valor_brl,
)

ORIGEM = "nubank_fatura"

_INICIO_TRANSACOES = re.compile(r"^TRANSA[ÇC][ÕO]ES DE ", re.I)

_LINHA = re.compile(
    r"^(?P<dia>\d{2})\s+(?P<mes>[A-Z]{3})\s+"
    r"(?:•{2,}\s*(?P<cartao>\d{4})\s+)?"
    r"(?P<desc>.+?)\s+"
    r"(?P<sinal>[−-])?R\$\s?(?P<valor>[\d.]+,\d{2})$"
)

#: "Parcela 3/12" ou "3/12" no fim da descrição.
_PARCELA = re.compile(r"(?:parcela\s+)?(\d{1,2})\s*/\s*(\d{1,2})\s*$", re.I)

_VENCIMENTO = re.compile(r"Data de vencimento:\s*(\d{2})\s+([A-Z]{3})\s+(\d{4})", re.I)
_PERIODO = re.compile(
    r"Per[íi]odo vigente:\s*(\d{2})\s+([A-Z]{3})\s+a\s+(\d{2})\s+([A-Z]{3})", re.I
)
#: O total do RESUMO, não o da tabela de parcelamento — que aparece antes no
#: PDF e traz o valor de quem parcela a fatura, não o que se deve.
_RESUMO = re.compile(r"RESUMO DA FATURA ATUAL(?P<bloco>.{0,800})", re.S)
_TOTAL_PAGAR = re.compile(r"Total a pagar\s+R\$\s?([\d.]+,\d{2})")

#: Linhas do cabeçalho e rodapé que repetem em toda página do bloco.
_RUIDO = re.compile(
    r"^(FATURA \d{2}|TRANSA[ÇC][ÕO]ES DE|\d+ de \d+$|[A-ZÀ-Ú\s]+$"
    r"|Pagamentos e Financiamentos|Total a pagar:|[A-Z][a-zà-ú]+(?: [A-Z][a-zà-ú]+)+ R\$)",
    re.I,
)

#: Fim de tudo que é lançamento: daqui para baixo só há texto legal.
_FIM_TRANSACOES = re.compile(
    r"^(Em cumprimento [àa] regula[çc][ãa]o|Como assegurado pela Resolu[çc][ãa]o)", re.I
)

#: Lançamentos que aparecem na fatura mas NÃO são cobrança deste mês.
#:
#: A seção "Pagamentos e Financiamentos" mistura duas coisas: o pagamento da
#: fatura anterior (que não é compra, e cortá-la fora é o que faz o total
#: fechar) e Pix no crédito financiado — que **é** cobrança real, com IOF e
#: juros embutidos. Cortar a seção inteira perdia R$ 33,83 na fatura de
#: agosto; por isso o filtro é por linha, não por bloco.
_NAO_E_COBRANCA = re.compile(r"^(Pagamento em\b|Saldo restante da fatura)", re.I)


class NubankFaturaParser:
    origem = ORIGEM

    def reconhece(self, texto: str) -> bool:
        """Marcadores presentes em todas as variantes da fatura.

        A primeira versão exigia "Nu Pagamentos", que vem do rodapé jurídico —
        e uma das faturas reais não o traz: quando não há juros nem
        parcelamento, o Nubank emite um PDF bem mais curto, sem essas páginas.
        `TRANSAÇÕES DE` mais o vencimento existem nas duas variantes.
        """
        limpo = sem_acento(texto).upper()
        return "TRANSACOES DE" in limpo and (
            "DATA DE VENCIMENTO" in limpo or "RESUMO DA FATURA" in limpo
        )

    def extrair(self, texto: str) -> DocumentoExtraido:
        linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]

        vencimento = self._vencimento(texto)
        inicio, fim = self._periodo(texto, vencimento)
        doc = DocumentoExtraido(
            origem=ORIGEM,
            parser="deterministico",
            periodo_inicio=inicio,
            periodo_fim=fim,
            # Fatura que vence em julho é despesa de julho, mesmo que a
            # compra tenha sido em 04 JUN (D-02).
            competencia=primeiro_dia(vencimento) if vencimento else None,
            total_declarado=self._total(texto),
        )

        dentro = False
        for numero, linha in enumerate(linhas, 1):
            if _INICIO_TRANSACOES.match(linha):
                dentro = True
                continue
            if not dentro:
                continue
            if _FIM_TRANSACOES.match(linha):
                break

            casou = _LINHA.match(linha)
            if casou is None:
                # Linha de cabeçalho repetido ou rodapé: esperado, sem aviso.
                if not _RUIDO.match(linha) and re.search(r"R\$\s?[\d.]+,\d{2}", linha):
                    doc.avisos.append(f"linha {numero} tem valor mas não casou: {linha!r}")
                continue

            item = self._item(casou, linha, numero, inicio, fim)
            if item is not None:
                doc.itens.append(item)

        return doc

    # -- pedaços -------------------------------------------------------

    def _item(
        self,
        casou: re.Match[str],
        linha: str,
        numero: int,
        inicio: date | None,
        fim: date | None,
    ) -> ItemExtraido | None:
        mes = MESES_PT.get(sem_acento(casou.group("mes")).upper())
        if mes is None:
            return None

        dia = int(casou.group("dia"))
        ano = self._ano_de(mes, inicio, fim)
        if ano is None:
            return None

        descricao = casou.group("desc").strip()
        if _NAO_E_COBRANCA.match(descricao):
            return None

        parcela_num = parcela_total = None
        if (p := _PARCELA.search(descricao)) is not None:
            parcela_num, parcela_total = int(p.group(1)), int(p.group(2))
            descricao = descricao[: p.start()].strip()

        valor = valor_brl(casou.group("valor"))
        negativo = casou.group("sinal") is not None

        # `transacoes` exige valor > 0. Linha de R$ 0,00 é marcador do
        # documento ("Saldo restante da fatura anterior"), não movimento.
        if valor == 0:
            return None

        # Valor negativo numa fatura é estorno: dinheiro voltando.
        tipo = TipoTransacao.RECEITA if negativo else TipoTransacao.DESPESA

        return ItemExtraido(
            linha_bruta=linha,
            linha_num=numero,
            data=date(ano, mes, dia),
            valor=abs(valor),
            descricao=limpar_descricao(descricao),
            tipo=tipo,
            cartao_final=casou.group("cartao"),
            parcela_num=parcela_num,
            parcela_total=parcela_total,
            observacao="estorno" if negativo else None,
        )

    def _ano_de(self, mes: int, inicio: date | None, fim: date | None) -> int | None:
        """O ano que a linha não traz.

        O período pode cruzar o réveillon (03 DEZ a 03 JAN): aí dezembro é do
        ano do início e janeiro é do ano do fim.
        """
        if inicio is None or fim is None:
            return None
        if inicio.year == fim.year:
            return inicio.year
        return inicio.year if mes >= inicio.month else fim.year

    def _vencimento(self, texto: str) -> date | None:
        casou = _VENCIMENTO.search(texto)
        if casou is None:
            return None
        mes = MESES_PT.get(sem_acento(casou.group(2)).upper())
        if mes is None:
            return None
        return date(int(casou.group(3)), mes, int(casou.group(1)))

    def _periodo(self, texto: str, vencimento: date | None) -> tuple[date | None, date | None]:
        casou = _PERIODO.search(texto)
        if casou is None or vencimento is None:
            return None, None

        mes_ini = MESES_PT.get(sem_acento(casou.group(2)).upper())
        mes_fim = MESES_PT.get(sem_acento(casou.group(4)).upper())
        if mes_ini is None or mes_fim is None:
            return None, None

        # O período termina pouco antes do vencimento; é dele que sai o ano.
        ano_fim = vencimento.year if mes_fim <= vencimento.month else vencimento.year - 1
        fim = date(ano_fim, mes_fim, int(casou.group(3)))
        ano_ini = ano_fim if mes_ini <= mes_fim else ano_fim - 1
        inicio = date(ano_ini, mes_ini, int(casou.group(1)))
        return inicio, fim

    def _total(self, texto: str) -> Decimal | None:
        resumo = _RESUMO.search(texto)
        if resumo is None:
            return None
        casou = _TOTAL_PAGAR.search(resumo.group("bloco"))
        return valor_brl(casou.group(1)) if casou else None
