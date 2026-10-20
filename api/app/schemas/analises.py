"""Schemas da tela Análises (D-22).

Tudo somado, dividido e arredondado no banco; a tela só desenha (D-14).
Transferência fica fora de todo número (D-05).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.inicio import FaixaOrcamento

#: Este mês, os últimos 3 ou os últimos 12, sempre terminando no mês corrente.
Periodo = Literal["mes", "3m", "12m"]


class MesAnalise(BaseModel):
    competencia: date
    despesas: Decimal
    receitas: Decimal
    #: O mês corrente: valores parciais, até hoje.
    em_curso: bool


class SubcategoriaAnalise(BaseModel):
    categoria_id: int
    nome: str
    valor: Decimal


class CategoriaAnalise(BaseModel):
    #: Nulo = sem categoria.
    categoria_id: int | None
    nome: str
    valor: Decimal
    subcategorias: list[SubcategoriaAnalise]


class MudancaCategoria(BaseModel):
    categoria_id: int
    nome: str
    #: O gasto no mês de referência.
    valor: Decimal
    #: A média mensal dos meses de comparação.
    media: Decimal
    #: Variação percentual inteira contra a média (+42, −13).
    variacao: int


class Mudancas(BaseModel):
    #: O último mês fechado do período.
    referencia: date
    #: Quantos meses fechados antes dele entram na média.
    meses_base: int
    #: Maior diferença em reais primeiro: +400% sobre R$ 5 não é notícia.
    linhas: list[MudancaCategoria]


class LinhaOrcamentoAnalise(BaseModel):
    categoria_id: int
    nome: str
    gasto: Decimal
    meta: Decimal
    percentual: int
    #: Faixas do README: até 90%, de 90% a 100%, acima de 100%.
    faixa: FaixaOrcamento
    #: Largura da barra, limitada a 100.
    largura: int
    #: Quanto passou da meta, quando passou.
    excesso: Decimal | None


class Analises(BaseModel):
    periodo: Periodo
    #: Primeiro e último mês do período (o último é o corrente).
    inicio: date
    fim: date
    dia_referencia: int
    dias_no_mes: int
    meses: list[MesAnalise]
    #: Meses fechados do período: todos menos o corrente.
    meses_fechados: int
    #: `media_mensal`: categorias pela média dos meses fechados. `mes`: o
    #: período é só o mês corrente, e os valores são dele.
    base_categorias: Literal["media_mensal", "mes"]
    #: Média de despesas dos meses fechados; nula quando não há.
    media_mensal: Decimal | None
    #: O mês de maior despesa do período, se algum teve despesa.
    mes_mais_caro: MesAnalise | None
    categorias: list[CategoriaAnalise]
    #: Nulo quando o período não tem mês fechado para comparar ("este mês").
    mudancas: Mudancas | None
    #: Metas do mês corrente. Com pessoa escolhida, o gasto é o dela contra a
    #: meta da casa.
    orcamento: list[LinhaOrcamentoAnalise]
