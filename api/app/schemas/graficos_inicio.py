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
