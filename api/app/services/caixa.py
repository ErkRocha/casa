"""Visão de caixa (D-27): o que sai da conta, com a fatura no vencimento.

O total do mês continua o da D-02 (competência). Aqui só mora a distribuição
por dia: cada cartão com compra na competência vira **um degrau** no dia em
que a fatura sai da conta (o pagamento identificado, D-22) ou, enquanto não
saiu, no dia do vencimento. Também mora aqui o bloco das faturas abertas.

Sem schema novo: não há tabela de fatura. As datas da Pluggy são lidas, a cada
pedido, do JSON que a sync guarda em `importacoes.arquivo_conteudo` — só os 3
comprovantes mais recentes, e vale o mais recente de cada fatura/conta (cada
sync traz a lista inteira). Se ficar lento, a saída é uma tabela de faturas
gravada pela sync (decisão e migration próprias).

Tudo é SQL (regra 7): o Python só escolhe parâmetros e monta a resposta. Os
blocos `CTES_*` são fragmentos de `WITH` (sem a palavra `WITH`) para o
chamador compor com as suas próprias CTEs.

Parâmetros dos fragmentos: `:c` (competência, 1º dia do mês), `:obs_conta` e
`:obs_cartao` (textos que marcam o pagamento de fatura, D-22). A consulta das
faturas abertas usa `:hoje`.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_PAGAMENTO_NA_CONTA, OBS_PAGAMENTO_NO_CARTAO
from app.schemas.inicio import FaturaAberta, FaturaMes, PontoEvolucao

#: Quantos comprovantes da Pluggy são lidos.
COMPROVANTES_LIDOS = 3
#: Dias depois do vencimento em que um pagamento ainda é da fatura.
FOLGA_PAGAMENTO_DIAS = 10
#: Cartão com compra nesta janela (dias) entra nas faturas abertas.
JANELA_ABERTAS_DIAS = 90
#: Fechamento de fatura mais antigo que isto (dias) deixa de valer como "desde".
VALIDADE_FECHAMENTO_DIAS = 45
#: Sem fechamento conhecido, a fatura fecha este tanto antes de vencer.
FECHAMENTO_ANTES_DO_VENCIMENTO_DIAS = 10

_C = "CAST(:c AS date)"
_HOJE = "CAST(:hoje AS date)"
_UM_MES = "interval '1 month'"


def parametros() -> dict[str, Any]:
    """Textos que marcam o pagamento de fatura; o resto o chamador fornece."""
    return {"obs_conta": OBS_PAGAMENTO_NA_CONTA, "obs_cartao": OBS_PAGAMENTO_NO_CARTAO}


def _inicio_mes(data: str) -> str:
    return f"date_trunc('month', {data})::date"


def _dias_do_mes(mes: str) -> str:
    return f"extract(day FROM (({mes}) + {_UM_MES} - interval '1 day'))::int"


def _no_mes(mes: str, dia: str) -> str:
    """Data do `dia` no mês que começa em `mes`; dia maior cai no último."""
    return f"(({mes}) + (least({dia}, {_dias_do_mes(mes)}) - 1))"


def _proxima_apos(data: str, dia: str) -> str:
    """Primeira data com esse `dia` do mês (clampado) estritamente depois de `data`."""
    neste = _no_mes(_inicio_mes(data), dia)
    no_seguinte = _no_mes(_inicio_mes(f"({data} + {_UM_MES})"), dia)
    return f"(CASE WHEN {neste} > {data} THEN {neste} ELSE {no_seguinte} END)"


def _mais_recente_ate(data: str, dia: str) -> str:
    """Data mais recente com esse `dia` do mês (clampado) menor ou igual a `data`."""
    neste = _no_mes(_inicio_mes(data), dia)
    no_anterior = _no_mes(_inicio_mes(f"({data} - {_UM_MES})"), dia)
    return f"(CASE WHEN {neste} <= {data} THEN {neste} ELSE {no_anterior} END)"


def _forca(origem: str) -> str:
    """Confiança da origem das datas: quanto maior, mais firme."""
    return (
        f"(CASE {origem} WHEN 'pluggy_conta' THEN 3 WHEN 'cadastro' THEN 2 "
        "WHEN 'pluggy_fatura' THEN 1 END)"
    )


def _resultados(resposta: str) -> str:
    return (
        "jsonb_array_elements(CASE WHEN "
        f"jsonb_typeof({resposta} -> 'corpo' -> 'results') = 'array' "
        f"THEN {resposta} -> 'corpo' -> 'results' ELSE '[]'::jsonb END)"
    )


def _data_do_json(valor: str) -> str:
    """Data civil de um texto ISO da Pluggy: os 10 primeiros caracteres."""
    return f"nullif(left({valor}, 10), '')::date"


#: Fechamento pelo `dia_fechamento` do cadastro, antes do vencimento `venc`: no
#: mesmo mês se o dia de fechamento é menor que o de vencimento, senão no mês
#: anterior.
_FECHAMENTO_CADASTRO = _no_mes(
    "date_trunc('month', d.venc - CASE WHEN d.dia_fechamento "
    "< coalesce(d.dia_vencimento, extract(day FROM d.venc)::int) "
    f"THEN interval '0 month' ELSE {_UM_MES} END)::date",
    "d.dia_fechamento",
)

#: Faturas e conta de crédito da Pluggy, e os cartões com as datas conhecidas.
#: `cartao_conta`: uma linha por cartão (forma `credito`) com `fid`, `apelido`,
#: `ativo`, `conta_id`, `dia_fechamento`, `dia_vencimento`, `account_id`
#: (Pluggy), `cc_fecha`/`cc_vence` (datas da conta de crédito) e `ult_fech`
#: (último `billClosingDate` conhecido).
CTES_FATURAS = f"""
    docs AS MATERIALIZED (
      SELECT row_number() OVER (ORDER BY u.criado_em DESC, u.id DESC) AS ordem,
             convert_from(i.arquivo_conteudo, 'UTF8')::jsonb AS doc
      FROM (
        SELECT id, criado_em FROM importacoes
        WHERE origem = 'pluggy' AND deleted_em IS NULL
          AND arquivo_tipo = 'application/json' AND arquivo_conteudo IS NOT NULL
        ORDER BY criado_em DESC, id DESC
        LIMIT {COMPROVANTES_LIDOS}
      ) u
      JOIN importacoes i ON i.id = u.id
    ),
    respostas AS MATERIALIZED (
      SELECT d.ordem, r.resp
      FROM docs d
      CROSS JOIN LATERAL jsonb_array_elements(
        CASE WHEN jsonb_typeof(d.doc -> 'respostas') = 'array'
          THEN d.doc -> 'respostas' ELSE '[]'::jsonb END
      ) AS r(resp)
    ),
    faturas AS MATERIALIZED (
      SELECT DISTINCT ON (b ->> 'id')
        r.resp -> 'params' ->> 'accountId' AS account_id,
        {_data_do_json("b ->> 'dueDate'")} AS vencimento,
        {_data_do_json("b ->> 'billClosingDate'")} AS fechamento
      FROM respostas r
      CROSS JOIN LATERAL {_resultados("r.resp")} AS b
      WHERE r.resp ->> 'caminho' = '/bills'
        AND b ->> 'id' IS NOT NULL AND b ->> 'dueDate' IS NOT NULL
      ORDER BY b ->> 'id', r.ordem
    ),
    contas_cred AS MATERIALIZED (
      SELECT DISTINCT ON (a ->> 'id')
        a ->> 'id' AS account_id,
        {_data_do_json("a -> 'creditData' ->> 'balanceCloseDate'")} AS fecha,
        {_data_do_json("a -> 'creditData' ->> 'balanceDueDate'")} AS vence
      FROM respostas r
      CROSS JOIN LATERAL {_resultados("r.resp")} AS a
      WHERE r.resp ->> 'caminho' = '/accounts'
        AND a ->> 'type' = 'CREDIT' AND a ->> 'id' IS NOT NULL
      ORDER BY a ->> 'id', r.ordem
    ),
    cartoes AS MATERIALIZED (
      SELECT DISTINCT ON (f.id)
        f.id AS fid, f.apelido, f.ativo, f.conta_id, f.dia_fechamento, f.dia_vencimento,
        cp.pluggy_account_id AS account_id
      FROM formas_pagamento f
      LEFT JOIN contas_pluggy cp ON cp.forma_pagamento_id = f.id AND cp.deleted_em IS NULL
      WHERE f.tipo = 'credito' AND f.deleted_em IS NULL
      ORDER BY f.id, cp.id
    ),
    cartao_conta AS MATERIALIZED (
      SELECT k.*, cc.fecha AS cc_fecha, cc.vence AS cc_vence,
        (SELECT max(fa.fechamento) FROM faturas fa WHERE fa.account_id = k.account_id)
          AS ult_fech
      FROM cartoes k
      LEFT JOIN contas_cred cc ON cc.account_id = k.account_id
    )
