"""Contratos da ingestão.

O parser não fala com o banco. Ele recebe texto e devolve `ItemExtraido` —
dado cru, sem id de categoria, sem pessoa, sem nada resolvido. Quem persiste é
o service; quem promove para `transacoes` é o usuário (D-07).

Essa separação é o que permite testar o parser contra os PDFs reais sem subir
banco nenhum.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.enums import TipoTransacao

#: Meses como o Nubank escreve, em maiúsculas e sem acento.
MESES_PT = {
    "JAN": 1,
    "FEV": 2,
    "MAR": 3,
    "ABR": 4,
    "MAI": 5,
    "JUN": 6,
    "JUL": 7,
    "AGO": 8,
    "SET": 9,
    "OUT": 10,
    "NOV": 11,
    "DEZ": 12,
}

MESES_EXTENSO = {
    "JANEIRO": 1,
    "FEVEREIRO": 2,
    "MARCO": 3,
    "ABRIL": 4,
    "MAIO": 5,
    "JUNHO": 6,
    "JULHO": 7,
    "AGOSTO": 8,
    "SETEMBRO": 9,
    "OUTUBRO": 10,
    "NOVEMBRO": 11,
    "DEZEMBRO": 12,
}


def sem_acento(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def valor_brl(texto: str) -> Decimal:
    """`1.234,56` -> `Decimal('1234.56')`.

    Decimal desde a primeira linha: converter para float aqui e voltar depois
    já teria comido centavo.
    """
    limpo = texto.strip().replace("R$", "").replace("−", "-").replace(" ", "")
    negativo = limpo.startswith("-")
    limpo = limpo.lstrip("-+").replace(".", "").replace(",", ".")
    valor = Decimal(limpo)
    return -valor if negativo else valor


@dataclass(slots=True)
class ItemExtraido:
    """Uma linha reconhecida no documento.

    `valor` é sempre positivo — o sinal vive em `tipo`, igual em `transacoes`.
    """

    linha_bruta: str
    linha_num: int
    data: date
    valor: Decimal
    descricao: str
    tipo: TipoTransacao = TipoTransacao.DESPESA
    #: Últimos 4 dígitos do cartão, quando a linha traz.
    cartao_final: str | None = None
    #: Parcela "3/12", quando houver.
    parcela_num: int | None = None
    parcela_total: int | None = None
    #: "entrada" ou "saida". Só faz sentido em transferência, e ali é
    #: obrigatório: `transacoes` exige conta de origem e destino, e sem a
    #: direção não há como saber qual é qual.
    direcao: str | None = None
    #: Por que o parser acha que acertou. 1.0 = leitura direta e inequívoca.
    confianca: Decimal = Decimal("1.00")
    #: Nota para a tela de revisão, quando algo merece o olho humano.
    observacao: str | None = None


@dataclass(slots=True)
class DocumentoExtraido:
    """O resultado de um arquivo inteiro."""

    origem: str
    parser: str
    itens: list[ItemExtraido] = field(default_factory=list)
    periodo_inicio: date | None = None
    periodo_fim: date | None = None
    #: Competência a aplicar em todos os itens. Na fatura é o mês do
    #: vencimento — compra de 28/06 na fatura de julho é despesa de julho
    #: (D-02). No extrato é o mês da própria data.
    competencia: date | None = None
    #: Total que o documento declara. `None` quando ele não declara.
    #: Na fatura é o "Total a pagar".
    total_declarado: Decimal | None = None
    #: O extrato declara os dois lados em vez de um total só.
    total_entradas_declarado: Decimal | None = None
    total_saidas_declarado: Decimal | None = None
    #: Linhas que pareciam transação mas não casaram. Vazio é o esperado.
    avisos: list[str] = field(default_factory=list)

    @property
    def soma_itens(self) -> Decimal:
        """Saldo líquido dos itens: despesas menos receitas.

        Receita abate porque, numa fatura, estorno reduz o que se deve — somar
        o valor absoluto faria a conferência estourar justamente no mês em que
        houve devolução.

        Transferência fica fora: no extrato, o pagamento da fatura não é gasto
        novo (D-05).
        """
        total = Decimal("0")
        for item in self.itens:
            if item.tipo is TipoTransacao.DESPESA:
                total += item.valor
            elif item.tipo is TipoTransacao.RECEITA:
                total -= item.valor
        return total

    @property
    def total_entradas(self) -> Decimal:
        return sum((i.valor for i in self.itens if i.direcao == "entrada"), Decimal("0"))

    @property
    def total_saidas(self) -> Decimal:
        return sum((i.valor for i in self.itens if i.direcao == "saida"), Decimal("0"))

    @property
    def confere(self) -> bool | None:
        """A extração bate com o que o próprio documento declara?

        É o único jeito honesto de saber se o parser perdeu linha, e é o que
        a tela de revisão mostra antes de deixar promover. `None` quando o
        documento não declara nada — aí a tela avisa, em vez de fingir
        certeza.
        """
        if self.total_declarado is not None:
            return self.soma_itens == self.total_declarado

        if self.total_entradas_declarado is not None and self.total_saidas_declarado is not None:
            return (
                self.total_entradas == self.total_entradas_declarado
                and self.total_saidas == self.total_saidas_declarado
            )

        return None


class Parser(Protocol):
    """Todo parser de banco implementa isto."""

    #: Identificador gravado em `importacoes.origem`.
    origem: str

    def reconhece(self, texto: str) -> bool:
        """O texto extraído é deste formato?"""
        ...

    def extrair(self, texto: str) -> DocumentoExtraido: ...


def primeiro_dia(d: date) -> date:
    return d.replace(day=1)


def limpar_descricao(texto: str) -> str:
    """Colapsa espaço e corta lixo de borda, sem mexer no conteúdo.

    O texto cru original vai para `descricao_original` e é imutável (regra
    11); esta limpeza serve à `descricao` editável.
    """
    return re.sub(r"\s+", " ", texto).strip(" -–—•\t")
