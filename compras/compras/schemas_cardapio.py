"""Entrada e saída da API do cardápio (docs/compras/api-cardapio.md).

Quantidade é `Decimal` e sai como texto decimal no JSON, como no resto do
serviço. Resposta de escrita traz a linha inteira.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from compras.enums import (
    EstadoDespensa,
    MedidaBase,
    OrigemItem,
    TipoRefeicao,
    UnidadeMedida,
)
from compras.schemas import Linha, Nome, Observacao, Quantidade

Porcoes = Annotated[Decimal, Field(gt=0, max_digits=4, decimal_places=2)]
Rendimento = Annotated[Decimal, Field(gt=0, max_digits=6, decimal_places=2)]
Rotulo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
ModoPreparo = Annotated[str, StringConstraints(strip_whitespace=True, max_length=10000)]


# --- Pessoas ------------------------------------------------------------------


class PessoaLeitura(Linha):
    nome: str
    porcao_padrao: Decimal
    identidade_id: int | None
    #: O login da tailnet ligado, quando há.
    login: str | None


class PessoaCriar(BaseModel):
    nome: Nome
    porcao_padrao: Porcoes = Decimal(1)
    identidade_id: int | None = None


class PessoaAtualizar(BaseModel):
    """Só o que vier é alterado; `identidade_id: null` desliga o login."""

    nome: Nome | None = None
    porcao_padrao: Porcoes | None = None
    identidade_id: int | None = None


# --- Receitas -----------------------------------------------------------------


class IngredienteEntrada(BaseModel):
    #: Um dos dois. Nome sem produto cria o produto em "Sem seção".
    produto_id: int | None = None
    produto_nome: Nome | None = None
    #: Nula só com `a_gosto`.
    quantidade: Quantidade | None = None
    unidade: UnidadeMedida
    observacao: Observacao | None = None

    @model_validator(mode="after")
    def _coerente(self) -> Self:
        if (self.produto_id is None) == (self.produto_nome is None):
            raise ValueError("informe produto_id ou produto_nome, um dos dois")
        if (self.unidade == UnidadeMedida.A_GOSTO) != (self.quantidade is None):
            raise ValueError("a_gosto não leva quantidade, e as outras unidades levam")
        return self


class ReceitaCorpo(BaseModel):
    nome: Nome
    tipo: TipoRefeicao
    rendimento_porcoes: Rendimento
    tempo_preparo_min: Annotated[int, Field(ge=0)] | None = None
    modo_preparo: ModoPreparo | None = None
    pode_antecipar: bool = False
    dura_dias: Annotated[int, Field(ge=1)] | None = None
    pode_congelar: bool = False
    ingredientes: list[IngredienteEntrada] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validade(self) -> Self:
        if self.pode_antecipar and self.dura_dias is None:
            raise ValueError("pode_antecipar exige dura_dias")
        return self


class ReceitaCriar(ReceitaCorpo):
    id_cliente: uuid.UUID


class IngredienteLeitura(Linha):
    produto_id: int
    produto_nome: str
    quantidade: Decimal | None
    unidade: UnidadeMedida
    observacao: str | None
    ordem: int
    #: Chega à lista com quantidade? Falso: falta `medida_base` ou `medida_por_unidade`.
    converte: bool


class ReceitaResumo(Linha):
    nome: str
    tipo: TipoRefeicao
    rendimento_porcoes: Decimal
    tempo_preparo_min: int | None
    pode_antecipar: bool
    dura_dias: int | None
    pode_congelar: bool
    id_cliente: uuid.UUID | None
    #: "Conferi, está certa": as quantidades foram conferidas por alguém.
    quantidades_revisadas: bool
    revisadas_por: str | None
    revisadas_em: datetime | None


class ReceitaDetalhe(ReceitaResumo):
    modo_preparo: str | None
    ingredientes: list[IngredienteLeitura]


class ReceitasPagina(BaseModel):
    items: list[ReceitaResumo]
    total: int
    limite: int
    offset: int


# --- Produtos -----------------------------------------------------------------


class ProdutoSemMedida(BaseModel):
    id: int
    nome: str
    secao_nome: str
    unidade_padrao: str | None
    medida_base: MedidaBase | None
    medida_por_unidade: Decimal | None
    #: Por que o uso na receita não converte.
    motivos: list[str]
    receitas: list[str]


# --- Semanas e refeições -----------------------------------------------------


class SemanaCriar(BaseModel):
    inicio: date
    observacao: Observacao | None = None


class SemanaCopiar(BaseModel):
    destino: date


class PessoaPorcao(BaseModel):
    pessoa_id: int
    #: Nulo: a `porcao_padrao` da pessoa.
    porcoes: Porcoes | None = None


class RefeicaoCriar(BaseModel):
    dia: date
    tipo: TipoRefeicao
    receita_id: int | None = None
    observacao: Observacao | None = None
    #: Sem isto, todas as pessoas vivas, com a porção padrão.
    pessoas: list[PessoaPorcao] | None = None

    @model_validator(mode="after")
    def _algo_a_comer(self) -> Self:
        if self.receita_id is None and not (self.observacao or "").strip():
            raise ValueError("informe receita_id ou observacao")
        return self


class RefeicaoAtualizar(BaseModel):
    """Só o que vier é alterado; `null` limpa `receita_id` e `observacao`."""

    dia: date | None = None
    tipo: TipoRefeicao | None = None
    receita_id: int | None = None
    observacao: Observacao | None = None
    ordem: Annotated[int, Field(ge=0)] | None = None


class PessoaNaRefeicao(BaseModel):
    pessoa_id: int
    nome: str
    #: A porção efetiva (o ajuste, ou a padrão da pessoa).
    porcoes: Decimal
    ajustada: bool


class IngredienteDaSemana(BaseModel):
    produto_id: int
    produto_nome: str
    quantidade: Decimal | None
    unidade: UnidadeMedida
    observacao: str | None


class ReceitaNaRefeicao(BaseModel):
    id: int
    nome: str
    rendimento_porcoes: Decimal
    tempo_preparo_min: int | None
    apagada: bool = False
    #: Só com `?ingredientes=true`; para semana passada, os vivos no fim dela.
    ingredientes: list[IngredienteDaSemana] | None = None


class RefeicaoLeitura(Linha):
    semana_id: int
    dia: date
    tipo: TipoRefeicao
    receita: ReceitaNaRefeicao | None
    observacao: str | None
    ordem: int
    pessoas: list[PessoaNaRefeicao]
    #: Soma das porções efetivas de quem come.
    porcoes: Decimal
    #: porcoes / rendimento da receita; nulo sem receita.
    fator: Decimal | None


class SessaoLeitura(Linha):
    semana_id: int
    data: date
    rotulo: str | None


class SessaoCriar(BaseModel):
    data: date
    rotulo: Rotulo | None = None


class SessaoAtualizar(BaseModel):
    data: date | None = None
    rotulo: Rotulo | None = None


class DiaLeitura(BaseModel):
    dia: date
    refeicoes: list[RefeicaoLeitura]


class SemanaResumo(Linha):
    inicio: date
    observacao: str | None
    passada: bool
    refeicoes: int


class SemanasPagina(BaseModel):
    items: list[SemanaResumo]
    total: int
    limite: int
    offset: int


class SemanaDetalhe(Linha):
    inicio: date
    observacao: str | None
    passada: bool
    dias: list[DiaLeitura]
    sessoes: list[SessaoLeitura]


class AvisoRefeicao(BaseModel):
    refeicao_id: int | None = None
    texto: str


class SemanaCopiada(SemanaDetalhe):
    avisos: list[AvisoRefeicao]


# --- Roteiro --------------------------------------------------------------------


class ReceitaNoRoteiro(BaseModel):
    id: int
    nome: str
    tempo_preparo_min: int | None


class DestinoPasso(BaseModel):
    refeicao_id: int
    dia: date
    tipo: TipoRefeicao
    porcoes: Decimal
    onde: Literal["geladeira", "congelador"]
    #: Só no congelador: o dia anterior à refeição.
    descongelar_em: date | None = None


class PassoFeitoPor(BaseModel):
    por: str
    em: datetime


class Passo(BaseModel):
    receita: ReceitaNoRoteiro
    #: Soma das porções de todas as refeições do passo.
    porcoes: Decimal
    #: Quantas receitas fazer (1,5 é 1,5): porcoes / rendimento.
    fator: Decimal
    porcoes_geladeira: Decimal
    porcoes_congelador: Decimal
    destinos: list[DestinoPasso]
    avisos: list[str]
    #: Quem marcou o passo como feito e quando; nulo se ainda não foi.
    feito: PassoFeitoPor | None = None


class SessaoNoRoteiro(BaseModel):
    sessao_id: int
    data: date
    rotulo: str | None
    passos: list[Passo]


class NoDia(BaseModel):
    refeicao_id: int
    dia: date
    tipo: TipoRefeicao
    receita: ReceitaNoRoteiro


class Roteiro(BaseModel):
    sessoes: list[SessaoNoRoteiro]
    no_dia: list[NoDia]
    avisos: list[AvisoRefeicao]


# --- Lista pelo cardápio -----------------------------------------------------


class ListaCriado(BaseModel):
    produto: str
    #: Nulo na prévia: o item ainda não existe.
    item_id: int | None
    quantidade: Decimal | None
    unidade: str | None
    de: list[str]


class ListaAjustado(BaseModel):
    produto: str
    item_id: int
    antes: Decimal | None
    depois: Decimal | None
    unidade: str | None
    origem_item: OrigemItem
    #: A semana não pede mais: o item saiu da lista (era só do cardápio).
    removido: bool = False
    pedido: Decimal | None
    de: list[str]


class ListaSemMudanca(BaseModel):
    produto: str
    item_id: int | None
    pedido: Decimal | None
    unidade: str | None
    de: list[str]


class ListaConfira(BaseModel):
    produto: str
    estado_despensa: EstadoDespensa
    pedido: Decimal | None
    unidade: str | None
    texto: str
    de: list[str]


class ListaAviso(BaseModel):
    produto: str | None
    texto: str


class ListaCardapio(BaseModel):
    criados: list[ListaCriado]
    ajustados: list[ListaAjustado]
    sem_mudanca: list[ListaSemMudanca]
    confira: list[ListaConfira]
    avisos: list[ListaAviso]
