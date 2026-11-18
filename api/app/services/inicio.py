"""A tela Início (D-24, D-31): quanto a gente gastou este mês?

Toda soma, diferença, percentual e a previsão saem do SQL abaixo; o Python
só escolhe o mês e monta a resposta (regras 7 e 10, D-14). Transferência
fica fora de tudo (D-05).

**O topo é pela data da compra (D-31).** Gasto até hoje, a comparação com o
mês anterior no mesmo dia, receitas, sobra, orçamento, quem gastou, por
categoria e os avisos de orçamento saem todos de `_COMPRA`: despesas e
receitas com data no mês, até o dia de referência, sem pendentes (D-28).
Pessoas e categorias somam o gasto, e nenhum número do topo usa competência.

**O caixa é um bloco à parte (D-27).** Faturas a pagar, o que já saiu da conta
e a previsão de fechamento são por competência, desenhados pelo caixa: Pix,
débito e boleto contam na data deles; cada cartão com compra na competência
vira um degrau único, no dia do pagamento da fatura (ou do vencimento,
enquanto "a pagar"). As datas e o cálculo dos degraus estão em
`app.services.caixa`. Cartão sem nenhuma data conhecida mantém as compras no
dia delas, e a compra com data anterior ao mês conta no dia 1. A previsão
soma as faturas do mês (já conhecidas, pagas ou não) e o "antes" dos cartões
sem datas, e só projeta em linha reta o que sobra. Sem essa separação, a
fatura inteira entraria no ritmo e seria multiplicada pelos dias que faltam.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.insights import tools
from app.schemas.inicio import (
    AvisoOrcamento,
    AvisoReajuste,
    CaixaMes,
    Inicio,
    LinhaCategoriaInicio,
    LinhaPessoaInicio,
    Orcamento,
    PontoAcumulado,
    Previsao,
)
from app.services import caixa
from app.services.cadastros import primeiro_dia_do_mes

#: Quantas categorias com nome a tela mostra; "Sem categoria" vem à parte.
TOP_CATEGORIAS = 5
#: Rótulo da linha que junta as categorias além das `TOP_CATEGORIAS`.
OUTRAS_CATEGORIAS = "Outras categorias"
#: Rótulo do balde conjunto na tela (D-24). Na API o balde é `conjunto`.
ROTULO_JUNTOS = "Juntos"

#: Dia da transação dentro do mês da competência: data antes do mês conta no
#: dia 1, data depois dele no último dia.
_BASE = """
    SELECT
      t.competencia,
      t.tipo,
      t.valor,
      t.pessoa_id,
      t.categoria_id,
      t.categoria_nome,
      t.forma_pagamento_id,
      t.data < t.competencia AS antes,
      CASE
        WHEN t.data < t.competencia THEN 1
        WHEN t.data >= (t.competencia + interval '1 month')::date
          THEN extract(day FROM (t.competencia + interval '1 month' - interval '1 day'))::int
        ELSE extract(day FROM t.data)::int
      END AS dia
    FROM vw_transacoes_completa t
    WHERE t.tipo <> 'transferencia'
"""

#: O caixa do mês (D-27): comprometido, previsão e o que está a pagar.
_CAIXA = f"""
    WITH {caixa.CTES_DEGRAUS},
    base AS ({_BASE} AND t.competencia = :c AND t.tipo = 'despesa'),
    marcada AS (
      SELECT b.*,
        EXISTS (SELECT 1 FROM degraus g WHERE g.fid = b.forma_pagamento_id) AS em_degrau
      FROM base b
    ),
    atual AS (
      SELECT
        coalesce(sum(valor) FILTER (WHERE dia <= :dia_ref AND NOT em_degrau), 0) AS livre,
        coalesce(sum(valor) FILTER (WHERE dia <= :dia_ref AND NOT em_degrau AND antes), 0)
          AS livre_antes
      FROM marcada
    ),
    faturas_mes AS (SELECT coalesce(sum(valor), 0) AS total FROM degraus)
    SELECT
      f.total + a.livre_antes AS comprometido,
      CASE WHEN :corrente AND :dia_ref > 0
        THEN round(f.total + a.livre_antes + (a.livre - a.livre_antes) / :dia_ref * :dias, 2)
      END AS previsao,
      (SELECT coalesce(sum(valor), 0) FROM degraus WHERE situacao = 'a_pagar') AS a_pagar
    FROM atual a, faturas_mes f
