"""Gráficos do Início (D-29): gastos dos últimos 30 dias, em linhas.

Cada série é um jeito de pagar (um cartão, Pix, débito, boleto, o resto) e
cada ponto é o **acumulado** do gasto desde o começo da janela, pela data da
compra. Entram as despesas lançadas e as compras pendentes do cartão
(`caixa.CTE_PENDENTES`), que também contam em `pendente`. Receita,
transferência e pagamento de fatura (item rejeitado, não transação) ficam fora.

Tudo é SQL (regra 7): acumulados, totais e a linha da soma saem do banco; o
Python só escolhe parâmetros e monta a resposta. `CTE_CORES_CARTOES` é o
fragmento da cor estável de cada cartão e serve também ao gráfico de faturas.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.graficos_inicio import (
    CicloFatura,
    FaturasCiclos,
    GastosJanela,
    PessoaConectada,
    PontoCiclo,
    PontoGasto,
    SerieGasto,
)
from app.services import caixa

#: Dias da janela, contando hoje.
JANELA_DIAS = 30
#: Vencimentos até este tanto de dias à frente esticam a janela das faturas.
JANELA_VENCIMENTOS_DIAS = 15
#: Candidato de fechamento a até este tanto de dias de outro mais firme é o
#: mesmo fechamento.
MESMO_FECHAMENTO_DIAS = 10
#: Sem vencimento conhecido, a fatura vence este tanto depois de fechar.
VENCIMENTO_APOS_FECHAMENTO_DIAS = 10
#: Rótulo e cor da linha que soma as séries escolhidas.
ROTULO_SOMA = "Soma das selecionadas"
COR_SOMA = "serie-soma"
CHAVE_SOMA = "soma"

#: Cor de cada cartão (`credito` não excluído): `serie-1` a `serie-4`, em ciclo,
#: pela ordem (com mapeamento ativo na Pluggy primeiro, depois o id). Não olha
#: janela nem filtro, então a cor não muda entre recarregamentos. `cores_cartoes`:
#: `fid`, `cor`.
CTE_CORES_CARTOES = """
    cores_cartoes AS MATERIALIZED (
      SELECT f.id AS fid,
        'serie-' || (((row_number() OVER (
          ORDER BY EXISTS (
            SELECT 1 FROM contas_pluggy cp
            WHERE cp.forma_pagamento_id = f.id AND cp.deleted_em IS NULL AND cp.ativo
          ) DESC, f.id
        ) - 1) % 4) + 1) AS cor
      FROM formas_pagamento f
      WHERE f.tipo = 'credito' AND f.deleted_em IS NULL
    )
