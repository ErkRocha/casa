"""Schemas da conferência da lista pela nota (api-notas.md, "Conferência")."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class RespostaDiferenca(BaseModel):
    """A resposta a uma pergunta de quantidade menor."""

    item_lista_id: int
    #: A diferença volta para a lista?
    volta: bool


class ConferenciaConfirmar(BaseModel):
    diferencas: list[RespostaDiferenca] = Field(default_factory=list)


class Confirmado(BaseModel):
    item_lista_id: int
    produto: str
    linhas: list[int]
    estava: Literal["aguardando_nota"]


class Marcado(BaseModel):
    item_lista_id: int
    produto: str
    linhas: list[int]
    aviso: str


class Extra(BaseModel):
    linha: int
    produto_id: int
    produto: str
    variante: str | None
    #: A despensa já acompanha o produto?
    acompanhado: bool
    #: `PUT /despensa/{produto_id}` com `tem`, quando não acompanha.
    acao: Literal["acompanhar_na_despensa"] | None


class ContinuaPendente(BaseModel):
    item_lista_id: int
    produto: str


class AguardandoNota(BaseModel):
    item_lista_id: int
    produto: str
    comprado_em: datetime
    dias: int


class Diferenca(BaseModel):
    item_lista_id: int
    produto: str
    pedido: str
    veio: str
    unidade: str
    pergunta: str
    #: A resposta dada, na confirmação; nulo na prévia.
    volta: bool | None = None


class NaoReconhecido(BaseModel):
    linha: int
    descricao_original: str


class MudancaDespensa(BaseModel):
    produto_id: int
    produto: str
    antes: str
    depois: str


class ConferenciaResposta(BaseModel):
    """A mesma resposta na prévia e na confirmação."""

    nota_id: int
    #: `pendente` (a confirmar), `sem_lista` (nada da lista bate) ou `feita`.
    conferencia: Literal["pendente", "sem_lista", "feita"]
    confirmados: list[Confirmado] = Field(default_factory=list)
    marcados: list[Marcado] = Field(default_factory=list)
    extras: list[Extra] = Field(default_factory=list)
    continuam_pendentes: list[ContinuaPendente] = Field(default_factory=list)
    aguardando_nota: list[AguardandoNota] = Field(default_factory=list)
    diferencas: list[Diferenca] = Field(default_factory=list)
    nao_reconhecidos: list[NaoReconhecido] = Field(default_factory=list)
    despensa: list[MudancaDespensa] = Field(default_factory=list)
