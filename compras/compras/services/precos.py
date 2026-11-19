"""Preços (D-33): tudo sai de `vw_preco_variante` e `vw_preco_produto`.

O preço comparável é R$/kg, R$/L ou R$/un, em `numeric` (nunca float). A
agregação (último, mínimo, máximo, média, contagem) é do banco (regra 7);
aqui só se monta a consulta e a forma da resposta.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from compras import tempo
from compras.models import Produto, Variante
from compras.normalizar import normalizar
from compras.schemas import ProdutoLeitura, VarianteLeitura
from compras.services.base import Conflito, NaoEncontrado
from compras.services.mercados import MercadoService
from compras.services.produtos import ProdutoService
from compras.services.variantes import VarianteService

_PRECOS = """
SELECT v.produto_id, p.nome AS produto_nome, v.mercado_id, m.nome AS mercado_nome,
       v.medida_base, v.por, v.ultimo_comparavel, v.ultima_variante_id, v.ultima_compra_em,
       v.preco_min, v.preco_max, v.preco_medio, v.compras, v.sem_comparavel
FROM compras.vw_preco_produto v
JOIN compras.produtos p ON p.id = v.produto_id
JOIN compras.mercados m ON m.id = v.mercado_id
WHERE (CAST(:produto_id AS bigint) IS NULL OR v.produto_id = :produto_id)
  AND (CAST(:mercado_id AS bigint) IS NULL OR v.mercado_id = :mercado_id)
  AND p.deleted_em IS NULL
ORDER BY p.nome_normalizado, v.por NULLS LAST, v.ultimo_comparavel, m.nome
LIMIT :limite
"""

_HISTORICO = """
SELECT v.nota_item_id, v.nota_fiscal_id, v.mercado_id, m.nome AS mercado_nome,
       v.emitida_em AS data, v.quantidade, v.unidade, v.preco_cheio, v.desconto_linha,
       v.desconto_rateado, v.desconto_linha + v.desconto_rateado AS desconto, v.preco_pago,
       v.preco_pago_estimado, v.preco_comparavel, v.por
FROM compras.vw_preco_variante v
LEFT JOIN compras.mercados m ON m.id = v.mercado_id
WHERE v.variante_id = :variante_id
ORDER BY v.emitida_em DESC NULLS LAST, v.nota_fiscal_id DESC, v.nota_item_id DESC
LIMIT :limite OFFSET :offset
"""

_HISTORICO_TOTAIS = """
SELECT count(*) AS total, count(*) FILTER (WHERE preco_comparavel IS NULL) AS sem_comparavel
FROM compras.vw_preco_variante WHERE variante_id = :variante_id
"""

#: A mais recente primeiro; a data vem do dia em São Paulo.
_ULTIMO = "ORDER BY v.emitida_em DESC NULLS LAST, v.nota_fiscal_id DESC, v.nota_item_id DESC"
_DESDE = (
    "(CAST(:desde AS date) IS NULL "
    "OR (v.emitida_em AT TIME ZONE 'America/Sao_Paulo')::date >= CAST(:desde AS date))"
)


def _estatisticas(chave: str) -> str:
    """As agregações do histórico, para o grupo `chave` (uma coluna de `v`)."""
    return f"""
    (array_agg(v.preco_comparavel {_ULTIMO}) FILTER (WHERE v.preco_comparavel IS NOT NULL))[1]
      AS ultimo_comparavel,
    max(v.emitida_em) FILTER (WHERE v.preco_comparavel IS NOT NULL) AS ultima_compra_em,
    min(v.preco_comparavel) AS minimo,
    max(v.preco_comparavel) AS maximo,
    round(avg(v.preco_comparavel), 4) AS media,
    count(v.preco_comparavel) AS compras,
    count(*) FILTER (WHERE v.preco_comparavel IS NULL) AS sem_comparavel,
    (array_agg({chave} {_ULTIMO}) FILTER (WHERE v.preco_comparavel IS NOT NULL))[1] AS ultimo_id
    """


_POR_VARIANTE = f"""
WITH grupo AS (
  SELECT v.variante_id, v.por, {_estatisticas("v.mercado_id")}
  FROM compras.vw_preco_variante v
  WHERE v.produto_id = :produto_id AND {_DESDE}
  GROUP BY v.variante_id, v.por
)
SELECT g.variante_id, va.nome AS variante_nome, g.por, g.ultimo_comparavel, g.ultima_compra_em,
       g.ultimo_id AS ultimo_mercado_id, m.nome AS ultimo_mercado_nome,
       g.minimo, g.maximo, g.media, g.compras, g.sem_comparavel
