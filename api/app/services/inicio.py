"""A tela Início (D-24, D-31): quanto a gente gastou este mês?

Toda soma, diferença, percentual e a previsão saem do SQL abaixo; o Python
só escolhe o mês e monta a resposta (regras 7 e 10, D-14). Transferência
fica fora de tudo (D-05).

**O topo é o gasto do mês da D-32** (ajusta a D-31). Cartão: a fatura do mês
de cada cartão, do dia seguinte ao fechamento até hoje, pela data da compra,
lançadas e pendentes (D-28). O resto (Pix, débito, boleto): pela data, no mês
até hoje. A comparação com o mês anterior, o orçamento, quem gastou, por
categoria e os avisos de orçamento saem da mesma base (`_cte_gasto`), numa
consulta só (`_TOPO`). Pendente entra sem categoria e na pessoa titular do
cartão. Pessoas e categorias somam o gasto. Receitas são pela data.

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
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.faixas_orcamento import sql_faixa
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
    -- A curva usa a soma das compras (`valor_compras`): fecha com o total do
    -- mês (D-02). O total real da fatura (D-34) aparece nas faturas e no a pagar.
    faturas_mes AS (SELECT coalesce(sum(valor_compras), 0) AS total FROM degraus)
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
        + (SELECT coalesce(sum(valor_compras), 0) FROM degraus
           WHERE situacao = 'paga' AND dia <= d.dia) AS acumulado,
        (SELECT coalesce(sum(valor_compras), 0) FROM degraus
         WHERE situacao = 'a_pagar' AND dia <= d.dia) AS a_pagar,
        (SELECT coalesce(sum(valor), 0) FROM livres
         WHERE dia > :dia_ref AND dia <= d.dia) AS futuras
    ) x
    ORDER BY d.dia
"""

#: Quantos dias depois do fechamento decidem de que mês é a fatura (D-32): o
#: ciclo é do mês em que cai a maior parte dele. Cartão que fecha dia 3 abre
#: o ciclo de novembro em 04/11; o que fecha dia 28 abre em 29/10 o ciclo que
#: é quase todo de novembro.
DIAS_ATE_O_MEIO_DO_CICLO = 15


