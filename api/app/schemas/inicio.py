"""Schemas da tela Início (D-22).

Tudo pronto para desenhar: somas, diferenças, percentuais e a previsão vêm
calculados do banco. Dinheiro sai como `Decimal` (texto no JSON).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

#: Faixa de orçamento do README do desenho: até 90% azul, 90–100% âmbar,
#: acima de 100% estourado.
FaixaOrcamento = Literal["ok", "perto", "estourado"]

#: Mês corrente, já fechado ou ainda por vir — cada um tem estado próprio.
SituacaoMes = Literal["corrente", "passado", "futuro"]


class PontoAcumulado(BaseModel):
    dia: int
    #: Despesa somada do dia 1 até este dia.
    acumulado: Decimal


class Orcamento(BaseModel):
    total: Decimal
    #: Gasto até o dia de referência sobre a meta total, inteiro.
    percentual_usado: int
    faixa: FaixaOrcamento


class Previsao(BaseModel):
    """Fechamento do mês no ritmo atual (só no mês corrente).

    `comprometido` é o que entrou no mês com data anterior a ele (compras de
    cartão da fatura que vence agora): já está decidido e não se repete, por
    isso fica fora do ritmo. O resto é projetado em linha reta até o fim do
    mês.
    """

    valor: Decimal
    comprometido: Decimal
    #: Previsão menos o orçamento total; nulo sem orçamento.
    diferenca_orcamento: Decimal | None


class LinhaPessoaInicio(BaseModel):
    #: Id da pessoa ou `conjunto`.
    balde: str
    nome: str
    valor: Decimal
    percentual: int


class LinhaCategoriaInicio(BaseModel):
    categoria_id: int | None
    nome: str
    valor: Decimal
    #: Parte do gasto do mês.
    percentual: int
    #: Largura da barra relativa à maior categoria (0–100).
    largura: int


class AvisoOrcamento(BaseModel):
    tipo: Literal["orcamento"] = "orcamento"
    categoria: str
    percentual: Decimal
    realizado: Decimal
    meta: Decimal
    #: "atencao" | "estourado", das detecções do relatório mensal.
    situacao: str
    #: Dias até o fim do mês corrente; nulo em mês fechado.
    dias_restantes: int | None


class AvisoReajuste(BaseModel):
    tipo: Literal["reajuste"] = "reajuste"
    descricao: str
    valor_anterior: Decimal
    valor_atual: Decimal


class Inicio(BaseModel):
    competencia: date
    situacao: SituacaoMes
    dias_no_mes: int
    #: Até que dia os números valem: hoje no mês corrente, o último dia num
    #: mês fechado, zero num mês futuro.
    dia_referencia: int
    #: Algum lançamento (de qualquer tipo) com esta competência.
    tem_dados: bool

    gasto: Decimal
    #: Gasto do mês anterior até o mesmo dia.
    gasto_mes_anterior: Decimal
    #: `gasto - gasto_mes_anterior` (negativo = gastou menos).
    diferenca_mes_anterior: Decimal
    receitas: Decimal
    #: `receitas - gasto`.
    sobra: Decimal

    orcamento: Orcamento | None
    previsao: Previsao | None
    serie: list[PontoAcumulado]
    pessoas: list[LinhaPessoaInicio]
    categorias: list[LinhaCategoriaInicio]
    avisos: list[AvisoOrcamento | AvisoReajuste]
