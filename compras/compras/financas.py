"""O que o `compras` pergunta (e, num caso, pede) à API de finanças, por HTTP.

Nenhuma FK nem consulta direta ao schema de finanças (D-25): a role
`casa_compras` nem alcança aquelas tabelas. Quase tudo é leitura: candidatas
a despesa da nota, compras pendentes do cartão (D-28), a transação que a
Pluggy confirmou, o destino de uma transação juntada pela revisão. A única
escrita é "lançar despesa pela nota" (D-33), pelo `POST /transacoes`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

import httpx


class FinancasIndisponivel(RuntimeError):
    """A API de finanças não respondeu ou respondeu erro."""


class FinancasRecusou(RuntimeError):
    """A API de finanças respondeu, mas recusou o pedido (4xx)."""


@dataclass(frozen=True, slots=True)
class TransacaoResumo:
    id: int
    data: date
    valor: Decimal
    descricao: str
    forma_pagamento: str | None
    #: `credito`, `debito`, `pix`, `dinheiro`... (o tipo da forma em finanças).
    forma_tipo: str | None = None
    lancada_pela_nota: bool = False


@dataclass(frozen=True, slots=True)
class PendenteResumo:
    """Compra pendente do cartão (D-28); o id é o da Pluggy."""

    id_externo: str
    data: date
    valor: Decimal
    descricao: str
    forma_pagamento: str | None
    forma_tipo: str | None = None


@dataclass(frozen=True, slots=True)
class SituacaoTransacao:
    id: int
    viva: bool
    substituida_por_id: int | None


@dataclass(frozen=True, slots=True)
class FormaPagamentoResumo:
    id: int
    apelido: str
    tipo: str


@dataclass(frozen=True, slots=True)
class NovaDespesa:
    """O que "lançar despesa pela nota" manda a finanças."""

    data: date
    valor: Decimal
    descricao: str
    pessoa_id: int | None
    forma_pagamento_id: int
    categoria_id: int | None
    local_nome: str | None = None
    observacao: str | None = None


class Financas(Protocol):
    def despesas(self, inicio: date, fim: date, valor: Decimal) -> list[TransacaoResumo]:
        """Despesas de `inicio` a `fim` com exatamente aquele valor."""
        ...

    def pendentes(self, inicio: date, fim: date, valor: Decimal) -> list[PendenteResumo]:
        """Compras pendentes do cartão de `inicio` a `fim` com aquele valor."""
        ...

    def existe(self, transacao_id: int) -> bool:
        """A transação existe (e não foi apagada) em finanças?"""
        ...

    def pendente_existe(self, id_externo: str) -> bool:
        """A compra pendente com este id da Pluggy ainda está em finanças?"""
        ...

    def transacao_da_pluggy(self, id_externo: str) -> int | None:
        """A transação viva que a Pluggy confirmou com este id, se houver."""
        ...

    def situacao(self, transacao_id: int) -> SituacaoTransacao | None:
        """Viva, apagada e para onde a revisão a juntou; nulo se nunca existiu."""
        ...

    def categoria_da_transacao(self, transacao_id: int) -> int | None:
        """A categoria da transação (nulo: sem categoria ou inexistente)."""
        ...

    def categoria_de_despesa(self, categoria_id: int) -> bool:
        """A categoria existe, está ativa e é de despesa?"""
        ...

    def formas_pagamento(self) -> list[FormaPagamentoResumo]:
        """As formas de pagamento ativas."""
        ...

    def criar_despesa(self, despesa: NovaDespesa) -> int:
        """Cria a despesa marcada `lancada_pela_nota`; devolve o id."""
        ...


class FinancasHttp:
    def __init__(self, url_base: str, tempo_limite_s: float = 5.0) -> None:
        self.url_base = url_base.rstrip("/")
        self.tempo_limite_s = tempo_limite_s

    # --- chamadas --------------------------------------------------------------

    def _pedir(self, metodo: str, caminho: str, **kwargs: Any) -> httpx.Response:
        try:
            return httpx.request(
                metodo, f"{self.url_base}{caminho}", timeout=self.tempo_limite_s, **kwargs
            )
        except httpx.HTTPError as exc:
            raise FinancasIndisponivel(
                f"A API de finanças não respondeu: {type(exc).__name__}."
            ) from exc

    def _json(self, resposta: httpx.Response) -> Any:
        if resposta.status_code != 200:
            raise FinancasIndisponivel(f"A API de finanças respondeu {resposta.status_code}.")
        try:
            return resposta.json()
        except ValueError as exc:
            raise FinancasIndisponivel("A API de finanças devolveu uma resposta inválida.") from exc

    def _existe(self, caminho: str) -> dict[str, Any] | None:
        """O corpo se há (200), nulo se 404, erro nos demais."""
        resposta = self._pedir("GET", caminho)
        if resposta.status_code == 404:
            return None
        corpo = self._json(resposta)
        return dict(corpo)

    # --- leitura ---------------------------------------------------------------

    def despesas(self, inicio: date, fim: date, valor: Decimal) -> list[TransacaoResumo]:
        params = {
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "valor": str(valor),
        }
        corpo = self._json(self._pedir("GET", "/transacoes/candidatas-nota", params=params))
        return [
            TransacaoResumo(
                id=int(t["id"]),
                data=date.fromisoformat(t["data"]),
                valor=Decimal(str(t["valor"])),
                descricao=str(t.get("descricao") or ""),
                forma_pagamento=t.get("forma_pagamento_apelido"),
                forma_tipo=t.get("forma_pagamento_tipo"),
                lancada_pela_nota=bool(t.get("lancada_pela_nota")),
            )
            for t in corpo
        ]

    def pendentes(self, inicio: date, fim: date, valor: Decimal) -> list[PendenteResumo]:
        params = {
            "data_inicio": inicio.isoformat(),
            "data_fim": fim.isoformat(),
            "valor": str(valor),
        }
        corpo = self._json(self._pedir("GET", "/transacoes/pendentes-cartao", params=params))
        return [
            PendenteResumo(
                id_externo=str(p["id_externo"]),
                data=date.fromisoformat(p["data"]),
                valor=Decimal(str(p["valor"])),
                descricao=str(p.get("descricao") or ""),
                forma_pagamento=p.get("forma_pagamento_apelido"),
                forma_tipo=p.get("forma_pagamento_tipo"),
            )
            for p in corpo
        ]

    def existe(self, transacao_id: int) -> bool:
        return self._existe(f"/transacoes/{transacao_id}") is not None

    def pendente_existe(self, id_externo: str) -> bool:
        return self._existe(f"/transacoes/pendentes-cartao/{id_externo}") is not None

    def transacao_da_pluggy(self, id_externo: str) -> int | None:
        corpo = self._existe(f"/transacoes/por-pluggy/{id_externo}")
        return None if corpo is None else int(corpo["transacao_id"])

    def situacao(self, transacao_id: int) -> SituacaoTransacao | None:
        corpo = self._existe(f"/transacoes/{transacao_id}/situacao")
        if corpo is None:
            return None
        subst = corpo.get("substituida_por_id")
        return SituacaoTransacao(
            id=int(corpo["id"]),
            viva=bool(corpo["viva"]),
            substituida_por_id=None if subst is None else int(subst),
        )

    def categoria_da_transacao(self, transacao_id: int) -> int | None:
        corpo = self._existe(f"/transacoes/{transacao_id}")
        if corpo is None or corpo.get("categoria_id") is None:
            return None
        return int(corpo["categoria_id"])

    def categoria_de_despesa(self, categoria_id: int) -> bool:
        corpo = self._existe(f"/categorias/{categoria_id}")
        return corpo is not None and corpo.get("tipo") == "despesa" and bool(corpo.get("ativo"))

    def formas_pagamento(self) -> list[FormaPagamentoResumo]:
        corpo = self._json(
            self._pedir("GET", "/formas-pagamento", params={"apenas_ativos": True, "limit": 200})
        )
        return [
            FormaPagamentoResumo(id=int(f["id"]), apelido=str(f["apelido"]), tipo=str(f["tipo"]))
            for f in corpo.get("items", [])
        ]

    # --- escrita ---------------------------------------------------------------

    def criar_despesa(self, despesa: NovaDespesa) -> int:
        corpo = {
            "data": despesa.data.isoformat(),
            "valor": str(despesa.valor),
            "tipo": "despesa",
            "descricao": despesa.descricao,
            "pessoa_id": despesa.pessoa_id,
            "categoria_id": despesa.categoria_id,
            "forma_pagamento_id": despesa.forma_pagamento_id,
            "observacao": despesa.observacao,
            "lancada_pela_nota": True,
        }
        params = {"local_nome": despesa.local_nome} if despesa.local_nome else None
        resposta = self._pedir("POST", "/transacoes", json=corpo, params=params)
        if 400 <= resposta.status_code < 500:
            try:
                detalhe = resposta.json().get("detail")
            except ValueError:
                detalhe = None
            raise FinancasRecusou(
                f"Finanças recusou o lançamento: {detalhe or resposta.status_code}"
            )
        if resposta.status_code != 201:
            raise FinancasIndisponivel(f"A API de finanças respondeu {resposta.status_code}.")
        return int(resposta.json()["id"])