"""

#: Degraus do mês `:c`, um por cartão com despesa na competência e alguma data
#: de vencimento (D-27). `degraus`: `fid`, `apelido`, `valor` (soma das
#: compras, não o `totalAmount`), `dia`, `situacao` ('paga'|'a_pagar'),
#: `vencimento`, `pago_em` e `origem` ('pluggy_fatura'|'pluggy_conta'|'cadastro').
CTES_DEGRAUS = (
    CTES_FATURAS
    + f""",
    vencs AS (
      SELECT cm.fid, cm.valor, k.apelido, k.conta_id, k.dia_fechamento, k.dia_vencimento,
             k.cc_fecha, k.cc_vence, k.ult_fech, fb.vencimento AS bill_venc,
             fb.fechamento AS bill_fech
      FROM (
        SELECT t.forma_pagamento_id AS fid, sum(t.valor) AS valor
        FROM vw_transacoes_completa t
        WHERE t.tipo = 'despesa' AND t.competencia = {_C} AND t.forma_pagamento_tipo = 'credito'
        GROUP BY t.forma_pagamento_id
      ) cm
      JOIN cartao_conta k ON k.fid = cm.fid
      LEFT JOIN LATERAL (
        SELECT fa.vencimento, fa.fechamento FROM faturas fa
        WHERE fa.account_id = k.account_id
          AND fa.vencimento >= {_C} AND fa.vencimento < {_C} + {_UM_MES}
        ORDER BY fa.vencimento DESC
        LIMIT 1
      ) fb ON true
    ),
    datas AS (
      SELECT v.*,
        CASE
          WHEN v.bill_venc IS NOT NULL THEN v.bill_venc
          WHEN v.cc_vence >= {_C} AND v.cc_vence < {_C} + {_UM_MES}
               AND (v.ult_fech IS NULL OR v.cc_vence > v.ult_fech) THEN v.cc_vence
          WHEN v.dia_vencimento IS NOT NULL THEN {_no_mes(_C, "v.dia_vencimento")}
        END AS venc,
        CASE
          WHEN v.bill_venc IS NOT NULL THEN 'pluggy_fatura'
          WHEN v.cc_vence >= {_C} AND v.cc_vence < {_C} + {_UM_MES}
               AND (v.ult_fech IS NULL OR v.cc_vence > v.ult_fech) THEN 'pluggy_conta'
          WHEN v.dia_vencimento IS NOT NULL THEN 'cadastro'
        END AS origem
      FROM vencs v
    ),
    janelas AS (
      SELECT d.*,
        coalesce(
          CASE WHEN d.origem = 'pluggy_fatura' THEN d.bill_fech END,
          CASE WHEN d.origem <> 'cadastro' AND d.cc_fecha < d.venc THEN d.cc_fecha END,
          CASE WHEN d.dia_fechamento IS NOT NULL THEN
            {_FECHAMENTO_CADASTRO}
          END,
          d.venc - {FECHAMENTO_ANTES_DO_VENCIMENTO_DIAS}
        ) AS fech
      FROM datas d
      WHERE d.venc IS NOT NULL
    ),
    degraus AS (
      SELECT j.fid, j.apelido, j.valor, j.venc AS vencimento, j.origem, pg.data AS pago_em,
        CASE WHEN pg.data IS NULL THEN 'a_pagar' ELSE 'paga' END AS situacao,
        CASE
          WHEN pg.data IS NULL THEN extract(day FROM j.venc)::int
          WHEN pg.data < {_C} THEN 1
          WHEN pg.data >= {_C} + {_UM_MES} THEN {_dias_do_mes(_C)}
          ELSE extract(day FROM pg.data)::int
        END AS dia
      FROM janelas j
      LEFT JOIN LATERAL (
        SELECT i.data
        FROM importacao_itens i
        LEFT JOIN formas_pagamento fs ON fs.id = i.forma_pagamento_sugerida_id
        WHERE i.status = 'rejeitado' AND i.deleted_em IS NULL
          AND i.data BETWEEN j.fech + 1 AND j.venc + {FOLGA_PAGAMENTO_DIAS}
          AND (
            (position(CAST(:obs_conta AS text) IN coalesce(i.observacao, '')) > 0
             AND fs.tipo <> 'credito' AND fs.conta_id = j.conta_id)
            OR
            (position(CAST(:obs_cartao AS text) IN coalesce(i.observacao, '')) > 0
             AND i.forma_pagamento_sugerida_id = j.fid)
          )
        ORDER BY
          CASE WHEN position(CAST(:obs_conta AS text) IN coalesce(i.observacao, '')) > 0
                AND fs.tipo <> 'credito' AND fs.conta_id = j.conta_id THEN 0 ELSE 1 END,
          abs(i.valor - j.valor),
          abs(i.data - j.venc)
        LIMIT 1
      ) pg ON true
    )
