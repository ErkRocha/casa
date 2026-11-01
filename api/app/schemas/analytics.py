"""Schemas dos painéis de Analytics (fase 4).

Tudo aqui já vem somado, ordenado e com percentual calculado: o front recebe
pronto e desenha (D-14). Nenhum destes números é recalculado no navegador.

Transferência fica fora de todo cálculo de gasto — regra de ouro do analytics.
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class PontoMensal(BaseModel):
    competencia: date
    pessoa_a: Decimal
    pessoa_b: Decimal
    conjunto: Decimal
    total: Decimal
    #: Mês corrente: total parcial, recebe realce na tela.
    em_curso: bool


class EvolucaoMensal(BaseModel):
    pontos: list[PontoMensal]
    #: Média do período, para a linha de referência.
    media_total: Decimal
    #: Rótulos dos dois baldes individuais, na ordem em que aparecem acima.
    #: A tela mostra o nome cadastrado, não "Pessoa A".
    rotulo_a: str
    rotulo_b: str


class LinhaComposicao(BaseModel):
    categoria_id: int
    nome: str
    #: Token de cor da categoria (`categorias.cor`), ex. `cat-3`.
    cor: str | None
    valor: Decimal
    percentual: Decimal
    #: `false` numa folha: não há para onde descer.
    tem_filhos: bool


class CategoriaPai(BaseModel):
    categoria_id: int
    nome: str


class ComposicaoCategoria(BaseModel):
    #: Nulo no nível raiz; preenchido dentro de um drill-down.
    categoria_pai: CategoriaPai | None
    linhas: list[LinhaComposicao]
    total_nivel: Decimal


class LinhaPessoa(BaseModel):
    #: Id da pessoa, ou `conjunto`.
    balde: str
    nome: str
    valor: Decimal
    #: Fatia do total. Os três somam 100, sem sobreposição (D-03).
    percentual: Decimal
    #: Mesmo balde no mês anterior, para o delta.
    valor_anterior: Decimal


class DivisaoPessoas(BaseModel):
    competencia: date
    linhas: list[LinhaPessoa]
    total: Decimal


class LinhaOrcamento(BaseModel):
    categoria_id: int
    nome: str
    realizado: Decimal
    meta: Decimal
    percentual: Decimal
    #: ok | atencao | estourado
    status: str


class ProgressoOrcamento(BaseModel):
    competencia: date
    linhas: list[LinhaOrcamento]
    #: Fração do mês já decorrida (0–1), para o marcador de ritmo. Gastar 60%
    #: da meta no dia 10 é outra história que no dia 28.
    fracao_decorrida: Decimal


class LinhaComparativo(BaseModel):
    chave: str
    label: str
    valor: Decimal
    valor_base: Decimal | None
    base_label: str | None


class Comparativo(BaseModel):
    linhas: list[LinhaComparativo]


class FormaNoBanco(BaseModel):
    forma_pagamento_id: int
    apelido: str
    #: `tipo_pagamento`: credito, debito, pix, boleto, dinheiro, transferencia.
    tipo: str
    #: Cartão de crédito. O resto sai direto da conta (débito, Pix, boleto).
    cartao: bool
    valor: Decimal
    quantidade: int
    #: Despesas desta forma ainda na revisão das importações: não estão no
    #: `valor`, mas vão estar depois de aprovadas.
    revisao_valor: Decimal
    revisao_quantidade: int


class LinhaBanco(BaseModel):
    #: Conta da forma de pagamento. Nulo = lançamento sem forma.
    conta_id: int | None
    nome: str
    total: Decimal
    #: Parte do total no cartão de crédito.
    cartao: Decimal
    #: Parte do total que saiu direto da conta.
    conta: Decimal
    percentual: Decimal
    formas: list[FormaNoBanco]
    revisao_valor: Decimal
    revisao_quantidade: int


class GastoPorBanco(BaseModel):
    """Despesa do período por banco e forma de pagamento.

    Ignora o filtro de forma de pagamento: o painel é o lugar onde se escolhe
    a forma, e sumir com as outras ao clicar numa impediria somar a segunda.
    """

    total: Decimal
    cartao: Decimal
    conta: Decimal
    linhas: list[LinhaBanco]
    revisao_valor: Decimal
    revisao_quantidade: int


class AnalyticsResumo(BaseModel):
    """Os painéis numa tacada — evita um round-trip por painel na abertura."""

    evolucao_mensal: EvolucaoMensal
    composicao_categoria: ComposicaoCategoria
    divisao_pessoas: DivisaoPessoas
    orcamento: ProgressoOrcamento
    comparativo: Comparativo
    por_banco: GastoPorBanco
