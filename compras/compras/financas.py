"""O que o `compras` pergunta à API de finanças: só leitura, por HTTP.

Nenhuma FK nem consulta direta ao schema de finanças (D-25): a role
`casa_compras` nem alcança aquelas tabelas. A sugestão de transação para uma
nota usa o `GET /transacoes` com os filtros que ele já tem.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import httpx


class FinancasIndisponivel(RuntimeError):
    """A API de finanças não respondeu ou respondeu erro."""


@dataclass(frozen=True, slots=True)
class TransacaoResumo:
    id: int
    data: date
    valor: Decimal
    descricao: str
    forma_pagamento: str | None


class Financas(Protocol):
    def despesas(self, dia: date, valor: Decimal) -> list[TransacaoResumo]:
        """Despesas daquele dia com exatamente aquele valor."""
        ...

    def existe(self, transacao_id: int) -> bool:
        """A transação existe (e não foi apagada) em finanças?"""
        ...


class FinancasHttp:
    def __init__(self, url_base: str, tempo_limite_s: float = 5.0) -> None:
        self.url_base = url_base.rstrip("/")
        self.tempo_limite_s = tempo_limite_s

    def despesas(self, dia: date, valor: Decimal) -> list[TransacaoResumo]:
        params: dict[str, Any] = {
            "data_inicio": dia.isoformat(),
            "data_fim": dia.isoformat(),
            "valor_min": str(valor),
            "valor_max": str(valor),
            "tipos": "despesa",
            "limit": 20,
        }
        try:
            r = httpx.get(f"{self.url_base}/transacoes", params=params, timeout=self.tempo_limite_s)
            r.raise_for_status()
            corpo = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise FinancasIndisponivel(
                f"A API de finanças não respondeu: {type(exc).__name__}."
            ) from exc
        return [
            TransacaoResumo(
                id=int(t["id"]),
                data=date.fromisoformat(t["data"]),
                valor=Decimal(str(t["valor"])),
                descricao=str(t.get("descricao") or ""),
                forma_pagamento=t.get("forma_pagamento_apelido"),
            )
            for t in corpo.get("items", [])
        ]

    def existe(self, transacao_id: int) -> bool:
        try:
            r = httpx.get(f"{self.url_base}/transacoes/{transacao_id}", timeout=self.tempo_limite_s)
        except httpx.HTTPError as exc:
            raise FinancasIndisponivel(
                f"A API de finanças não respondeu: {type(exc).__name__}."
            ) from exc
        if r.status_code == 404:
            return False
        if r.status_code != 200:
            raise FinancasIndisponivel(f"A API de finanças respondeu {r.status_code}.")
        return True