def _cte_gasto(nome: str, mes: str, ate_cartao: str, ate_outros: str) -> str:
    """CTEs do "gasto até hoje" de um mês (D-32), com o prefixo `nome`.

    Precisa de `caixa.CTES_FATURAS` e `caixa.CTE_PENDENTES` antes. A última CTE,
    `{nome}`, tem uma linha por despesa: `valor`, `pessoa_id`, `categoria_id`,
    `categoria_nome`, `categoria_raiz_id` e `pendente`.

    * **Cartão com datas** (fatura da Pluggy, dia de fechamento cadastrado ou
      a conta de crédito da Pluggy): as compras do ciclo que é do mês, do dia
      seguinte ao fechamento até o próximo fechamento e até `ate_cartao`;
      lançadas e pendentes (D-28). A compra antes do fechamento é do ciclo
      anterior, contada no mês anterior: cada compra entra em um mês só.
    * **O resto** (Pix, débito, boleto, dinheiro, sem forma, cartão sem
      nenhuma data): pela data, no mês e até `ate_outros`.

    `mes`, `ate_cartao` e `ate_outros` são nomes de parâmetro (":c"), nunca
    texto do usuário.
    """
    m = f"CAST({mes} AS date)"
    ac = f"CAST({ate_cartao} AS date)"
    ao = f"CAST({ate_outros} AS date)"
    return f"""
    {nome}_fechs AS (
      SELECT k.fid,
        coalesce(
          (SELECT max(fa.fechamento) FROM faturas fa
            WHERE fa.account_id = k.account_id AND date_trunc('month', fa.fechamento) = x.m),
          CASE WHEN k.dia_fechamento IS NOT NULL THEN {caixa.no_mes("x.m", "k.dia_fechamento")} END,
          CASE WHEN date_trunc('month', k.cc_fecha) = x.m THEN k.cc_fecha END
        ) AS fech
      FROM cartao_conta k
      CROSS JOIN (
        SELECT ({m} + n * interval '1 month')::date AS m FROM generate_series(-2, 2) AS n
      ) x
    ),
    {nome}_com_datas AS (
      SELECT DISTINCT fid FROM {nome}_fechs WHERE fech IS NOT NULL
    ),
    {nome}_ciclos AS (
      SELECT f.fid, f.fech AS desde,
        least(
          coalesce(
            (SELECT min(g.fech) FROM {nome}_fechs g WHERE g.fid = f.fid AND g.fech > f.fech),
            {ac}
          ),
          {ac}
        ) AS ate
      FROM {nome}_fechs f
      WHERE f.fech IS NOT NULL
        AND date_trunc('month', f.fech + {DIAS_ATE_O_MEIO_DO_CICLO}) = {m}
    ),
    {nome} AS (
      SELECT t.valor, t.pessoa_id, t.categoria_id, t.categoria_nome, t.categoria_raiz_id,
        false AS pendente
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa' AND (
        EXISTS (
          SELECT 1 FROM {nome}_ciclos z
          WHERE z.fid = t.forma_pagamento_id AND t.data > z.desde AND t.data <= z.ate
        )
        OR (
          (t.forma_pagamento_id IS NULL
           OR t.forma_pagamento_id NOT IN (SELECT fid FROM {nome}_com_datas))
          AND t.data >= {m} AND t.data < ({m} + interval '1 month')::date AND t.data <= {ao}
        )
      )
      UNION ALL
      SELECT p.valor, coalesce(f.titular_id, ct.titular_id), NULL::bigint, NULL::text,
        NULL::bigint, true
      FROM pendentes p
      JOIN formas_pagamento f ON f.id = p.forma_pagamento_id
      LEFT JOIN contas ct ON ct.id = f.conta_id
      WHERE EXISTS (
          SELECT 1 FROM {nome}_ciclos z
          WHERE z.fid = p.forma_pagamento_id AND p.data > z.desde AND p.data <= z.ate
        )
        OR (
          p.forma_pagamento_id NOT IN (SELECT fid FROM {nome}_com_datas)
          AND p.data >= {m} AND p.data < ({m} + interval '1 month')::date AND p.data <= {ao}
        )
    )"""


