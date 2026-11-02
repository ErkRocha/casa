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