"""

_INICIO = "CAST(:inicio AS date)"
_HOJE = "CAST(:hoje AS date)"
_SERIES = "CAST(:series AS text[])"
_PESSOA = "CAST(:pessoa_id AS bigint)"

#: Uma linha por (série, dia) mais, se `:somar`, uma por dia da linha da soma.
#: `visivel` vem de `:series` (nulo = todas). `total`/`pendente_total` são os
#: da série (ou da soma) inteira; `geral_*` os de todas as visíveis.
_GASTOS = f"""
    WITH {caixa.CTE_PENDENTES},
    {CTE_CORES_CARTOES},
    dias AS (
      SELECT g.dt::date AS data
      FROM generate_series({_INICIO}, {_HOJE}, interval '1 day') AS g(dt)
    ),
    movs AS (
      SELECT t.data, t.valor, 0::numeric AS pendente, 0 AS e_pendente,
             t.forma_pagamento_id AS fid
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa' AND t.data >= {_INICIO} AND t.data <= {_HOJE}
      UNION ALL
      SELECT p.data, p.valor, p.valor, 1, p.forma_pagamento_id
      FROM pendentes p
      WHERE p.data >= {_INICIO} AND p.data <= {_HOJE}
    ),
    classificadas AS (
      SELECT m.data, m.valor, m.pendente, m.e_pendente,
        CASE WHEN f.tipo = 'credito' THEN 'cartao:' || f.id
             WHEN f.tipo IN ('pix', 'debito', 'boleto') THEN f.tipo::text
             ELSE 'outros' END AS chave,
        CASE WHEN f.tipo = 'credito' THEN f.apelido
             WHEN f.tipo = 'pix' THEN 'Pix'
             WHEN f.tipo = 'debito' THEN 'Débito'
             WHEN f.tipo = 'boleto' THEN 'Boleto'
             ELSE 'Outros' END AS rotulo,
        CASE WHEN f.tipo = 'credito' THEN 'cartao'
             WHEN f.tipo IN ('pix', 'debito', 'boleto') THEN f.tipo::text
             ELSE 'outros' END AS tipo,
        CASE WHEN f.tipo = 'credito' THEN f.id END AS forma_id,
        CASE WHEN f.tipo = 'credito' THEN coalesce(cc.cor, 'serie-outros')
             WHEN f.tipo = 'pix' THEN 'serie-pix'
             WHEN f.tipo = 'debito' THEN 'serie-debito'
             WHEN f.tipo = 'boleto' THEN 'serie-boleto'
             ELSE 'serie-outros' END AS cor,
        CASE WHEN f.tipo = 'credito' THEN 0
             WHEN f.tipo = 'pix' THEN 1
             WHEN f.tipo = 'debito' THEN 2
             WHEN f.tipo = 'boleto' THEN 3
             ELSE 4 END AS ordem
      FROM movs m
      LEFT JOIN formas_pagamento f ON f.id = m.fid
      LEFT JOIN contas c ON c.id = f.conta_id
      LEFT JOIN cores_cartoes cc ON cc.fid = f.id
      WHERE {_PESSOA} IS NULL OR c.titular_id = {_PESSOA}
    ),
    por_dia AS (
      SELECT chave, rotulo, tipo, forma_id, cor, ordem, data,
             sum(valor) AS valor, sum(pendente) AS pendente, max(e_pendente) AS e_pendente
      FROM classificadas
      GROUP BY chave, rotulo, tipo, forma_id, cor, ordem, data
    ),
    series AS (
      SELECT DISTINCT chave, rotulo, tipo, forma_id, cor, ordem,
             ({_SERIES} IS NULL OR chave = ANY({_SERIES})) AS visivel
      FROM por_dia
    ),
    grade AS (
      SELECT s.*, d.data,
             coalesce(p.valor, 0) AS valor,
             coalesce(p.pendente, 0) AS pendente,
             coalesce(p.e_pendente, 0) AS e_pendente
      FROM series s
      CROSS JOIN dias d
      LEFT JOIN por_dia p ON p.chave = s.chave AND p.data = d.data
    ),
    acumuladas AS (
      SELECT g.*,
        sum(g.valor) OVER (PARTITION BY g.chave ORDER BY g.data) AS acumulado,
        sum(g.pendente) OVER (PARTITION BY g.chave ORDER BY g.data) AS pendente_acumulado,
        sum(g.valor) OVER (PARTITION BY g.chave) AS total,
        sum(g.pendente) OVER (PARTITION BY g.chave) AS pendente_total
      FROM grade g
    ),
    soma_dia AS (
      SELECT g.data, sum(g.valor) AS valor, sum(g.pendente) AS pendente,
             max(g.e_pendente) AS e_pendente
      FROM grade g
      WHERE g.visivel
      GROUP BY g.data
    ),
    soma AS (
      SELECT s.data, s.e_pendente,
        sum(s.valor) OVER (ORDER BY s.data) AS acumulado,
        sum(s.pendente) OVER (ORDER BY s.data) AS pendente_acumulado,
        sum(s.valor) OVER () AS total,
        sum(s.pendente) OVER () AS pendente_total
      FROM soma_dia s
    ),
    geral AS (
      SELECT coalesce(sum(valor), 0) AS total, coalesce(sum(pendente), 0) AS pendente
      FROM grade
      WHERE visivel
    )
    SELECT a.chave, a.rotulo, a.tipo, a.forma_id, a.cor, a.ordem, a.visivel, a.data,
           a.acumulado, a.pendente_acumulado, a.e_pendente > 0 AS tem_pendente,
           a.total, a.pendente_total,
           g.total AS geral_total, g.pendente AS geral_pendente
    FROM acumuladas a CROSS JOIN geral g
    UNION ALL
    SELECT '{CHAVE_SOMA}', '{ROTULO_SOMA}', '{CHAVE_SOMA}', NULL::bigint, '{COR_SOMA}', 9, true,
           s.data, s.acumulado, s.pendente_acumulado, s.e_pendente > 0,
           s.total, s.pendente_total, g.total, g.pendente
    FROM soma s CROSS JOIN geral g
    WHERE CAST(:somar AS boolean)
    ORDER BY ordem, rotulo, chave, data