"""
)

_FATURAS_DO_MES = f"""
    WITH {CTES_DEGRAUS}
    SELECT fid, apelido, valor, dia, situacao, vencimento, pago_em, origem
    FROM degraus
    ORDER BY dia, fid
"""

#: Último fechamento: o maior entre o último billClosingDate (se for dos últimos
#: 45 dias) e a data mais recente com `dia_fechamento`. A Pluggy demora a
#: listar a fatura nova, e o cadastro cobre esse intervalo.
_DESDE = (
    f"greatest(CASE WHEN c.bill_ult >= {_HOJE} - {VALIDADE_FECHAMENTO_DIAS} THEN c.bill_ult END, "
    f"CASE WHEN c.dia_fechamento IS NOT NULL THEN "
    f"{_mais_recente_ate(_HOJE, 'c.dia_fechamento')} END)"
)

#: Meses inteiros de `desde0` até hoje, e quantos meses somar a `desde0` para
#: passar de hoje (pelo menos 1).
_MESES_ATE_HOJE = (
    f"((extract(year FROM {_HOJE})::int - extract(year FROM d.desde0)::int) * 12 "
    f"+ extract(month FROM {_HOJE})::int - extract(month FROM d.desde0)::int)"
)
_PASSOS_PARA_PASSAR_HOJE = (
    f"greatest(1, {_MESES_ATE_HOJE} + CASE WHEN d.desde0 + {_MESES_ATE_HOJE} * {_UM_MES} "
    f"> {_HOJE} THEN 0 ELSE 1 END)"
)

#: Uma linha por (cartão, dia) das faturas abertas; `dia` é nulo quando o
#: último fechamento é hoje (sem dias para desenhar).
_FATURAS_ABERTAS = f"""
    WITH {CTES_FATURAS},
    ativos AS MATERIALIZED (
      SELECT k.*,
        (SELECT max(fa.fechamento) FROM faturas fa
          WHERE fa.account_id = k.account_id AND fa.fechamento <= {_HOJE}) AS bill_ult,
        (SELECT fa.vencimento - fa.fechamento FROM faturas fa
          WHERE fa.account_id = k.account_id AND fa.fechamento IS NOT NULL
          ORDER BY fa.fechamento DESC LIMIT 1) AS prazo
      FROM cartao_conta k
      WHERE k.ativo AND EXISTS (
        SELECT 1 FROM vw_transacoes_completa t
        WHERE t.forma_pagamento_id = k.fid AND t.tipo = 'despesa'
          AND t.data >= {_HOJE} - {JANELA_ABERTAS_DIAS} AND t.data <= {_HOJE}
      )
    ),
    desdes AS (
      SELECT c.*, {_DESDE} AS desde0 FROM ativos c
    ),
    -- Sem dia de fechamento nem data da conta, só resta a cadência mensal da
    -- última fatura: avança até o fechamento passar de hoje. Nos outros casos
    -- o fechamento já sai depois de hoje.
    ajustados AS (
      SELECT d.*,
        CASE
          WHEN d.cc_fecha > {_HOJE} OR d.dia_fechamento IS NOT NULL THEN d.desde0
          ELSE (d.desde0 + ({_PASSOS_PARA_PASSAR_HOJE} - 1) * {_UM_MES})::date
        END AS desde
      FROM desdes d
      WHERE d.desde0 IS NOT NULL
    ),
    fechas AS (
      SELECT d.*,
        CASE
          WHEN d.cc_fecha > {_HOJE} THEN d.cc_fecha
          WHEN d.dia_fechamento IS NOT NULL THEN {_proxima_apos("d.desde", "d.dia_fechamento")}
          ELSE (d.desde + {_UM_MES})::date
        END AS fecha,
        CASE
          WHEN d.cc_fecha > {_HOJE} THEN 'pluggy_conta'
          WHEN d.dia_fechamento IS NOT NULL THEN 'cadastro'
          ELSE 'pluggy_fatura'
        END AS o_fecha
      FROM ajustados d
    ),
    vences AS MATERIALIZED (
      SELECT f.*,
        CASE
          WHEN f.cc_vence > f.fecha THEN f.cc_vence
          WHEN f.dia_vencimento IS NOT NULL THEN {_proxima_apos("f.fecha", "f.dia_vencimento")}
          WHEN f.prazo IS NOT NULL THEN f.fecha + f.prazo
        END AS vence,
        CASE
          WHEN f.cc_vence > f.fecha THEN 'pluggy_conta'
          WHEN f.dia_vencimento IS NOT NULL THEN 'cadastro'
          WHEN f.prazo IS NOT NULL THEN 'pluggy_fatura'
        END AS o_vence
      FROM fechas f
    )
    SELECT
      v.fid, v.apelido, v.desde, v.fecha, v.vence,
      CASE
        WHEN v.o_vence IS NULL OR {_forca("v.o_fecha")} <= {_forca("v.o_vence")} THEN v.o_fecha
        ELSE v.o_vence
      END AS origem_datas,
      (SELECT coalesce(sum(t.valor), 0) FROM vw_transacoes_completa t
        WHERE t.forma_pagamento_id = v.fid AND t.tipo = 'despesa'
          AND t.data > v.desde AND t.data <= {_HOJE}) AS valor,
      e.dia, e.acumulado
    FROM vences v
    LEFT JOIN LATERAL (
      SELECT v.desde + g.n AS dia,
        (SELECT coalesce(sum(t.valor), 0) FROM vw_transacoes_completa t
          WHERE t.forma_pagamento_id = v.fid AND t.tipo = 'despesa'
            AND t.data > v.desde AND t.data <= v.desde + g.n) AS acumulado
      FROM generate_series(1, {_HOJE} - v.desde) AS g(n)
    ) e ON true
    ORDER BY v.fecha, v.apelido, v.fid, e.dia
