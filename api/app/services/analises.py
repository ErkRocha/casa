"""A tela Análises (D-22): o período, a pessoa e os quatro blocos.

Toda soma, média, variação e faixa sai do SQL abaixo; o Python escolhe os
meses e monta a resposta (regras 7 e 10, D-14). Transferência fica fora de
tudo (D-05).

**Média é dos meses fechados.** O mês corrente está pela metade: entrar na
média puxaria tudo para baixo. Ele aparece no gráfico, marcado como parcial,
e é o mês do orçamento. No período "este mês", que não tem mês fechado, as
categorias mostram o próprio mês e não há comparação com a média.

**Orçamento pela categoria raiz**, a mesma regra de `vw_orcamento_mes` (o
gasto da raiz soma as subcategorias), para Análises, Início e relatório
dizerem o mesmo. A pessoa, quando escolhida, filtra o gasto; a meta é da
casa.
"""

from __future__ import annotations

import calendar
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import Row, text
from sqlalchemy.orm import Session

from app.schemas.analises import (
    Analises,
    CategoriaAnalise,
    LinhaOrcamentoAnalise,
    MesAnalise,
    MudancaCategoria,
    Mudancas,
    Periodo,
    SubcategoriaAnalise,
)
from app.services.cadastros import primeiro_dia_do_mes

#: Quantos meses cada período cobre, terminando no corrente.
MESES_DO_PERIODO: dict[str, int] = {"mes": 1, "3m": 3, "12m": 12}
#: Quantas categorias "o que mais mudou" mostra.
LIMITE_MUDANCAS = 5
SEM_CATEGORIA = "Sem categoria"

#: `:pessoa` é o id em texto, `conjunto`, ou nulo para todos.
_PESSOA = """
    AND (CAST(:pessoa AS text) IS NULL
         OR coalesce(CAST(t.pessoa_id AS text), 'conjunto') = CAST(:pessoa AS text))
"""

_MENSAL = f"""
    WITH meses AS (
      SELECT generate_series(CAST(:inicio AS date), CAST(:fim AS date), interval '1 month')::date
        AS competencia
    ),
    somas AS (
      SELECT
        t.competencia,
        sum(t.valor) FILTER (WHERE t.tipo = 'despesa') AS despesas,
        sum(t.valor) FILTER (WHERE t.tipo = 'receita') AS receitas
      FROM vw_transacoes_completa t
      WHERE t.tipo <> 'transferencia'
        AND t.competencia BETWEEN CAST(:inicio AS date) AND CAST(:fim AS date)
        {_PESSOA}
      GROUP BY t.competencia
    ),
    mensal AS (
      SELECT
        m.competencia,
        coalesce(s.despesas, 0) AS despesas,
        coalesce(s.receitas, 0) AS receitas,
        m.competencia = CAST(:fim AS date) AS em_curso
      FROM meses m
      LEFT JOIN somas s ON s.competencia = m.competencia
    )
"""

_MESES = f"""
    {_MENSAL}
    SELECT competencia, despesas, receitas, em_curso FROM mensal ORDER BY competencia
"""

_RESUMO_MESES = f"""
    {_MENSAL},
    mais_caro AS (
      SELECT competencia, despesas, receitas, em_curso
      FROM mensal WHERE despesas > 0
      ORDER BY despesas DESC, competencia DESC
      LIMIT 1
    )
    SELECT
      (SELECT round(avg(despesas), 2) FROM mensal WHERE NOT em_curso) AS media_mensal,
      c.competencia, c.despesas, c.receitas, c.em_curso
    FROM (SELECT 1) AS um
    LEFT JOIN mais_caro c ON true
"""

