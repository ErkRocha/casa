"""Schemas dos gráficos do Início (D-28).

Tudo pronto para desenhar: acumulados, totais e a linha da soma vêm do banco.
Dinheiro sai como `Decimal` (texto no JSON).
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

#: Jeito de pagar de uma série. `soma` é só a linha da soma das escolhidas.
TipoSerie = Literal["cartao", "pix", "debito", "boleto", "outros", "soma"]


class PontoGasto(BaseModel):
    data: date
    #: Gasto desde o início da janela até este dia, com as pendentes. Nunca desce.
    acumulado: Decimal
    #: Parte de `acumulado` que ainda é pendente no banco.
    pendente_acumulado: Decimal
    #: Houve compra pendente neste dia.
    tem_pendente: bool


class SerieGasto(BaseModel):
    #: Estável: `cartao:<forma_pagamento_id>`, `pix`, `debito`, `boleto`,
    #: `outros` (e `soma` na linha da soma).
    chave: str
    rotulo: str
    tipo: TipoSerie
    #: Só o cartão.
    forma_pagamento_id: int | None
    #: Nome do token de cor do front: `serie-1`..`serie-4` por cartão, ou
    #: `serie-pix`, `serie-debito`, `serie-boleto`, `serie-outros`, `serie-soma`.
    cor: str
    visivel: bool
    #: Acumulado no fim da janela.
    total: Decimal
    #: Parte de `total` que é pendente.
    pendente: Decimal
    #: Um por dia da janela, do primeiro até hoje.
    pontos: list[PontoGasto]


class PessoaConectada(BaseModel):
    id: int
    nome: str


class GastosJanela(BaseModel):
    """Os últimos 30 dias até hoje, uma linha acumulada por forma de pagar."""

    inicio: date
    hoje: date
    #: Todas as séries com gasto na janela; `visivel` diz as escolhidas.
    series: list[SerieGasto]
    #: Soma diária acumulada das visíveis; só com `somar` e ao menos uma visível.
    soma: SerieGasto | None
    #: Das séries visíveis, lançado mais pendente.
    total: Decimal
    pendente: Decimal
    #: Titulares de contas ligadas à Pluggy (as opções do filtro de pessoa).
    pessoas_conectadas: list[PessoaConectada]
    #: Eco do filtro pedido.
    pessoa_id: int | None


#: De onde veio cada data de um ciclo de fatura. `derivada`: sem fechamento
#: anterior conhecido, a abertura sai de um mês antes do fechamento (ou o
#: vencimento sai de 10 dias depois do fechamento).
OrigemData = Literal["pluggy_fatura", "pluggy_conta", "cadastro", "derivada"]


class PontoCiclo(BaseModel):
    data: date
    #: Compras do ciclo até este dia (nunca passa do fechamento nem de hoje).
    #: No dia do pagamento há dois pontos: o valor antes e depois zero.
    valor: Decimal
    #: Dia depois de hoje: o que ainda vai acontecer.
    tracejado: bool


class CicloFatura(BaseModel):
    #: Estável: `ciclo:<forma_pagamento_id>:<AAAA-MM-DD do fechamento>`.
    chave: str
    forma_pagamento_id: int
    cartao: str
    #: Token de cor do cartão, o mesmo do gráfico de gastos.
    cor: str
    #: Primeiro dia do mês do vencimento.
    mes_fatura: date
    abertura: date
    fechamento: date
    vencimento: date
    #: Dia do pagamento identificado (D-22), se houver.
    pago_em: date | None
    #: Compras de `abertura` até o fechamento (ou hoje), com as pendentes.
    valor: Decimal
    #: Parte de `valor` que ainda é pendente.
    pendente: Decimal
    #: Ciclo de maior fechamento do cartão; os outros são anteriores.
    atual: bool
    #: `aberta` (ainda não fechou), `fechada` (sem pagamento) ou `paga`.
    situacao: Literal["aberta", "fechada", "paga"]
    origem_abertura: OrigemData
    origem_fechamento: OrigemData
    origem_vencimento: OrigemData
    origem_pagamento: Literal["identificado"] | None
    pontos: list[PontoCiclo]


class FaturasCiclos(BaseModel):
    """Uma linha por ciclo de fatura, dos últimos 30 dias até o último
    vencimento dos próximos 15."""

    inicio: date
    hoje: date
    fim: date
    #: Por cartão e fechamento.
    ciclos: list[CicloFatura]
