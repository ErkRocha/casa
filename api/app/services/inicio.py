"""A tela Início (D-24): o mês num relance.

Toda soma, diferença, percentual e a previsão saem do SQL abaixo; o Python
só escolhe o mês e monta a resposta (regras 7 e 10, D-14). Transferência
fica fora de tudo (D-05).

**Por competência, desenhado pelo caixa (D-27).** O total do mês é o da
competência (D-02), o mesmo do orçamento e do relatório. O que muda é o dia:
Pix, débito e boleto contam na data deles; cada cartão com compra na
competência vira um degrau único, no dia do pagamento da fatura (ou do
vencimento, enquanto "a pagar"). As datas e o cálculo dos degraus estão em
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

_TOTAIS = f"""
    WITH {caixa.CTES_DEGRAUS},
    base AS ({_BASE} AND t.competencia IN (:c, :p)),
    marcada AS (
      SELECT b.*,
        EXISTS (SELECT 1 FROM degraus g WHERE g.fid = b.forma_pagamento_id) AS em_degrau
      FROM base b
    ),
    atual AS (
      SELECT
        coalesce(sum(valor) FILTER (WHERE tipo = 'despesa' AND dia <= :dia_ref), 0) AS gasto,
        coalesce(sum(valor) FILTER (
          WHERE tipo = 'despesa' AND dia <= :dia_ref AND NOT em_degrau), 0) AS livre,
        coalesce(sum(valor) FILTER (
          WHERE tipo = 'despesa' AND dia <= :dia_ref AND NOT em_degrau AND antes), 0)
          AS livre_antes,
        coalesce(sum(valor) FILTER (WHERE tipo = 'receita' AND dia <= :dia_ref), 0) AS receitas
      FROM marcada WHERE competencia = :c
    ),
    faturas_mes AS (SELECT coalesce(sum(valor), 0) AS total FROM degraus),
    anterior AS (
      SELECT coalesce(sum(valor) FILTER (WHERE tipo = 'despesa' AND dia <= :dia_cmp), 0) AS gasto
      FROM base WHERE competencia = :p
    ),
    meta AS (
      SELECT sum(valor_meta) AS total
      FROM orcamentos WHERE competencia = :c AND deleted_em IS NULL
    ),
    calculo AS (
      SELECT
        a.gasto,
        f.total + a.livre_antes AS comprometido,
        a.receitas,
        ant.gasto AS gasto_anterior,
        m.total AS meta,
        CASE WHEN m.total > 0 THEN a.gasto / m.total * 100 END AS razao,
        CASE WHEN :corrente AND :dia_ref > 0
          THEN round(
            f.total + a.livre_antes + (a.livre - a.livre_antes) / :dia_ref * :dias, 2)
        END AS previsao
      FROM atual a, faturas_mes f, anterior ant, meta m
    )
    SELECT
      gasto,
      comprometido,
      receitas,
      gasto_anterior,
      gasto - gasto_anterior AS diferenca_anterior,
      receitas - gasto AS sobra,
      meta,
      round(razao)::int AS percentual_usado,
      CASE WHEN razao > 100 THEN 'estourado' WHEN razao > 90 THEN 'perto' ELSE 'ok' END AS faixa,
      previsao,
      previsao - meta AS previsao_menos_meta,
      (SELECT count(*) FROM vw_transacoes_completa WHERE competencia = :c) AS lancamentos,
      (SELECT coalesce(sum(valor), 0) FROM degraus WHERE situacao = 'a_pagar') AS a_pagar_mes
    FROM calculo
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

#: Despesas pela data da compra (não a competência), sem pendentes (D-28):
#: no mês `:c` até o dia `:dia_ref` e no mês `:p` até `:dia_cmp`.
_GASTO_COMPRA = """
    SELECT
      coalesce(sum(t.valor) FILTER (
        WHERE t.data >= CAST(:c AS date) AND extract(day FROM t.data) <= :dia_ref), 0) AS atual,
      coalesce(sum(t.valor) FILTER (
        WHERE t.data < CAST(:c AS date) AND extract(day FROM t.data) <= :dia_cmp), 0) AS anterior
    FROM vw_transacoes_completa t
    WHERE t.tipo = 'despesa' AND t.data >= CAST(:p AS date)
      AND t.data < (CAST(:c AS date) + interval '1 month')::date
"""