#: Por raiz e por folha, divididos pelo número de meses (mês sem gasto conta
#: como zero na média).
_CATEGORIAS = f"""
    WITH base AS (
      SELECT
        t.categoria_raiz_id AS raiz_id,
        coalesce(t.categoria_pai_nome, t.categoria_nome) AS raiz_nome,
        t.categoria_id,
        t.categoria_nome,
        t.categoria_pai_id,
        t.valor
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa'
        AND t.competencia BETWEEN CAST(:de AS date) AND CAST(:ate AS date)
        {_PESSOA}
    ),
    raizes AS (
      SELECT raiz_id, raiz_nome, round(sum(valor) / :n, 2) AS valor
      FROM base GROUP BY raiz_id, raiz_nome
    ),
    folhas AS (
      SELECT raiz_id, categoria_id, categoria_nome, round(sum(valor) / :n, 2) AS valor
      FROM base WHERE categoria_pai_id IS NOT NULL
      GROUP BY raiz_id, categoria_id, categoria_nome
    )
    SELECT
      r.raiz_id,
      coalesce(r.raiz_nome, CAST(:sem_categoria AS text)) AS raiz_nome,
      r.valor AS raiz_valor,
      f.categoria_id,
      f.categoria_nome,
      f.valor AS folha_valor
    FROM raizes r
    LEFT JOIN folhas f ON f.raiz_id = r.raiz_id
    ORDER BY r.raiz_id IS NULL, r.valor DESC, r.raiz_id, f.valor DESC, f.categoria_id
"""

#: O mês de referência contra a média dos meses de base, por folha.
_MUDANCAS = f"""
    WITH base AS (
      SELECT t.categoria_id, t.categoria_nome, t.competencia, t.valor
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa'
        AND t.categoria_id IS NOT NULL
        AND t.competencia BETWEEN CAST(:base_de AS date) AND CAST(:ref AS date)
        {_PESSOA}
    ),
    por_categoria AS (
      SELECT
        categoria_id,
        categoria_nome,
        coalesce(sum(valor) FILTER (WHERE competencia = CAST(:ref AS date)), 0) AS valor,
        coalesce(sum(valor) FILTER (WHERE competencia < CAST(:ref AS date)), 0) / :n_base AS media
      FROM base
      GROUP BY categoria_id, categoria_nome
    )
    SELECT
      categoria_id,
      categoria_nome AS nome,
      valor,
      round(media, 2) AS media,
      round((valor - media) / media * 100)::int AS variacao
    FROM por_categoria
    WHERE media > 0
    ORDER BY abs(valor - media) DESC, categoria_id
    LIMIT :limite
"""

_ORCAMENTO = f"""
    WITH metas AS (
      SELECT o.categoria_id, c.nome, o.valor_meta
      FROM orcamentos o
      JOIN categorias c ON c.id = o.categoria_id
      WHERE o.competencia = CAST(:fim AS date) AND o.deleted_em IS NULL AND o.valor_meta > 0
    ),
    gastos AS (
      SELECT t.categoria_raiz_id AS categoria_id, sum(t.valor) AS gasto
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa' AND t.competencia = CAST(:fim AS date)
        {_PESSOA}
      GROUP BY t.categoria_raiz_id
    ),
    calculo AS (
      SELECT
        m.categoria_id,
        m.nome,
        m.valor_meta AS meta,
        coalesce(g.gasto, 0) AS gasto,
        coalesce(g.gasto, 0) / m.valor_meta * 100 AS razao
      FROM metas m
      LEFT JOIN gastos g ON g.categoria_id = m.categoria_id
    )
    SELECT
      categoria_id,
      nome,
      gasto,
      meta,
      round(razao)::int AS percentual,
      CASE WHEN razao > 100 THEN 'estourado' WHEN razao > 90 THEN 'perto' ELSE 'ok' END AS faixa,
      least(100, round(razao))::int AS largura,
      CASE WHEN gasto > meta THEN gasto - meta END AS excesso
    FROM calculo
    ORDER BY razao DESC, nome
"""