"""


def faturas_do_mes(session: Session, competencia: date) -> list[FaturaMes]:
    """Os degraus do mês, em ordem de dia."""
    linhas = session.execute(text(_FATURAS_DO_MES), {"c": competencia, **parametros()}).mappings()
    return [
        FaturaMes(
            forma_pagamento_id=linha["fid"],
            cartao=linha["apelido"],
            valor=Decimal(linha["valor"]),
            dia=int(linha["dia"]),
            situacao=linha["situacao"],
            vencimento=linha["vencimento"],
            pago_em=linha["pago_em"],
            origem_vencimento=linha["origem"],
        )
        for linha in linhas
    ]


def faturas_abertas(session: Session, hoje: date) -> list[FaturaAberta]:
    """Fatura aberta de cada cartão ativo com compra nos últimos 90 dias.

    Soma pela **data da compra**, desde o último fechamento. `origem_datas` é
    a mais fraca entre as origens do fechamento e do vencimento (conta da
    Pluggy > cadastro > derivada da última fatura da Pluggy).
    """
    abertas: dict[int, FaturaAberta] = {}
    linhas = session.execute(text(_FATURAS_ABERTAS), {"hoje": hoje}).mappings()
    for linha in linhas:
        fatura = abertas.get(linha["fid"])
        if fatura is None:
            fatura = abertas[linha["fid"]] = FaturaAberta(
                forma_pagamento_id=linha["fid"],
                cartao=linha["apelido"],
                valor=Decimal(linha["valor"]),
                desde=linha["desde"],
                fecha=linha["fecha"],
                vence=linha["vence"],
                origem_datas=linha["origem_datas"],
                evolucao=[],
            )
        if linha["dia"] is not None:
            fatura.evolucao.append(
                PontoEvolucao(data=linha["dia"], acumulado=Decimal(linha["acumulado"]))
            )
    return list(abertas.values())
