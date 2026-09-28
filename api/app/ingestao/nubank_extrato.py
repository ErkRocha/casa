"""Parser do extrato de conta do Nubank.

Mais chato que a fatura: a transação ocupa várias linhas físicas, e o valor
fica no fim da primeira.

    06 JUL 2026 Total de entradas + 1.958,73
    Transferência recebida pelo Pix ERIK ... - BCO      1.938,73
    SANTANDER (BRASIL) S.A. (0033) Agência: 3418            <- continuação
    Conta: 1087023-3                                        <- continuação
    Total de saídas - 2.314,77
    Pagamento de fatura                                  1.874,77

**O ponto crítico** (D-05): `Pagamento de fatura` é o dinheiro saindo da conta
para quitar o cartão. O gasto detalhado já veio da fatura — contar os dois
como despesa infla tudo em dobro. Foi confirmado nestes extratos: o pagamento
de junho (R$ 1.074,01) é exatamente o total da fatura de junho.

Por isso ele vira `tipo = transferencia`, que o analytics exclui de todo
cálculo de gasto. O mesmo vale para "Valor adicionado na conta por cartão de
crédito" (Pix no crédito), que é movimentação interna.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.enums import TipoTransacao
from app.ingestao.base import (
    MESES_EXTENSO,
    MESES_PT,
    DocumentoExtraido,
    ItemExtraido,
    limpar_descricao,
    primeiro_dia,
    sem_acento,
    valor_brl,
)

ORIGEM = "nubank_extrato"

#: "06 JUL 2026 Total de entradas + 1.958,73"
_CABECALHO_DIA = re.compile(
    r"^(?P<dia>\d{2})\s+(?P<mes>[A-Z]{3})\s+(?P<ano>\d{4})\s+Total de "
    r"(?P<direcao>entradas|sa[íi]das)\s*(?P<sinal>[+-])\s*(?P<valor>[\d.]+,\d{2})$",
    re.I,
)
#: "Total de saídas - 2.314,77" — sem data, herda o dia do cabeçalho anterior.
_TOTAL_DIRECAO = re.compile(
    r"^Total de (?P<direcao>entradas|sa[íi]das)\s*(?P<sinal>[+-])?\s*(?P<valor>[\d.]+,\d{2})$",
    re.I,
)
#: Linha de movimento: descrição + valor no fim, sem "R$".
_MOVIMENTO = re.compile(r"^(?P<desc>.+?)\s+(?P<valor>[\d.]+,\d{2})$")

_PERIODO = re.compile(
    r"(\d{2})\s+DE\s+([A-ZÇÃ]+)\s+DE\s+(\d{4})\s+a\s+(\d{2})\s+DE\s+([A-ZÇÃ]+)\s+DE\s+(\d{4})",
    re.I,
)
#: Totais do cabeçalho — o gabarito da extração.
_TOTAL_ENTRADAS = re.compile(r"Total de entradas\s*\+\s*([\d.]+,\d{2})")
_TOTAL_SAIDAS = re.compile(r"Total de sa[íi]das\s*-\s*([\d.]+,\d{2})")

#: Movimentações que NÃO são gasto novo — são dinheiro andando entre contas
#: do próprio dono. Viram transferência (D-05).
_TRANSFERENCIA_INTERNA = (
    "pagamento de fatura",
    "valor adicionado na conta por cartao de credito",
    "valor adicionado para pix no credito",
)

#: Ruído estrutural do documento: nunca é transação.
#:
#: Casado apenas no **início** da linha. A versão anterior procurava estes
#: termos em qualquer posição, e "Nu Pagamentos" / "CNPJ" aparecem dentro de
#: descrição legítima de Pix (é o banco da contraparte) — o parser descartava
#: transferências reais de centenas de reais por causa disso.
_IGNORAR_PREFIXO = (
    "saldo inicial",
    "saldo final",
    "rendimento liquido",
    "total de entradas",
    "total de saidas",
    "movimentacoes",
    "valores em r$",
    "extrato gerado",
    "tem alguma duvida",
    "cpf ",
    "agencia ",
    "conta:",
    "nu financeira s.a",
    "nu pagamentos s.a",
    "cnpj:",
    "o saldo liquido",
    "nao nos responsabilizamos",
    "asseguramos a autenticidade",
    "caso a solucao",
)


class NubankExtratoParser:
    origem = ORIGEM

    def reconhece(self, texto: str) -> bool:
        limpo = sem_acento(texto).upper()
        return "MOVIMENTACOES" in limpo and ("NU FINANCEIRA" in limpo or "VALORES EM R$" in limpo)

    def extrair(self, texto: str) -> DocumentoExtraido:
        linhas = [linha.strip() for linha in texto.splitlines() if linha.strip()]

        inicio, fim = self._periodo(texto)
        doc = DocumentoExtraido(
            origem=ORIGEM,
            parser="deterministico",
            periodo_inicio=inicio,
            periodo_fim=fim,
            competencia=primeiro_dia(inicio) if inicio else None,
            # O extrato declara os dois lados separadamente. Não dá para
            # somar num total só: transferência interna entra dos dois lados
            # e se anularia.
            total_entradas_declarado=self._total(_TOTAL_ENTRADAS, texto),
            total_saidas_declarado=self._total(_TOTAL_SAIDAS, texto),
        )

        data_corrente: date | None = None
        direcao = "saidas"
        dentro = False

        for numero, linha in enumerate(linhas, 1):
            if sem_acento(linha).lower().startswith("movimentacoes"):
                dentro = True
                continue
            if not dentro:
                continue

            if (cab := _CABECALHO_DIA.match(linha)) is not None:
                mes = MESES_PT.get(sem_acento(cab.group("mes")).upper())
                if mes is not None:
                    data_corrente = date(int(cab.group("ano")), mes, int(cab.group("dia")))
                direcao = (
                    "entradas" if cab.group("direcao").lower().startswith("entrada") else "saidas"
                )
                continue

            if (tot := _TOTAL_DIRECAO.match(linha)) is not None:
                direcao = (
                    "entradas" if tot.group("direcao").lower().startswith("entrada") else "saidas"
                )
                continue

            if self._e_ruido(linha) or data_corrente is None:
                continue

            mov = _MOVIMENTO.match(linha)
            if mov is None:
                # Continuação da linha anterior (agência, conta, banco).
                continue

            doc.itens.append(self._item(mov, linha, numero, data_corrente, direcao))

        return doc

    # -- pedaços -------------------------------------------------------

    def _item(
        self,
        mov: re.Match[str],
        linha: str,
        numero: int,
        data: date,
        direcao: str,
    ) -> ItemExtraido:
        descricao = limpar_descricao(mov.group("desc"))
        chave = sem_acento(descricao).lower()

        if any(chave.startswith(t) or t in chave for t in _TRANSFERENCIA_INTERNA):
            tipo = TipoTransacao.TRANSFERENCIA
            observacao = (
                "Movimentação entre contas próprias — fica fora do cálculo de gasto (D-05)."
            )
            # Precisa de conta de origem e destino, que o parser não sabe.
            # O usuário escolhe na revisão; daí a confiança menor.
            confianca = Decimal("0.70")
        else:
            tipo = TipoTransacao.RECEITA if direcao == "entradas" else TipoTransacao.DESPESA
            observacao = None
            confianca = Decimal("0.95")

        return ItemExtraido(
            linha_bruta=linha,
            linha_num=numero,
            data=data,
            valor=abs(valor_brl(mov.group("valor"))),
            descricao=descricao,
            tipo=tipo,
            # A seção em que a linha caiu diz se o dinheiro entrou ou saiu.
            # É o que permite montar origem e destino da transferência.
            direcao="entrada" if direcao == "entradas" else "saida",
            confianca=confianca,
            observacao=observacao,
        )

    def _e_ruido(self, linha: str) -> bool:
        chave = sem_acento(linha).lower()
        return any(chave.startswith(prefixo) for prefixo in _IGNORAR_PREFIXO)

    def _total(self, padrao: re.Pattern[str], texto: str) -> Decimal | None:
        """Primeiro casamento do total no cabeçalho do documento."""
        casou = padrao.search(texto)
        return valor_brl(casou.group(1)) if casou else None

    def _periodo(self, texto: str) -> tuple[date | None, date | None]:
        casou = _PERIODO.search(texto)
        if casou is None:
            return None, None
        mes_ini = MESES_EXTENSO.get(sem_acento(casou.group(2)).upper())
        mes_fim = MESES_EXTENSO.get(sem_acento(casou.group(5)).upper())
        if mes_ini is None or mes_fim is None:
            return None, None
        return (
            date(int(casou.group(3)), mes_ini, int(casou.group(1))),
            date(int(casou.group(6)), mes_fim, int(casou.group(4))),
        )


__all__ = ["ORIGEM", "NubankExtratoParser"]