FROM grupo g
JOIN compras.variantes va ON va.id = g.variante_id
LEFT JOIN compras.mercados m ON m.id = g.ultimo_id
ORDER BY g.por NULLS LAST, g.ultimo_comparavel NULLS LAST, va.nome_normalizado
"""

_POR_MERCADO = f"""
WITH grupo AS (
  SELECT v.mercado_id, v.por, {_estatisticas("v.variante_id")}
  FROM compras.vw_preco_variante v
  WHERE v.produto_id = :produto_id AND v.mercado_id IS NOT NULL AND {_DESDE}
  GROUP BY v.mercado_id, v.por
)
SELECT g.mercado_id, m.nome AS mercado_nome, g.por, g.ultimo_comparavel, g.ultima_compra_em,
       g.ultimo_id AS ultima_variante_id, va.nome AS ultima_variante_nome,
       g.minimo, g.maximo, g.media, g.compras, g.sem_comparavel
FROM grupo g
JOIN compras.mercados m ON m.id = g.mercado_id
LEFT JOIN compras.variantes va ON va.id = g.ultimo_id
ORDER BY g.por NULLS LAST, g.ultimo_comparavel NULLS LAST, m.nome
"""

#: A variante de menor último comparável, por unidade.
_MAIS_BARATA = f"""
WITH grupo AS (
  SELECT v.variante_id, v.por, {_estatisticas("v.mercado_id")}
  FROM compras.vw_preco_variante v
  WHERE v.produto_id = :produto_id AND {_DESDE}
  GROUP BY v.variante_id, v.por
)
SELECT DISTINCT ON (g.por) g.por, g.variante_id, va.nome AS variante_nome,
       g.ultimo_id AS mercado_id, m.nome AS mercado_nome,
       g.ultimo_comparavel, g.ultima_compra_em
FROM grupo g
JOIN compras.variantes va ON va.id = g.variante_id
LEFT JOIN compras.mercados m ON m.id = g.ultimo_id
WHERE g.ultimo_comparavel IS NOT NULL
ORDER BY g.por, g.ultimo_comparavel, g.ultima_compra_em DESC NULLS LAST
"""

_SEM_COMPARAVEL_PRODUTO = f"""
SELECT count(*) FROM compras.vw_preco_variante v
WHERE v.produto_id = :produto_id AND v.preco_comparavel IS NULL AND {_DESDE}
"""

_DO_MERCADO = f"""
WITH grupo AS (
  SELECT v.produto_id, v.por, {_estatisticas("v.variante_id")}
  FROM compras.vw_preco_variante v
  WHERE v.mercado_id = CAST(:mercado_id AS bigint) AND {_DESDE}
  GROUP BY v.produto_id, v.por
), com_media AS (
  SELECT g.*,
    (SELECT round(avg(o.preco_comparavel), 4)
       FROM compras.vw_preco_variante o
       WHERE o.produto_id = g.produto_id AND o.por = g.por
         AND o.mercado_id IS DISTINCT FROM CAST(:mercado_id AS bigint)
         AND (CAST(:desde AS date) IS NULL
              OR (o.emitida_em AT TIME ZONE 'America/Sao_Paulo')::date >= CAST(:desde AS date))
    ) AS media_outros_mercados
  FROM grupo g
)
SELECT c.produto_id, p.nome AS produto_nome, c.por, c.ultimo_comparavel, c.ultima_compra_em,
       c.media_outros_mercados,
       CASE WHEN c.media_outros_mercados > 0 AND c.ultimo_comparavel IS NOT NULL
         THEN round((c.ultimo_comparavel - c.media_outros_mercados)
                    / c.media_outros_mercados * 100, 1) END AS diferenca_percentual,
       c.compras, c.sem_comparavel,
       count(*) OVER () AS total
FROM com_media c
JOIN compras.produtos p ON p.id = c.produto_id
ORDER BY p.nome_normalizado, c.por NULLS LAST
LIMIT :limite OFFSET :offset
"""

_ONDE_MAIS_BARATO = """
WITH ultimo AS (
  SELECT DISTINCT ON (v.mercado_id, v.por)
         v.mercado_id, v.por, v.variante_id, v.preco_comparavel, v.emitida_em
  FROM compras.vw_preco_variante v
  WHERE v.produto_id = :produto_id
    AND v.mercado_id IS NOT NULL
    AND v.preco_comparavel IS NOT NULL
    AND (v.emitida_em AT TIME ZONE 'America/Sao_Paulo')::date
          >= CAST(:hoje AS date) - CAST(:dias AS integer)
  ORDER BY v.mercado_id, v.por, v.emitida_em DESC NULLS LAST, v.nota_fiscal_id DESC,
           v.nota_item_id DESC
)
SELECT row_number() OVER (PARTITION BY u.por ORDER BY u.preco_comparavel, u.emitida_em DESC)
         AS posicao,
       u.por, u.mercado_id, m.nome AS mercado_nome, u.variante_id, va.nome AS variante_nome,
       u.preco_comparavel AS comparavel, u.emitida_em AS data,
       CAST(:hoje AS date) - (u.emitida_em AT TIME ZONE 'America/Sao_Paulo')::date AS dias_atras