#: O topo do Início numa consulta só (D-32): o gasto do mês e o do mês
#: anterior na mesma regra, receitas, orçamento, pessoas, categorias e os
#: avisos de orçamento. As listas saem em JSON com dinheiro em texto (regra 1:
#: nunca float no caminho).
_TOPO = f"""
    WITH {caixa.CTES_FATURAS},
    {caixa.CTE_PENDENTES},
    {_cte_gasto("atual", ":c", ":ate_cartao", ":ate_outros")},
    {_cte_gasto("anterior", ":p", ":ate_cartao_p", ":ate_outros_p")},
    totais AS (
      SELECT
        (SELECT coalesce(sum(valor), 0) FROM atual) AS gasto,
        (SELECT coalesce(sum(valor), 0) FROM atual WHERE pendente) AS pendente,
        (SELECT coalesce(sum(valor), 0) FROM anterior) AS gasto_anterior,
        (SELECT coalesce(sum(t.valor), 0) FROM vw_transacoes_completa t
          WHERE t.tipo = 'receita' AND t.data >= CAST(:c AS date)
            AND t.data < (CAST(:c AS date) + interval '1 month')::date
            AND t.data <= CAST(:ate_outros AS date)) AS receitas,
        (SELECT sum(valor_meta) FROM orcamentos
          WHERE competencia = CAST(:c AS date) AND deleted_em IS NULL) AS meta
    ),
    calculo AS (
      SELECT *, CASE WHEN meta > 0 THEN gasto / meta * 100 END AS razao FROM totais
    ),
    p_somas AS (
      SELECT coalesce(cast(pessoa_id AS text), 'conjunto') AS balde, sum(valor) AS valor
      FROM atual GROUP BY 1
    ),
    p_total AS (SELECT sum(valor) AS total FROM p_somas),
    p_baldes AS (
      SELECT cast(id AS text) AS balde, nome, 0 AS ordem
      FROM pessoas
      WHERE deleted_em IS NULL OR cast(id AS text) IN (SELECT balde FROM p_somas)
      UNION ALL
      SELECT 'conjunto', CAST(:juntos AS text), 1
    ),
    p_linhas AS (
      SELECT b.balde, b.nome, b.ordem, coalesce(s.valor, 0) AS valor,
        CASE WHEN t.total > 0 THEN round(coalesce(s.valor, 0) / t.total * 100)::int ELSE 0 END
          AS percentual
      FROM p_baldes b
      LEFT JOIN p_somas s ON s.balde = b.balde
      CROSS JOIN p_total t
    ),
    c_somas AS (
      SELECT categoria_id, max(categoria_nome) AS nome, sum(valor) AS valor
      FROM atual GROUP BY categoria_id
    ),
    c_ranqueadas AS (
      SELECT s.*, row_number() OVER (ORDER BY valor DESC, nome) AS posicao
      FROM c_somas s WHERE categoria_id IS NOT NULL
    ),
    c_escolhidas AS (
      SELECT 'categoria' AS tipo, 0 AS grupo, categoria_id, nome, valor
      FROM c_ranqueadas WHERE posicao <= :top
      UNION ALL
      SELECT 'outras', 1, NULL, CAST(:outras AS text), sum(valor)
      FROM c_ranqueadas WHERE posicao > :top HAVING count(*) > 0
      UNION ALL
      SELECT 'sem_categoria', 2, NULL, CAST(:sem_categoria AS text), valor
      FROM c_somas WHERE categoria_id IS NULL
    ),
    c_total AS (SELECT sum(valor) AS total, max(valor) AS maior FROM c_escolhidas),
    c_linhas AS (
      SELECT e.*,
        round(e.valor / t.total * 100)::int AS percentual,
        round(e.valor / t.maior * 100)::int AS largura
      FROM c_escolhidas e CROSS JOIN c_total t
      WHERE t.total > 0
    ),
    o_linhas AS (
      SELECT cat.nome AS categoria, o.valor_meta AS meta, coalesce(r.realizado, 0) AS realizado,
        round(coalesce(r.realizado, 0) / o.valor_meta * 100, 1) AS percentual,
        {sql_faixa("coalesce(r.realizado, 0) / o.valor_meta * 100")} AS situacao
      FROM orcamentos o
      JOIN categorias cat ON cat.id = o.categoria_id
      LEFT JOIN LATERAL (
        SELECT sum(a.valor) AS realizado FROM atual a WHERE a.categoria_raiz_id = o.categoria_id
      ) r ON true
      WHERE o.deleted_em IS NULL AND o.competencia = CAST(:c AS date) AND o.valor_meta > 0
    )
    SELECT
      k.gasto,
      k.pendente,
      k.receitas,
      k.gasto_anterior,
      k.gasto - k.gasto_anterior AS diferenca_anterior,
      k.receitas - k.gasto AS sobra,
      k.meta,
      round(k.razao)::int AS percentual_usado,
      {sql_faixa("k.razao")} AS faixa,
      (SELECT count(*) FROM vw_transacoes_completa t
       WHERE t.competencia = CAST(:c AS date)
          OR (t.data >= CAST(:c AS date)
              AND t.data < (CAST(:c AS date) + interval '1 month')::date)) AS lancamentos,
      (SELECT coalesce(json_agg(json_build_object(
          'balde', balde, 'nome', nome, 'valor', valor::text, 'percentual', percentual)
          ORDER BY ordem, nome), '[]') FROM p_linhas) AS pessoas,
      (SELECT coalesce(json_agg(json_build_object(
          'tipo', tipo, 'categoria_id', categoria_id, 'nome', nome, 'valor', valor::text,
          'percentual', percentual, 'largura', largura)
          ORDER BY grupo, valor DESC, nome), '[]') FROM c_linhas) AS categorias,
      (SELECT coalesce(json_agg(json_build_object(
          'categoria', categoria, 'meta', meta::text, 'realizado', realizado::text,
          'percentual', percentual::text, 'situacao', situacao)
          ORDER BY situacao = 'atencao', percentual DESC, categoria), '[]')
        FROM o_linhas WHERE situacao <> 'ok') AS orcamento_avisos
    FROM calculo k
"""


