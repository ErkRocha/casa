"""Espelho Python dos tipos enum nativos do Postgres.

Os nomes aqui têm que bater exatamente com os valores criados na migration
0001. Mudar um valor é mudar o schema — e schema só muda por migration nova.
"""

from enum import StrEnum


class TipoTransacao(StrEnum):
    DESPESA = "despesa"
    RECEITA = "receita"
    #: Pagar fatura não é despesa nova. Fica fora de todo cálculo de gasto.
    TRANSFERENCIA = "transferencia"


class TipoConta(StrEnum):
    CORRENTE = "corrente"
    POUPANCA = "poupanca"
    CARTEIRA = "carteira"
    INVESTIMENTO = "investimento"
    CARTAO = "cartao"


class TipoPagamento(StrEnum):
    CREDITO = "credito"
    DEBITO = "debito"
    PIX = "pix"
    DINHEIRO = "dinheiro"
    BOLETO = "boleto"
    TRANSFERENCIA = "transferencia"


class TipoPessoa(StrEnum):
    INDIVIDUAL = "individual"
    CONJUNTA = "conjunta"


class StatusImportacao(StrEnum):
    PROCESSANDO = "processando"
    AGUARDANDO_REVISAO = "aguardando_revisao"
    CONCLUIDA = "concluida"
    ERRO = "erro"
    CANCELADA = "cancelada"


class StatusItem(StrEnum):
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"
    DUPLICADO = "duplicado"


class Periodicidade(StrEnum):
    MENSAL = "mensal"
    BIMESTRAL = "bimestral"
    TRIMESTRAL = "trimestral"
    SEMESTRAL = "semestral"
    ANUAL = "anual"


#: Nomes dos tipos no Postgres, para `postgresql.ENUM(..., name=...)`.
PG_ENUM_NAMES = {
    TipoTransacao: "tipo_transacao",
    TipoConta: "tipo_conta",
    TipoPagamento: "tipo_pagamento",
    TipoPessoa: "tipo_pessoa",
    StatusImportacao: "status_importacao",
    StatusItem: "status_item",
    Periodicidade: "periodicidade",
}
