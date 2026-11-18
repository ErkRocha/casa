"""Schemas da tela Início (D-24, D-31).

Tudo pronto para desenhar: somas, diferenças, percentuais e a previsão vêm
calculados do banco. Dinheiro sai como `Decimal` (texto no JSON).

**Duas bases, sem mistura (D-31).** O topo de `Inicio` (gasto, comparação,
receitas, sobra, orçamento, pessoas, categorias e avisos de orçamento) é pela
**data da compra**. O que sai da conta (D-27) fica todo em `caixa`.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

#: Faixa de orçamento: regra e limiares em `app.faixas_orcamento`.
from app.faixas_orcamento import FaixaOrcamento

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


class Orcamento(BaseModel):
    total: Decimal
    #: Gasto até o dia de referência sobre a meta total, inteiro.
    percentual_usado: int
    faixa: FaixaOrcamento


class Previsao(BaseModel):
    """Fechamento do caixa do mês no ritmo atual (só no mês corrente).

    `comprometido` é o que já está decidido e não se repete, por isso fica
    fora do ritmo: as faturas de cartão que saem da conta no mês (pagas ou
    não, D-27) mais as despesas sem degrau com data anterior ao mês (cartão
    sem datas conhecidas). O resto — Pix, débito, boleto — é projetado em
    linha reta até o fim do mês.
    """

    valor: Decimal
    comprometido: Decimal


class LinhaPessoaInicio(BaseModel):
    #: Id da pessoa ou `conjunto`.
    balde: str
    nome: str
    valor: Decimal
    percentual: int


class LinhaCategoriaInicio(BaseModel):
    #: `outras` junta as categorias além das maiores, para as linhas somarem
    #: o gasto do mês (D-31).
    tipo: Literal["categoria", "outras", "sem_categoria"]
    categoria_id: int | None
    nome: str
    valor: Decimal
    #: Parte do gasto do mês.
    percentual: int
    #: Largura da barra relativa à maior categoria (0–100).
    largura: int


class AvisoOrcamento(BaseModel):
    """Categoria perto ou acima da meta, pela data da compra (D-31)."""

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


class CaixaMes(BaseModel):
    """O que sai da conta no mês (D-27): bloco secundário do Início (D-31).

    Base própria: o total é o da competência (D-02), com a fatura de cada
    cartão no dia em que sai da conta. Nada daqui entra no topo.
    """

    #: O que já saiu da conta no dia de referência (`serie`); zero sem série.
    saiu_da_conta: Decimal
    #: Faturas do mês ainda "a pagar".
    a_pagar: Decimal
    previsao: Previsao | None
    #: Um ponto por dia do mês (vazio no mês futuro).
    serie: list[PontoAcumulado]
    #: Degraus de fatura do mês, em ordem de dia (D-27).
    faturas: list[FaturaMes]


class Inicio(BaseModel):
    competencia: date
    situacao: SituacaoMes
    dias_no_mes: int
    #: Até que dia os números valem: hoje no mês corrente, o último dia num
    #: mês fechado, zero num mês futuro.
    dia_referencia: int
    #: Algum lançamento (de qualquer tipo) com data no mês ou competência nele.
    tem_dados: bool

    #: Despesas pela data da compra no mês, até o dia de referência (sem
    #: pendentes, D-28). `pessoas` e `categorias` somam este valor.
    gasto: Decimal
    #: O mesmo no mês anterior, até o mesmo dia.
    gasto_mes_anterior: Decimal
    #: `gasto - gasto_mes_anterior` (negativo = gastou menos).
    diferenca_mes_anterior: Decimal
    #: Receitas pela data, até o dia de referência.
    receitas: Decimal
    #: `receitas - gasto`.
    sobra: Decimal

    #: Metas do mês contra `gasto`.
    orcamento: Orcamento | None
    pessoas: list[LinhaPessoaInicio]
    categorias: list[LinhaCategoriaInicio]
    avisos: list[AvisoOrcamento | AvisoReajuste]

    #: O que sai da conta, na base do caixa (D-27).
    caixa: CaixaMes
    #: Faturas abertas hoje; não dependem do mês pedido.
    faturas_abertas: list[FaturaAberta]