"""

#: Titulares (pessoas) das contas ligadas à Pluggy: só eles têm gasto que a
#: sync traz sozinha, e por isso só eles viram filtro.
_PESSOAS_CONECTADAS = """
    SELECT DISTINCT p.id, p.nome
    FROM contas_pluggy cp
    JOIN contas c ON c.id = cp.conta_id AND c.deleted_em IS NULL
    JOIN pessoas p ON p.id = c.titular_id AND p.deleted_em IS NULL
    WHERE cp.deleted_em IS NULL AND cp.ativo
    ORDER BY p.nome, p.id
"""


_FOLGA = caixa.FOLGA_PAGAMENTO_DIAS
_PROXIMO = MESMO_FECHAMENTO_DIAS

#: Ciclos de fatura (D-29). Os fechamentos de cada cartão vêm, por prioridade,
#: das faturas da Pluggy (a), do ciclo aberto de `caixa.CTES_CICLO_ABERTO` (b)
#: e dos dias cadastrados (c); candidato mais fraco a até 10 dias de um mais
#: firme é descartado. A abertura é o dia seguinte ao fechamento anterior. O
#: pagamento segue o critério do degrau de `caixa.CTES_DEGRAUS`, e um mesmo
#: pagamento só serve a um ciclo do cartão. Os pontos são diários, do começo
#: visível ao fim da linha; no dia do pagamento há dois (antes e depois de zero).
_CICLOS = f"""
    WITH {caixa.CTES_FATURAS},
    {caixa.CTE_PENDENTES},
    {caixa.CTES_CICLO_ABERTO},
    {CTE_CORES_CARTOES},
    movs AS MATERIALIZED (
      SELECT t.forma_pagamento_id AS fid, t.data, t.valor, 0::numeric AS pendente
      FROM vw_transacoes_completa t
      WHERE t.tipo = 'despesa' AND t.data <= {_HOJE}
        AND t.forma_pagamento_id IN (SELECT fid FROM vences)
      UNION ALL
      SELECT p.forma_pagamento_id, p.data, p.valor, p.valor
      FROM pendentes p
      WHERE p.data <= {_HOJE} AND p.forma_pagamento_id IN (SELECT fid FROM vences)
    ),
    cand_a AS (
      SELECT v.fid, fa.fechamento AS fecha, fa.vencimento AS vence,
             'pluggy_fatura' AS o_fecha, 'pluggy_fatura' AS o_vence, 1 AS prio
      FROM vences v
      JOIN faturas fa ON fa.account_id = v.account_id
      WHERE fa.fechamento IS NOT NULL
    ),
    cand_b AS (
      SELECT v.fid, v.fecha,
             coalesce(v.vence, v.fecha + {VENCIMENTO_APOS_FECHAMENTO_DIAS}) AS vence,
             v.o_fecha, coalesce(v.o_vence, 'derivada') AS o_vence, 2 AS prio
      FROM vences v
      WHERE NOT EXISTS (
        SELECT 1 FROM cand_a a WHERE a.fid = v.fid AND abs(a.fecha - v.fecha) <= {_PROXIMO}
      )
    ),
    cand_c AS (
      SELECT v.fid, m.fecha,
             CASE WHEN v.dia_vencimento IS NOT NULL
               THEN {caixa.proxima_apos("m.fecha", "v.dia_vencimento")}
               ELSE m.fecha + {VENCIMENTO_APOS_FECHAMENTO_DIAS} END AS vence,
             'cadastro' AS o_fecha,
             CASE WHEN v.dia_vencimento IS NOT NULL THEN 'cadastro' ELSE 'derivada' END AS o_vence,
             3 AS prio
      FROM vences v
      CROSS JOIN LATERAL (
        SELECT {caixa.no_mes("g.mes::date", "v.dia_fechamento")} AS fecha
        FROM generate_series(
          date_trunc('month', {_INICIO} - interval '2 months')::date,
          date_trunc('month', {_HOJE})::date,
          interval '1 month'
        ) AS g(mes)
      ) m
      WHERE v.dia_fechamento IS NOT NULL
        AND NOT EXISTS (
          SELECT 1 FROM (SELECT * FROM cand_a UNION ALL SELECT * FROM cand_b) o
          WHERE o.fid = v.fid AND abs(o.fecha - m.fecha) <= {_PROXIMO}
        )
    ),
    ordenados AS (
      SELECT x.fid, x.fecha, x.vence, x.o_fecha, x.o_vence,
        lag(x.fecha) OVER w AS fecha_ant,
        lag(x.o_fecha) OVER w AS o_ant,
        max(x.fecha) OVER (PARTITION BY x.fid) AS ultimo
      FROM (
        SELECT * FROM cand_a UNION ALL SELECT * FROM cand_b UNION ALL SELECT * FROM cand_c
      ) x
      WINDOW w AS (PARTITION BY x.fid ORDER BY x.fecha)
    ),
    ciclos AS (
      SELECT o.fid, o.fecha, o.vence, o.o_fecha, o.o_vence,
        coalesce(o.fecha_ant + 1, (o.fecha - interval '1 month')::date + 1) AS abertura,
        CASE WHEN o.fecha_ant IS NULL THEN 'derivada' ELSE o.o_ant END AS o_abertura,
        o.fecha = o.ultimo AS atual
      FROM ordenados o
    ),
    valorados AS (
      SELECT c.*,
        (SELECT coalesce(sum(m.valor), 0) FROM movs m
          WHERE m.fid = c.fid AND m.data >= c.abertura
            AND m.data <= least(c.fecha, {_HOJE})) AS valor,
        (SELECT coalesce(sum(m.pendente), 0) FROM movs m
          WHERE m.fid = c.fid AND m.data >= c.abertura
            AND m.data <= least(c.fecha, {_HOJE})) AS pendente
      FROM ciclos c
    ),
    com_pg AS (
      SELECT c.*, pg.id AS pg_id, pg.data AS pg_data
      FROM valorados c
      JOIN vences v ON v.fid = c.fid
      LEFT JOIN LATERAL (
        SELECT i.id, i.data
        FROM importacao_itens i
        LEFT JOIN formas_pagamento fs ON fs.id = i.forma_pagamento_sugerida_id
        WHERE i.status = 'rejeitado' AND i.deleted_em IS NULL
          AND i.data BETWEEN c.fecha + 1 AND c.vence + {_FOLGA}
          AND (
            (position(CAST(:obs_conta AS text) IN coalesce(i.observacao, '')) > 0
             AND fs.tipo <> 'credito' AND fs.conta_id = v.conta_id)
            OR
            (position(CAST(:obs_cartao AS text) IN coalesce(i.observacao, '')) > 0
             AND i.forma_pagamento_sugerida_id = c.fid)
          )
        ORDER BY
          CASE WHEN position(CAST(:obs_conta AS text) IN coalesce(i.observacao, '')) > 0
                AND fs.tipo <> 'credito' AND fs.conta_id = v.conta_id THEN 0 ELSE 1 END,
          abs(i.valor - c.valor),
          abs(i.data - c.vence)
        LIMIT 1
      ) pg ON true
    ),
    ranqueados AS (
      SELECT c.*,
        row_number() OVER (
          PARTITION BY c.fid, c.pg_id ORDER BY abs(c.pg_data - c.vence), c.fecha
        ) AS pos
      FROM com_pg c
    ),
    pagos AS (
      SELECT r.*, CASE WHEN r.pg_id IS NOT NULL AND r.pos = 1 THEN r.pg_data END AS pago_em
      FROM ranqueados r
    ),
    janela AS (
      SELECT coalesce(
        max(p.vence) FILTER (
          WHERE p.pago_em IS NULL AND p.vence > {_HOJE}
            AND p.vence <= {_HOJE} + {JANELA_VENCIMENTOS_DIAS}
        ),
        {_HOJE}
      ) AS fim
      FROM pagos p
    ),
    linhas AS (
      SELECT p.*, j.fim,
        CASE WHEN p.pago_em IS NOT NULL THEN least(p.pago_em, j.fim)
             ELSE least(greatest({_HOJE}, p.vence), j.fim) END AS fim_linha
      FROM pagos p CROSS JOIN janela j
    ),
    elegiveis AS (
      SELECT l.*, greatest(l.abertura, {_INICIO}) AS comeco
      FROM linhas l
      WHERE l.abertura <= l.fim AND l.fim_linha >= {_INICIO} AND (l.valor > 0 OR l.atual)
        -- Fatura sem pagamento identificado cujo prazo (vencimento + folga)
        -- acabou antes da janela foi paga fora do que a sync enxerga (faturas
        -- de antes da D-22): não vira uma reta atravessando o gráfico.
        AND (l.pago_em IS NOT NULL OR l.vence + {_FOLGA} >= {_INICIO})
    ),
    resultado AS (
      SELECT v.apelido, e.fid, coalesce(cc.cor, 'serie-outros') AS cor,
        e.abertura, e.fecha, e.vence, e.pago_em, e.valor, e.pendente, e.atual,
        CASE WHEN e.fecha > {_HOJE} THEN 'aberta'
             WHEN e.pago_em IS NOT NULL THEN 'paga' ELSE 'fechada' END AS situacao,
        e.o_abertura, e.o_fecha, e.o_vence,
        pt.dia, pt.valor_dia, pt.tracejado, pt.ordem
      FROM elegiveis e
      JOIN vences v ON v.fid = e.fid
      LEFT JOIN cores_cartoes cc ON cc.fid = e.fid
      CROSS JOIN LATERAL (
        SELECT d.dia,
          (SELECT coalesce(sum(m.valor), 0) FROM movs m
            WHERE m.fid = e.fid AND m.data >= e.abertura
              AND m.data <= least(d.dia, e.fecha, {_HOJE})) AS valor_dia,
          d.dia > {_HOJE} AS tracejado, 0 AS ordem
        FROM (
          SELECT e.comeco + g.n AS dia FROM generate_series(0, e.fim_linha - e.comeco) AS g(n)
        ) d
        UNION ALL
        SELECT e.pago_em, 0::numeric, e.pago_em > {_HOJE}, 1
        WHERE e.pago_em IS NOT NULL
      ) pt
    )
    SELECT j.fim, r.*
    FROM janela j
    LEFT JOIN resultado r ON true
    ORDER BY r.apelido, r.fid, r.fecha, r.dia, r.ordem
