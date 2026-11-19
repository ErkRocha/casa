"""Média mensal de gastos: uma conta só para Análises e relatório.

**Mês sem nenhum lançamento fica fora.** Num mês sem nada lançado (antes do
primeiro mês com dados, ou um mês ainda não importado), zero quer dizer
"não importei", não "não gastei". Dividir pela janela inteira daria, com dois
meses de histórico numa janela de doze, uma média seis vezes menor. Já o mês
que tem lançamentos mas nenhuma despesa (só receita, só transferência) entra
como zero: ali o zero é de verdade.

"Ter lançamento" é da casa, não da pessoa filtrada: se a casa tem dados no
mês e a pessoa não gastou, o zero dela conta.

A média é calculada no banco (regra 7) e serve à sessão normal e à read-only
do relatório (só lê `vw_transacoes_completa`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.gasto import GASTO_TIPOS_SQL, gasto_liquido_sql

#: `caixa` = competência (D-02, D-27); `compra` = mês da data da compra (D-31).
BaseMes = Literal["caixa", "compra"]

#: O mês de cada transação, por base. Dicionário fechado: o SQL nunca recebe
#: texto do usuário.
MES_POR_BASE: dict[str, str] = {
    "caixa": "t.competencia",
    "compra": "date_trunc('month', t.data)::date",
}

_MEDIA = f"""
    WITH meses AS (
      SELECT DISTINCT __MES__ AS mes
      FROM vw_transacoes_completa t
      WHERE __MES__ BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
    ),
    despesas AS (
      SELECT __MES__ AS mes, sum({gasto_liquido_sql("t")}) AS total
      FROM vw_transacoes_completa t
      WHERE t.tipo IN {GASTO_TIPOS_SQL}
        AND __MES__ BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
        AND (CAST(:pessoa AS text) IS NULL
             OR coalesce(CAST(t.pessoa_id AS text), 'conjunto') = CAST(:pessoa AS text))
      GROUP BY 1
    )
    SELECT count(*) AS meses, round(avg(coalesce(d.total, 0)), 2) AS media
    FROM meses m
    LEFT JOIN despesas d ON d.mes = m.mes
"""


@dataclass(frozen=True)
class MediaMensal:
    #: Nula quando nenhum mês da janela tem lançamento.
    media: Decimal | None
    #: Quantos meses entraram na média.
    meses: int


def media_mensal_despesas(
    sessao: Session,
    de: date,
    ate: date,
    *,
    base: BaseMes = "caixa",
    pessoa: str | None = None,
) -> MediaMensal:
    """Média das despesas por mês de `de` a `ate` (inclusive, dia 1 de cada).

    `pessoa` é o id em texto ou `conjunto`; nulo para a casa inteira.
    """
    linha = sessao.execute(
        text(_MEDIA.replace("__MES__", MES_POR_BASE[base])),
        {"de": de, "ate": ate, "pessoa": pessoa},
    ).one()
    meses = int(linha.meses)
    return MediaMensal(media=Decimal(linha.media) if meses else None, meses=meses)
