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
    GastosJanela,
    PessoaConectada,
    PontoGasto,
    SerieGasto,
)
from app.services import caixa

#: Dias da janela, contando hoje.
JANELA_DIAS = 30
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
