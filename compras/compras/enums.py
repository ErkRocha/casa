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
    #: Posto pela geração da lista a partir do cardápio (D-30).
    CARDAPIO = "cardapio"
    #: Criado pela conferência da nota: a diferença de quantidade que volta (D-33).
    NOTA = "nota"


class FechamentoItem(StrEnum):
    """Como o item comprado deixou de esperar nota (migration 0006, D-33)."""

    NOTA = "nota"
    SEM_NOTA = "sem_nota"
    NAO_COMPREI = "nao_comprei"


class OrigemAssociacao(StrEnum):
    """O que decidiu o produto de um item da nota."""

    APELIDO = "apelido"
    GTIN = "gtin"
    USUARIO = "usuario"


class StatusNota(StrEnum):
    LIDA = "lida"
    ERRO = "erro"


# --- Cardápio (migration 0004, D-30) -----------------------------------------


class TipoRefeicao(StrEnum):
    """Na ordem do dia: é a ordem do enum no Postgres, e a das listagens."""

    CAFE_DA_MANHA = "cafe_da_manha"
    LANCHE = "lanche"
    ALMOCO = "almoco"
    JANTA = "janta"


class UnidadeMedida(StrEnum):
    G = "g"
    KG = "kg"
    ML = "ml"
    L = "l"
    UN = "un"
    COLHER_SOPA = "colher_sopa"
    COLHER_CHA = "colher_cha"
    XICARA = "xicara"
    A_GOSTO = "a_gosto"


class MedidaBase(StrEnum):
    """Em que o produto é medido (`produtos.medida_base`)."""

    G = "g"
    ML = "ml"
    UN = "un"