"""


class GraficosInicioService:
    def __init__(self, session: Session, hoje: date | None = None) -> None:
        self.session = session
        #: Injetável para o teste não depender do relógio.
        self.hoje = hoje or date.today()

    def gastos_30_dias(
        self,
        pessoa_id: int | None = None,
        series: list[str] | None = None,
        somar: bool = False,
    ) -> GastosJanela:
        """As linhas acumuladas dos últimos 30 dias até hoje.

        `series` são as chaves visíveis (nulo = todas); `pessoa_id` filtra pelo
        titular da conta da forma de pagamento.
        """
        inicio = self.hoje - timedelta(days=JANELA_DIAS - 1)
        params: dict[str, Any] = {
            "inicio": inicio,
            "hoje": self.hoje,
            "pessoa_id": pessoa_id,
            "series": series,
            "somar": somar,
        }
        linhas = self.session.execute(text(_GASTOS), params).mappings()

        por_chave: dict[str, SerieGasto] = {}
        total = pendente = Decimal(0)
        for linha in linhas:
            serie = por_chave.get(linha["chave"])
            if serie is None:
                serie = por_chave[linha["chave"]] = SerieGasto(
                    chave=linha["chave"],
                    rotulo=linha["rotulo"],
                    tipo=linha["tipo"],
                    forma_pagamento_id=linha["forma_id"],
                    cor=linha["cor"],
                    visivel=linha["visivel"],
                    total=Decimal(linha["total"]),
                    pendente=Decimal(linha["pendente_total"]),
                    pontos=[],
                )
            serie.pontos.append(
                PontoGasto(
                    data=linha["data"],
                    acumulado=Decimal(linha["acumulado"]),
                    pendente_acumulado=Decimal(linha["pendente_acumulado"]),
                    tem_pendente=linha["tem_pendente"],
                )
            )
            total = Decimal(linha["geral_total"])
            pendente = Decimal(linha["geral_pendente"])

        soma = por_chave.pop(CHAVE_SOMA, None)
        pessoas = [
            PessoaConectada(id=linha["id"], nome=linha["nome"])
            for linha in self.session.execute(text(_PESSOAS_CONECTADAS)).mappings()
        ]
        return GastosJanela(
            inicio=inicio,
            hoje=self.hoje,
            series=list(por_chave.values()),
            soma=soma,
            total=total,
            pendente=pendente,
            pessoas_conectadas=pessoas,
            pessoa_id=pessoa_id,
        )

    def faturas_ciclos(self) -> FaturasCiclos:
        """Um ciclo de fatura por linha, com os pontos diários prontos.

        Do `hoje - 29` ao maior vencimento ainda não pago dos próximos 15 dias
        (ou hoje, se não há).
        """
        inicio = self.hoje - timedelta(days=JANELA_DIAS - 1)
        params: dict[str, Any] = {"inicio": inicio, "hoje": self.hoje, **caixa.parametros()}
        linhas = self.session.execute(text(_CICLOS), params).mappings()

        por_chave: dict[str, CicloFatura] = {}
        fim = self.hoje
        for linha in linhas:
            fim = linha["fim"]
            if linha["fid"] is None:
                continue
            chave = f"ciclo:{linha['fid']}:{linha['fecha'].isoformat()}"
            ciclo = por_chave.get(chave)
            if ciclo is None:
                ciclo = por_chave[chave] = CicloFatura(
                    chave=chave,
                    forma_pagamento_id=linha["fid"],
                    cartao=linha["apelido"],
                    cor=linha["cor"],
                    mes_fatura=linha["vence"].replace(day=1),
                    abertura=linha["abertura"],
                    fechamento=linha["fecha"],
                    vencimento=linha["vence"],
                    pago_em=linha["pago_em"],
                    valor=Decimal(linha["valor"]),
                    pendente=Decimal(linha["pendente"]),
                    atual=linha["atual"],
                    situacao=linha["situacao"],
                    origem_abertura=linha["o_abertura"],
                    origem_fechamento=linha["o_fecha"],
                    origem_vencimento=linha["o_vence"],
                    origem_pagamento="identificado" if linha["pago_em"] else None,
                    pontos=[],
                )
            ciclo.pontos.append(
                PontoCiclo(
                    data=linha["dia"],
                    valor=Decimal(linha["valor_dia"]),
                    tracejado=linha["tracejado"],
                )
            )
        return FaturasCiclos(
            inicio=inicio, hoje=self.hoje, fim=fim, ciclos=list(por_chave.values())
        )