FROM ultimo u
JOIN compras.mercados m ON m.id = u.mercado_id
JOIN compras.variantes va ON va.id = u.variante_id
ORDER BY u.por, u.preco_comparavel, u.emitida_em DESC
"""


def _dicts(linhas: Any) -> list[dict[str, Any]]:
    return [dict(linha._mapping) for linha in linhas]


def _com_comparavel(linha: dict[str, Any]) -> dict[str, Any]:
    """`{preco_comparavel, por}` vira `comparavel: {valor, por}` (ou nulo)."""
    valor = linha.pop("preco_comparavel")
    por = linha.pop("por")
    linha["comparavel"] = {"valor": valor, "por": por} if valor is not None else None
    return linha


class PrecoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar(
        self, produto_id: int | None, mercado_id: int | None, limite: int
    ) -> list[dict[str, Any]]:
        """Uma linha por produto, mercado e medida; o mais barato primeiro."""
        return _dicts(
            self.session.execute(
                text(_PRECOS),
                {"produto_id": produto_id, "mercado_id": mercado_id, "limite": limite},
            )
        )

    def historico_da_variante(self, variante: Variante, limite: int, offset: int) -> dict[str, Any]:
        parametros = {"variante_id": variante.id}
        totais = self.session.execute(text(_HISTORICO_TOTAIS), parametros).one()
        itens = _dicts(
            self.session.execute(
                text(_HISTORICO), {**parametros, "limite": limite, "offset": offset}
            )
        )
        servico = VarianteService(self.session)
        return {
            "variante": VarianteLeitura.de(variante, servico.codigos([variante.id])[variante.id]),
            "total": totais.total,
            "limite": limite,
            "offset": offset,
            "sem_comparavel": totais.sem_comparavel,
            "itens": [_com_comparavel(i) for i in itens],
        }

    def do_produto(self, produto_id: int, desde: date | None) -> dict[str, Any]:
        produto = ProdutoService(self.session).get(produto_id)
        parametros = {"produto_id": produto.id, "desde": desde}
        return {
            "produto_id": produto.id,
            "produto_nome": produto.nome,
            "por_variante": _dicts(self.session.execute(text(_POR_VARIANTE), parametros)),
            "por_mercado": _dicts(self.session.execute(text(_POR_MERCADO), parametros)),
            "mais_barata": _dicts(self.session.execute(text(_MAIS_BARATA), parametros)),
            "sem_comparavel": self.session.execute(
                text(_SEM_COMPARAVEL_PRODUTO), parametros
            ).scalar_one(),
        }

    def do_mercado(
        self, mercado_id: int, desde: date | None, limite: int, offset: int
    ) -> dict[str, Any]:
        mercado = MercadoService(self.session).get(mercado_id)
        linhas = _dicts(
            self.session.execute(
                text(_DO_MERCADO),
                {"mercado_id": mercado.id, "desde": desde, "limite": limite, "offset": offset},
            )
        )
        total = linhas[0].pop("total") if linhas else 0
        for linha in linhas[1:]:
            linha.pop("total")
        return {
            "mercado_id": mercado.id,
            "mercado_nome": mercado.nome,
            "total": total,
            "limite": limite,
            "offset": offset,
            "itens": linhas,
        }

    def produto_pelo_nome(self, busca: str) -> Produto:
        """O produto pelo nome, sem caixa nem acento. Igual ao nome inteiro vale;
        senão, o único que contém o texto. Mais de um: 409 com os candidatos."""
        termo = normalizar(busca)
        vivos = select(Produto).where(Produto.deleted_em.is_(None))
        exato = self.session.scalar(vivos.where(Produto.nome_normalizado == termo))
        if exato is not None:
            return exato
        achados = list(
            self.session.scalars(
                vivos.where(Produto.nome_normalizado.contains(termo, autoescape=True)).order_by(
                    Produto.nome_normalizado
                )
            )
        )
        if not achados:
            raise NaoEncontrado("produto", busca)
        if len(achados) > 1:
            raise Conflito(
                f'"{busca}" serve a {len(achados)} produtos: escolha um (produto_id).',
                {
                    "candidatos": [
                        ProdutoLeitura.de(p).model_dump(mode="json") for p in achados[:20]
                    ]
                },
            )
        return achados[0]

    def onde_mais_barato(
        self, produto_id: int | None, busca: str | None, dias: int
    ) -> dict[str, Any]:
        produto = (
            ProdutoService(self.session).get(produto_id)
            if produto_id is not None
            else self.produto_pelo_nome(busca or "")
        )
        ranking = _dicts(
            self.session.execute(
                text(_ONDE_MAIS_BARATO),
                {"produto_id": produto.id, "dias": dias, "hoje": tempo.hoje()},
            )
        )
        return {
            "produto_id": produto.id,
            "produto_nome": produto.nome,
            "dias": dias,
            "ranking": ranking,
        }