"""

#: Um ponto por dia do mês (D-27). `acumulado` é o que já saiu da conta;
#: `com_a_pagar` soma o que ainda vai sair. Despesa de cartão sem degrau fica
#: no dia dela (ou no dia 1, se a data é anterior ao mês).
_SERIE = f"""
    WITH {caixa.CTES_DEGRAUS},
    base AS ({_BASE} AND t.competencia = :c AND t.tipo = 'despesa'),
    livres AS (
      SELECT b.dia, b.valor FROM base b
      WHERE NOT EXISTS (SELECT 1 FROM degraus g WHERE g.fid = b.forma_pagamento_id)
    )
    SELECT d.dia, x.acumulado, x.acumulado + x.a_pagar + x.futuras AS com_a_pagar
    FROM generate_series(1, CASE WHEN :dia_ref > 0 THEN :dias ELSE 0 END) AS d(dia)
    CROSS JOIN LATERAL (
      SELECT
        (SELECT coalesce(sum(valor), 0) FROM livres WHERE dia <= least(d.dia, :dia_ref))
        + (SELECT coalesce(sum(valor), 0) FROM degraus
           WHERE situacao = 'paga' AND dia <= d.dia) AS acumulado,
        (SELECT coalesce(sum(valor), 0) FROM degraus
         WHERE situacao = 'a_pagar' AND dia <= d.dia) AS a_pagar,
        (SELECT coalesce(sum(valor), 0) FROM livres
         WHERE dia > :dia_ref AND dia <= d.dia) AS futuras
    ) x
    ORDER BY d.dia
"""

#: A base do topo (D-31): despesas e receitas pela data da compra, no mês
#: `:c` até o dia `:dia_ref`, sem pendentes (D-28).
_COMPRA = """
    SELECT t.tipo, t.valor, t.pessoa_id, t.categoria_id, t.categoria_nome
    FROM vw_transacoes_completa t
    WHERE t.tipo IN ('despesa', 'receita')
      AND t.data >= CAST(:c AS date)
      AND t.data < (CAST(:c AS date) + interval '1 month')::date
      AND extract(day FROM t.data) <= :dia_ref
"""

_TOTAIS = f"""
    WITH base AS ({_COMPRA}),
    atual AS (
      SELECT
        coalesce(sum(valor) FILTER (WHERE tipo = 'despesa'), 0) AS gasto,
        coalesce(sum(valor) FILTER (WHERE tipo = 'receita'), 0) AS receitas
      FROM base
    ),
    anterior AS (
      SELECT coalesce(sum(t.valor), 0) AS gasto
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa'
        AND t.data >= CAST(:p AS date) AND t.data < CAST(:c AS date)
        AND extract(day FROM t.data) <= :dia_cmp
    ),
    meta AS (
      SELECT sum(valor_meta) AS total
      FROM orcamentos WHERE competencia = :c AND deleted_em IS NULL
    ),
    calculo AS (
      SELECT
        a.gasto,
        a.receitas,
        ant.gasto AS gasto_anterior,
        m.total AS meta,
        CASE WHEN m.total > 0 THEN a.gasto / m.total * 100 END AS razao
      FROM atual a, anterior ant, meta m
    )
    SELECT
      gasto,
      receitas,
      gasto_anterior,
      gasto - gasto_anterior AS diferenca_anterior,
      receitas - gasto AS sobra,
      meta,
      round(razao)::int AS percentual_usado,
      CASE WHEN razao > 100 THEN 'estourado' WHEN razao > 90 THEN 'perto' ELSE 'ok' END AS faixa,
      (SELECT count(*) FROM vw_transacoes_completa t
       WHERE t.competencia = :c
          OR (t.data >= CAST(:c AS date)
              AND t.data < (CAST(:c AS date) + interval '1 month')::date)) AS lancamentos
    FROM calculo
