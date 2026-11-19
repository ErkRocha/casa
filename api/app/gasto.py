"""Gasto líquido (D-34): despesa menos estorno.

Um único lugar diz o que entra na soma de gasto e com que sinal, para as
consultas em SQL puro, as montadas com SQLAlchemy e as views não divergirem. O
estorno abate o gasto da categoria e da pessoa em que foi lançado; nunca é
receita.

* SQL puro: `GASTO_TIPOS_SQL` no `WHERE` e `gasto_liquido_sql("t")` dentro do
  `sum(...)`.
* SQLAlchemy: `so_gasto(tipo)` no `where` e `gasto_liquido(tipo, valor)` dentro
  do `func.sum(...)`.

As views `vw_gasto_por_pessoa` e `vw_orcamento_mes` (migration 0009) têm a mesma
expressão escrita à mão no SQL delas.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import case
from sqlalchemy.sql.elements import ColumnElement

from app.enums import TipoTransacao

#: Tipos que entram na soma de gasto, para `WHERE tipo IN ...` em SQL puro.
GASTO_TIPOS_SQL = "('despesa', 'estorno')"


def gasto_liquido_sql(alias: str = "t") -> str:
    """Valor da linha com sinal de gasto: despesa positiva, estorno negativo.

    Só tem sentido sobre linhas já filtradas por `GASTO_TIPOS_SQL`; qualquer
    outro tipo daria nulo.
    """
    return (
        f"(CASE {alias}.tipo WHEN 'despesa' THEN {alias}.valor "
        f"WHEN 'estorno' THEN -{alias}.valor END)"
    )


def so_gasto(tipo: Any) -> ColumnElement[bool]:
    """Filtro de linhas que contam no gasto: despesa e estorno."""
    filtro: ColumnElement[bool] = tipo.in_([TipoTransacao.DESPESA, TipoTransacao.ESTORNO])
    return filtro


def gasto_liquido(tipo: Any, valor: Any) -> ColumnElement[Any]:
    """Valor com sinal de gasto, para dentro de `func.sum(...)`."""
    return case(
        (tipo == TipoTransacao.DESPESA, valor),
        (tipo == TipoTransacao.ESTORNO, -valor),
    )