_PESSOAS = f"""
    WITH base AS ({_BASE} AND t.competencia = :c AND t.tipo = 'despesa'),
    somas AS (
      SELECT coalesce(cast(pessoa_id AS text), 'conjunto') AS balde, sum(valor) AS valor
      FROM base WHERE dia <= :dia_ref GROUP BY 1
    ),
    total AS (SELECT sum(valor) AS total FROM somas),
    baldes AS (
      SELECT cast(id AS text) AS balde, nome, 0 AS ordem
      FROM pessoas WHERE deleted_em IS NULL
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

_CATEGORIAS = f"""
    WITH base AS ({_BASE} AND t.competencia = :c AND t.tipo = 'despesa'),
    somas AS (
      SELECT categoria_id, max(categoria_nome) AS nome, sum(valor) AS valor
      FROM base WHERE dia <= :dia_ref GROUP BY categoria_id
    ),
    total AS (SELECT sum(valor) AS total, max(valor) AS maior FROM somas),
    escolhidas AS (
      SELECT categoria_id, nome, valor FROM (
        SELECT s.*, row_number() OVER (ORDER BY valor DESC, nome) AS posicao
        FROM somas s WHERE categoria_id IS NOT NULL
      ) x WHERE posicao <= :top
      UNION ALL
      SELECT NULL, CAST(:sem_categoria AS text), valor FROM somas WHERE categoria_id IS NULL
    )
    SELECT
      e.categoria_id,
      e.nome,
      e.valor,
      round(e.valor / t.total * 100)::int AS percentual,
      round(e.valor / t.maior * 100)::int AS largura
    FROM escolhidas e CROSS JOIN total t
    WHERE t.total > 0
    ORDER BY (e.categoria_id IS NULL), e.valor DESC, e.nome
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

        params_caixa = {**params, **caixa.parametros()}
        t = self.session.execute(text(_TOTAIS), params_caixa).mappings().one()

        orcamento = (
            Orcamento(
                total=Decimal(t["meta"]),
                percentual_usado=int(t["percentual_usado"]),
                faixa=t["faixa"],
            )
            if t["meta"] is not None and Decimal(t["meta"]) > 0
            else None
        )
        previsao = (
            Previsao(
                valor=Decimal(t["previsao"]),
                comprometido=Decimal(t["comprometido"]),
                diferenca_orcamento=(
                    Decimal(t["previsao_menos_meta"]) if orcamento is not None else None
                ),
            )
            if t["previsao"] is not None
            else None
        )

        compra = self.session.execute(text(_GASTO_COMPRA), params).mappings().one()
        serie = [
            PontoAcumulado(
                dia=linha.dia,
                acumulado=Decimal(linha.acumulado),
                com_a_pagar=Decimal(linha.com_a_pagar),
            )
            for linha in self.session.execute(
                text(_SERIE),
                {**params_caixa, "dias": dias, "dia_ref": dia_ref},
            )
        ]
        saiu = next((ponto.acumulado for ponto in serie if ponto.dia == dia_ref), Decimal(0))

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
            gasto_compra=Decimal(compra["atual"]),
            gasto_compra_mes_anterior=Decimal(compra["anterior"]),
            diferenca_compra_mes_anterior=Decimal(compra["atual"]) - Decimal(compra["anterior"]),
            saiu_da_conta=saiu,
            a_pagar_mes=Decimal(t["a_pagar_mes"]),
            janela=caixa.janela(self.session, self.hoje),
            orcamento=orcamento,
            previsao=previsao,
            serie=serie,
            faturas=caixa.faturas_do_mes(self.session, c),
            faturas_abertas=caixa.faturas_abertas(self.session, self.hoje),
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
                    categoria_id=linha.categoria_id,
                    nome=linha.nome,
                    valor=Decimal(linha.valor),
                    percentual=int(linha.percentual),
                    largura=int(linha.largura),
                )
                for linha in self.session.execute(
                    text(_CATEGORIAS),
                    {**params, "top": TOP_CATEGORIAS, "sem_categoria": tools.SEM_CATEGORIA},
                )
            ],
            avisos=self._avisos(c, situacao, dias - dia_ref),
        )

    def _avisos(
        self, c: date, situacao: str, dias_restantes: int
    ) -> list[AvisoOrcamento | AvisoReajuste]:
        """As detecções do relatório mensal, sem modelo nenhum (D-10).

        Mês futuro não tem o que detectar. A ordem é a de leitura: o que
        estourou, o que está perto, e os reajustes.
        """
        if situacao == "futuro":
            return []
        avisos: list[AvisoOrcamento | AvisoReajuste] = []
        orcamento = tools.status_orcamento(self.session, c)
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