"""

#: Cada balde (pessoa ou conjunto, D-03) com o gasto do topo. Pessoa removida
#: que tem gasto no mês continua listada: as linhas somam o gasto.
_PESSOAS = f"""
    WITH base AS ({_COMPRA}),
    somas AS (
      SELECT coalesce(cast(pessoa_id AS text), 'conjunto') AS balde, sum(valor) AS valor
      FROM base WHERE tipo = 'despesa' GROUP BY 1
    ),
    total AS (SELECT sum(valor) AS total FROM somas),
    baldes AS (
      SELECT cast(id AS text) AS balde, nome, 0 AS ordem
      FROM pessoas
      WHERE deleted_em IS NULL OR cast(id AS text) IN (SELECT balde FROM somas)
      UNION ALL
      SELECT 'conjunto', CAST(:juntos AS text), 1
    )
    SELECT
      b.balde,
      b.nome,
      coalesce(s.valor, 0) AS valor,
      CASE WHEN t.total > 0 THEN round(coalesce(s.valor, 0) / t.total * 100)::int ELSE 0 END
        AS percentual
    FROM baldes b
    LEFT JOIN somas s ON s.balde = b.balde
    CROSS JOIN total t
    ORDER BY b.ordem, b.nome
"""

#: As maiores categorias, "Outras categorias" com o resto e "Sem categoria"
#: no fim: as linhas somam o gasto do topo (D-31).
_CATEGORIAS = f"""
    WITH base AS ({_COMPRA}),
    somas AS (
      SELECT categoria_id, max(categoria_nome) AS nome, sum(valor) AS valor
      FROM base WHERE tipo = 'despesa' GROUP BY categoria_id
    ),
    ranqueadas AS (
      SELECT s.*, row_number() OVER (ORDER BY valor DESC, nome) AS posicao
      FROM somas s WHERE categoria_id IS NOT NULL
    ),
    escolhidas AS (
      SELECT 'categoria' AS tipo, 0 AS grupo, categoria_id, nome, valor
      FROM ranqueadas WHERE posicao <= :top
      UNION ALL
      SELECT 'outras', 1, NULL, CAST(:outras AS text), sum(valor)
      FROM ranqueadas WHERE posicao > :top HAVING count(*) > 0
      UNION ALL
      SELECT 'sem_categoria', 2, NULL, CAST(:sem_categoria AS text), valor
      FROM somas WHERE categoria_id IS NULL
    ),
    total AS (SELECT sum(valor) AS total, max(valor) AS maior FROM escolhidas)
    SELECT
      e.tipo,
      e.categoria_id,
      e.nome,
      e.valor,
      round(e.valor / t.total * 100)::int AS percentual,
      round(e.valor / t.maior * 100)::int AS largura
    FROM escolhidas e CROSS JOIN total t
    WHERE t.total > 0
    ORDER BY e.grupo, e.valor DESC, e.nome
