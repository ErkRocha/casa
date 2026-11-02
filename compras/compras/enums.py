"""Enums do schema `compras`, espelho dos tipos nativos do Postgres."""

from enum import StrEnum


class SituacaoItem(StrEnum):
    PENDENTE = "pendente"
    COMPRADO = "comprado"


class EstadoDespensa(StrEnum):
    TEM = "tem"
    ACABANDO = "acabando"
    ACABOU = "acabou"


class OrigemItem(StrEnum):
    MANUAL = "manual"
    DESPENSA = "despensa"
    VOZ = "voz"


class OrigemAssociacao(StrEnum):
    """O que decidiu o produto de um item da nota."""

    APELIDO = "apelido"
    GTIN = "gtin"
    USUARIO = "usuario"


class StatusNota(StrEnum):
    LIDA = "lida"
    ERRO = "erro"