def _somar_meses(competencia: date, n: int) -> date:
    indice = competencia.year * 12 + (competencia.month - 1) + n
    return date(indice // 12, indice % 12 + 1, 1)


class AnalisesService:
    def __init__(self, session: Session, hoje: date | None = None) -> None:
        self.session = session
        self.hoje = hoje or date.today()

    def resumo(self, periodo: Periodo, pessoa: str | None = None) -> Analises:
        fim = primeiro_dia_do_mes(self.hoje)
        quantos = MESES_DO_PERIODO[periodo]
        inicio = _somar_meses(fim, -(quantos - 1))
        fechados = quantos - 1
        params: dict[str, Any] = {"inicio": inicio, "fim": fim, "pessoa": pessoa}

        meses = [
            MesAnalise.model_validate(dict(linha._mapping))
            for linha in self.session.execute(text(_MESES), params)
        ]
        resumo = self.session.execute(text(_RESUMO_MESES), params).one()

        # Categorias: a média dos meses fechados, ou o próprio mês.
        if fechados > 0:
            de, ate, n = inicio, _somar_meses(fim, -1), fechados
        else:
            de, ate, n = fim, fim, 1
        categorias = self._categorias(
            self.session.execute(
                text(_CATEGORIAS),
                {**params, "de": de, "ate": ate, "n": n, "sem_categoria": SEM_CATEGORIA},
            ).all()
        )

        return Analises(
            periodo=periodo,
            inicio=inicio,
            fim=fim,
            dia_referencia=self.hoje.day,
            dias_no_mes=calendar.monthrange(fim.year, fim.month)[1],
            meses=meses,
            meses_fechados=fechados,
            base_categorias="media_mensal" if fechados > 0 else "mes",
            media_mensal=(
                Decimal(resumo.media_mensal) if resumo.media_mensal is not None else None
            ),
            mes_mais_caro=(
                MesAnalise(
                    competencia=resumo.competencia,
                    despesas=resumo.despesas,
                    receitas=resumo.receitas,
                    em_curso=resumo.em_curso,
                )
                if resumo.competencia is not None
                else None
            ),
            categorias=categorias,
            mudancas=self._mudancas(params, inicio, fim, fechados),
            orcamento=[
                LinhaOrcamentoAnalise.model_validate(dict(linha._mapping))
                for linha in self.session.execute(text(_ORCAMENTO), params)
            ],
        )

    def _mudancas(
        self, params: dict[str, Any], inicio: date, fim: date, fechados: int
    ) -> Mudancas | None:
        """O último mês fechado contra a média dos fechados antes dele."""
        base = fechados - 1
        if base < 1:
            return None
        referencia = _somar_meses(fim, -1)
        linhas = self.session.execute(
            text(_MUDANCAS),
            {
                **params,
                "base_de": inicio,
                "ref": referencia,
                "n_base": base,
                "limite": LIMITE_MUDANCAS,
            },
        )
        return Mudancas(
            referencia=referencia,
            meses_base=base,
            linhas=[MudancaCategoria.model_validate(dict(linha._mapping)) for linha in linhas],
        )

    @staticmethod
    def _categorias(linhas: Sequence[Row[Any]]) -> list[CategoriaAnalise]:
        """Raízes na ordem do SQL, cada uma com as folhas dela."""
        raizes: dict[int | None, CategoriaAnalise] = {}
        for linha in linhas:
            raiz = raizes.get(linha.raiz_id)
            if raiz is None:
                raiz = CategoriaAnalise(
                    categoria_id=linha.raiz_id,
                    nome=linha.raiz_nome,
                    valor=linha.raiz_valor,
                    subcategorias=[],
                )
                raizes[linha.raiz_id] = raiz
            if linha.categoria_id is not None:
                raiz.subcategorias.append(
                    SubcategoriaAnalise(
                        categoria_id=linha.categoria_id,
                        nome=linha.categoria_nome,
                        valor=linha.folha_valor,
                    )
                )
        return list(raizes.values())