"""


def _mes_anterior(competencia: date) -> date:
    if competencia.month == 1:
        return date(competencia.year - 1, 12, 1)
    return date(competencia.year, competencia.month - 1, 1)


class InicioService:
    def __init__(self, session: Session, hoje: date | None = None) -> None:
        self.session = session
        #: Injetável para o teste não depender do relógio.
        self.hoje = hoje or date.today()

    def resumo(self, competencia: date | None = None) -> Inicio:
        c = primeiro_dia_do_mes(competencia or self.hoje)
        mes_atual = primeiro_dia_do_mes(self.hoje)
        dias = calendar.monthrange(c.year, c.month)[1]
        if c > mes_atual:
            situacao, dia_ref = "futuro", 0
        elif c == mes_atual:
            situacao, dia_ref = "corrente", self.hoje.day
        else:
            situacao, dia_ref = "passado", dias

        p = _mes_anterior(c)
        dias_p = calendar.monthrange(p.year, p.month)[1]
        params: dict[str, Any] = {
            "c": c,
            "p": p,
            "dias": dias,
            "dia_ref": dia_ref,
            "dia_cmp": min(dia_ref, dias_p),
            "corrente": situacao == "corrente",
        }

        t = self.session.execute(text(_TOTAIS), params).mappings().one()
        orcamento = (
            Orcamento(
                total=Decimal(t["meta"]),
                percentual_usado=int(t["percentual_usado"]),
                faixa=t["faixa"],
            )
            if t["meta"] is not None and Decimal(t["meta"]) > 0
            else None
        )

        return Inicio(
            competencia=c,
            situacao=situacao,
            dias_no_mes=dias,
            dia_referencia=dia_ref,
            tem_dados=int(t["lancamentos"]) > 0,
            gasto=Decimal(t["gasto"]),
            gasto_mes_anterior=Decimal(t["gasto_anterior"]),
            diferenca_mes_anterior=Decimal(t["diferenca_anterior"]),
            receitas=Decimal(t["receitas"]),
            sobra=Decimal(t["sobra"]),
            orcamento=orcamento,
            pessoas=[
                LinhaPessoaInicio(
                    balde=linha.balde,
                    nome=linha.nome,
                    valor=Decimal(linha.valor),
                    percentual=int(linha.percentual),
                )
                for linha in self.session.execute(
                    text(_PESSOAS), {**params, "juntos": ROTULO_JUNTOS}
                )
            ],
            categorias=[
                LinhaCategoriaInicio(
                    tipo=linha.tipo,
                    categoria_id=linha.categoria_id,
                    nome=linha.nome,
                    valor=Decimal(linha.valor),
                    percentual=int(linha.percentual),
                    largura=int(linha.largura),
                )
                for linha in self.session.execute(
                    text(_CATEGORIAS),
                    {
                        **params,
                        "top": TOP_CATEGORIAS,
                        "outras": OUTRAS_CATEGORIAS,
                        "sem_categoria": tools.SEM_CATEGORIA,
                    },
                )
            ],
            avisos=self._avisos(c, situacao, dia_ref, dias - dia_ref),
            caixa=self._caixa(c, params),
            faturas_abertas=caixa.faturas_abertas(self.session, self.hoje),
        )

    def _caixa(self, c: date, params: dict[str, Any]) -> CaixaMes:
        """O bloco "o que sai da conta" (D-27), por competência."""
        params_caixa = {**params, **caixa.parametros()}
        k = self.session.execute(text(_CAIXA), params_caixa).mappings().one()
        serie = [
            PontoAcumulado(
                dia=linha.dia,
                acumulado=Decimal(linha.acumulado),
                com_a_pagar=Decimal(linha.com_a_pagar),
            )
            for linha in self.session.execute(text(_SERIE), params_caixa)
        ]
        dia_ref = params["dia_ref"]
        return CaixaMes(
            saiu_da_conta=next(
                (ponto.acumulado for ponto in serie if ponto.dia == dia_ref), Decimal(0)
            ),
            a_pagar=Decimal(k["a_pagar"]),
            previsao=(
                Previsao(valor=Decimal(k["previsao"]), comprometido=Decimal(k["comprometido"]))
                if k["previsao"] is not None
                else None
            ),
            serie=serie,
            faturas=caixa.faturas_do_mes(self.session, c),
        )

    def _avisos(
        self, c: date, situacao: str, dia_ref: int, dias_restantes: int
    ) -> list[AvisoOrcamento | AvisoReajuste]:
        """As detecções do relatório mensal, sem modelo nenhum (D-10).

        Mês futuro não tem o que detectar. A ordem é a de leitura: o que
        estourou, o que está perto, e os reajustes. O orçamento é pela data
        da compra até o dia de referência, como o resto do topo (D-31).
        """
        if situacao == "futuro":
            return []
        avisos: list[AvisoOrcamento | AvisoReajuste] = []
        orcamento = tools.status_orcamento(self.session, c, pela_compra_ate=c.replace(day=dia_ref))
        for situacao_linha in ("estourado", "atencao"):
            for linha in orcamento.linhas:
                if linha.situacao != situacao_linha:
                    continue
                avisos.append(
                    AvisoOrcamento(
                        categoria=linha.categoria,
                        percentual=linha.percentual,
                        realizado=linha.realizado,
                        meta=linha.meta,
                        situacao=linha.situacao,
                        dias_restantes=dias_restantes if situacao == "corrente" else None,
                    )
                )
        for reajuste in tools.recorrencias_com_reajuste(self.session, c).linhas:
            avisos.append(
                AvisoReajuste(
                    descricao=reajuste.descricao,
                    valor_anterior=reajuste.valor_anterior,
                    valor_atual=reajuste.valor_atual,
                )
            )
        return avisos
