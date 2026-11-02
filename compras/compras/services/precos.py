"""Histórico de preço por produto e mercado (`vw_preco_produto`)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_PRECOS = """
SELECT v.produto_id, p.nome AS produto_nome, v.mercado_id, m.nome AS mercado_nome,
       v.unidade, v.ultimo_preco, v.ultima_compra_em, v.preco_min, v.preco_max,
       v.preco_medio, v.compras
FROM compras.vw_preco_produto v
JOIN compras.produtos p ON p.id = v.produto_id
JOIN compras.mercados m ON m.id = v.mercado_id
WHERE (CAST(:produto_id AS bigint) IS NULL OR v.produto_id = :produto_id)
  AND (CAST(:mercado_id AS bigint) IS NULL OR v.mercado_id = :mercado_id)
  AND p.deleted_em IS NULL
ORDER BY p.nome_normalizado, v.ultimo_preco, m.nome
LIMIT :limite
"""


class PrecoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar(
        self, produto_id: int | None, mercado_id: int | None, limite: int
    ) -> list[dict[str, Any]]:
        """Uma linha por produto, mercado e unidade; o mais barato primeiro."""
        linhas = self.session.execute(
            text(_PRECOS),
            {"produto_id": produto_id, "mercado_id": mercado_id, "limite": limite},
        )
        return [dict(linha._mapping) for linha in linhas]
