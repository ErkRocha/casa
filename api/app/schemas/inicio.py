"""Schemas da tela Início (D-24).

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


#: De onde vieram as datas de uma fatura (D-27): fatura da Pluggy, conta de
#: crédito da Pluggy ou dia cadastrado na forma de pagamento.
OrigemDatas = Literal["pluggy_fatura", "pluggy_conta", "cadastro"]


class PontoAcumulado(BaseModel):
    """Um dia do gráfico "o que sai da conta" (D-27).

    O total do mês é o da competência (D-02); aqui só muda o dia em que cada
    despesa conta. Cartão com datas conhecidas vira um degrau único.
    """

    dia: int
    #: O que já saiu da conta até este dia: despesas que não são fatura de
    #: cartão (até hoje, no mês corrente) mais as faturas já pagas.
    acumulado: Decimal
    #: `acumulado` mais o que ainda vai sair até este dia: faturas a pagar e,
    #: no mês corrente, despesas com data futura. No último dia é o total do
    #: mês (competência).
    com_a_pagar: Decimal


class FaturaMes(BaseModel):
    """Degrau de um cartão no mês: a soma das compras da competência."""

    forma_pagamento_id: int
    cartao: str
    #: Soma das compras do cartão na competência (não o total da Pluggy).
    valor: Decimal
    #: Dia do mês em que a fatura sai da conta: o do pagamento ou o do vencimento.
    dia: int
    situacao: Literal["paga", "a_pagar"]
    vencimento: date
    #: Data do pagamento identificado (D-22); nulo enquanto "a pagar".
    pago_em: date | None
    origem_vencimento: OrigemDatas


class PontoEvolucao(BaseModel):
    data: date
    #: Compras do cartão desde o último fechamento, até esta data.
    acumulado: Decimal


class FaturaAberta(BaseModel):
    """Fatura em aberto de um cartão ativo, somada pela data da compra."""

    forma_pagamento_id: int
    cartao: str
    #: Compras com data depois de `desde` e até hoje, lançadas mais as
    #: pendentes (D-28).
    valor: Decimal
    #: Parte de `valor` que ainda é pendente (só exibição, D-28).
    pendente: Decimal
    #: Último fechamento.
    desde: date
    #: Próximo fechamento.
    fecha: date
    #: Vencimento previsto; nulo se não há como estimar.
    vence: date | None
    #: A origem mais fraca entre as do fechamento e do vencimento.
    origem_datas: OrigemDatas
    #: Um ponto por dia, de `desde` + 1 até hoje.
    evolucao: list[PontoEvolucao]


class DiaJanela(BaseModel):
    """Um dia da janela dos últimos 30 dias mais a faixa "a pagar" (D-27/D-28)."""

    data: date
    #: Despesas lançadas em cartão de crédito, pela data da compra.
    cartao: Decimal
    #: Compras pendentes do cartão (D-28), pela data da compra.
    cartao_pendente: Decimal
    #: Pix, débito, boleto e o resto, pela data.
    conta: Decimal
    #: `cartao + cartao_pendente + conta`.
    total: Decimal
    #: Dia depois de hoje (faixa dos vencimentos): os valores são zero.
    a_pagar: bool


class PagamentoJanela(BaseModel):
    """Pagamento de fatura que saiu da conta (D-22), só para marcar no gráfico."""

    data: date
    valor: Decimal
    #: Cartão pago, se a conta paga exatamente um cartão ativo.
    cartao: str | None
    forma_pagamento_id: int | None


class VencimentoJanela(BaseModel):
    """Fatura a pagar que vence nos próximos dias."""

    data: date
    forma_pagamento_id: int
    cartao: str
    #: Soma das compras lançadas da fatura (degrau da D-27).
    valor: Decimal
    #: Compras pendentes previstas para esta fatura (D-28); não entram em `valor`.
    pendente: Decimal
    origem_vencimento: OrigemDatas


class Janela(BaseModel):
    """Os últimos 30 dias até hoje e os vencimentos dos próximos 15.

    Não depende do mês escolhido. A compra no cartão conta no dia da compra e
    o pagamento da fatura nunca entra nas barras (já está nas compras).
    """

    inicio: date
    hoje: date
    #: Último vencimento mostrado, ou `hoje` se não há nenhum.
    fim: date
    dias: list[DiaJanela]
    pagamentos: list[PagamentoJanela]
    vencimentos: list[VencimentoJanela]
    #: `cartao + conta` de `inicio` até hoje.
    total: Decimal
    #: Cartão no período, lançado mais pendente.
    cartao: Decimal
    cartao_pendente: Decimal
    conta: Decimal


class Orcamento(BaseModel):
    total: Decimal
    #: Gasto até o dia de referência sobre a meta total, inteiro.
    percentual_usado: int
    faixa: FaixaOrcamento


class Previsao(BaseModel):
    """Fechamento do mês no ritmo atual (só no mês corrente).

    `comprometido` é o que já está decidido e não se repete, por isso fica
    fora do ritmo: as faturas de cartão que saem da conta no mês (pagas ou
    não, D-27) mais as despesas sem degrau com data anterior ao mês (cartão
    sem datas conhecidas). O resto — Pix, débito, boleto — é projetado em
    linha reta até o fim do mês.
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

    #: Despesas pela data da compra no mês, até o dia de referência (sem
    #: pendentes). Difere de `gasto`, que é por competência.
    gasto_compra: Decimal
    #: O mesmo no mês anterior, até o mesmo dia.
    gasto_compra_mes_anterior: Decimal
    diferenca_compra_mes_anterior: Decimal
    #: O que já saiu da conta no dia de referência (`serie`); zero sem série.
    saiu_da_conta: Decimal
    #: Faturas do mês ainda "a pagar".
    a_pagar_mes: Decimal
    janela: Janela

    orcamento: Orcamento | None
    previsao: Previsao | None
    #: Um ponto por dia do mês (vazio no mês futuro).
    serie: list[PontoAcumulado]
    #: Degraus de fatura do mês, em ordem de dia (D-27).
    faturas: list[FaturaMes]
    #: Faturas abertas hoje; não dependem do mês pedido.
    faturas_abertas: list[FaturaAberta]
    pessoas: list[LinhaPessoaInicio]
    categorias: list[LinhaCategoriaInicio]
    avisos: list[AvisoOrcamento | AvisoReajuste]