def _mes_anterior(competencia: date) -> date:
    if competencia.month == 1:
        return date(competencia.year - 1, 12, 1)
    return date(competencia.year, competencia.month - 1, 1)


def _cortes(situacao: str, c: date, p: date, hoje: date, dias: int, dias_p: int) -> dict[str, date]:
    """Até que data cada parte do gasto vale, no mês e no anterior (D-32).

    Mês corrente: hoje, e o mês anterior até o mesmo dia. Mês fechado: o mês
    inteiro, e o cartão até hoje (o ciclo do mês fecha no começo do seguinte).
    Mês futuro: nada.
    """
    if situacao == "futuro":
        nada = c - timedelta(days=1)
        return {
            "ate_cartao": date(1900, 1, 1),
            "ate_outros": nada,
            "ate_cartao_p": date(1900, 1, 1),
            "ate_outros_p": nada,
        }
    if situacao == "corrente":
        mesmo_dia = p.replace(day=min(hoje.day, dias_p))
        return {
            "ate_cartao": hoje,
            "ate_outros": hoje,
            "ate_cartao_p": mesmo_dia,
            "ate_outros_p": mesmo_dia,
        }
    return {
        "ate_cartao": hoje,
        "ate_outros": c.replace(day=dias),
        "ate_cartao_p": hoje,
        "ate_outros_p": p.replace(day=dias_p),
    }


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

        t = (
            self.session.execute(
                text(_TOPO),
                {
                    "c": c,
                    "p": p,
                    **_cortes(situacao, c, p, self.hoje, dias, dias_p),
                    "juntos": ROTULO_JUNTOS,
                    "top": TOP_CATEGORIAS,
                    "outras": OUTRAS_CATEGORIAS,
                    "sem_categoria": tools.SEM_CATEGORIA,
                },
            )
            .mappings()
            .one()
        )
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
            gasto_pendente=Decimal(t["pendente"]),
            gasto_mes_anterior=Decimal(t["gasto_anterior"]),
            diferenca_mes_anterior=Decimal(t["diferenca_anterior"]),
            receitas=Decimal(t["receitas"]),
            sobra=Decimal(t["sobra"]),
            orcamento=orcamento,
            pessoas=[LinhaPessoaInicio.model_validate(linha) for linha in t["pessoas"]],
            categorias=[LinhaCategoriaInicio.model_validate(linha) for linha in t["categorias"]],
            avisos=self._avisos(c, situacao, dias - dia_ref, t["orcamento_avisos"]),
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
        self,
        c: date,
        situacao: str,
        dias_restantes: int,
        orcamento: list[dict[str, Any]],
    ) -> list[AvisoOrcamento | AvisoReajuste]:
        """Orçamento na base do topo (D-32) e os reajustes do relatório (D-10).

        Mês futuro não tem o que detectar. A ordem é a de leitura: o que
        estourou, o que está em atenção, e os reajustes.
        """
        if situacao == "futuro":
            return []
        avisos: list[AvisoOrcamento | AvisoReajuste] = [
            AvisoOrcamento(
                categoria=linha["categoria"],
                percentual=Decimal(linha["percentual"]),
                realizado=Decimal(linha["realizado"]),
                meta=Decimal(linha["meta"]),
                situacao=linha["situacao"],
                dias_restantes=dias_restantes if situacao == "corrente" else None,
            )
            for linha in orcamento
        ]
        for reajuste in tools.recorrencias_com_reajuste(self.session, c).linhas:
            avisos.append(
                AvisoReajuste(
                    descricao=reajuste.descricao,
                    valor_anterior=reajuste.valor_anterior,
                    valor_atual=reajuste.valor_atual,
                )
            )
        return avisos
