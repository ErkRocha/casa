"""`FinancasHttp`: os caminhos e a leitura das respostas de finanças, sem rede."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest

from compras.financas import FinancasHttp, FinancasIndisponivel, FinancasRecusou, NovaDespesa


class Servidor:
    """Troca `httpx.request`: responde por (método, caminho) e guarda os pedidos."""

    def __init__(self, respostas: dict[tuple[str, str], httpx.Response | Exception]) -> None:
        self.respostas = respostas
        self.pedidos: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(self, metodo: str, url: str, **kwargs: Any) -> httpx.Response:
        caminho = url.removeprefix("http://api:8000")
        self.pedidos.append((metodo, caminho, kwargs))
        r = self.respostas.get((metodo, caminho), httpx.Response(404))
        if isinstance(r, Exception):
            raise r
        return httpx.Response(r.status_code, json=r.json() if r.content else None)


def _http(
    monkeypatch: pytest.MonkeyPatch, respostas: dict[Any, Any]
) -> tuple[FinancasHttp, Servidor]:
    servidor = Servidor(respostas)
    monkeypatch.setattr(httpx, "request", servidor)
    return FinancasHttp("http://api:8000/"), servidor


def test_despesas_e_pendentes_pedem_a_janela_e_o_valor(monkeypatch: pytest.MonkeyPatch) -> None:
    http, servidor = _http(
        monkeypatch,
        {
            ("GET", "/transacoes/candidatas-nota"): httpx.Response(
                200,
                json=[
                    {
                        "id": 7,
                        "data": "2026-11-02",
                        "valor": "9.98",
                        "descricao": "MERCADO",
                        "forma_pagamento_apelido": "Cartão",
                        "forma_pagamento_tipo": "credito",
                        "lancada_pela_nota": True,
                    }
                ],
            ),
            ("GET", "/transacoes/pendentes-cartao"): httpx.Response(
                200,
                json=[
                    {
                        "id_externo": "p-1",
                        "data": "2026-11-01",
                        "valor": "9.98",
                        "descricao": "MERCADO",
                        "forma_pagamento_apelido": "Cartão",
                        "forma_pagamento_tipo": "credito",
                    }
                ],
            ),
        },
    )
    (t,) = http.despesas(date(2026, 11, 1), date(2026, 11, 3), Decimal("9.98"))
    assert (t.id, t.valor, t.forma_tipo, t.lancada_pela_nota) == (
        7,
        Decimal("9.98"),
        "credito",
        True,
    )
    (p,) = http.pendentes(date(2026, 11, 1), date(2026, 11, 3), Decimal("9.98"))
    assert (p.id_externo, p.data) == ("p-1", date(2026, 11, 1))
    assert servidor.pedidos[0][2]["params"] == {
        "data_inicio": "2026-11-01",
        "data_fim": "2026-11-03",
        "valor": "9.98",
    }


def test_404_vira_nulo_ou_falso_e_outro_erro_vira_indisponivel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http, _ = _http(
        monkeypatch,
        {
            ("GET", "/transacoes/1/situacao"): httpx.Response(
                200, json={"id": 1, "viva": False, "substituida_por_id": 2}
            ),
            ("GET", "/transacoes/por-pluggy/p-1"): httpx.Response(
                200, json={"id_externo": "p-1", "transacao_id": 5}
            ),
            ("GET", "/transacoes/9"): httpx.Response(500),
            ("GET", "/categorias/10"): httpx.Response(200, json={"tipo": "despesa", "ativo": True}),
            ("GET", "/categorias/11"): httpx.Response(200, json={"tipo": "receita", "ativo": True}),
        },
    )
    situacao = http.situacao(1)
    assert situacao is not None and (situacao.viva, situacao.substituida_por_id) == (False, 2)
    assert http.situacao(2) is None
    assert http.transacao_da_pluggy("p-1") == 5
    assert http.transacao_da_pluggy("p-2") is None
    assert http.pendente_existe("p-2") is False
    assert http.categoria_de_despesa(10) is True
    assert http.categoria_de_despesa(11) is False
    assert http.categoria_de_despesa(12) is False
    with pytest.raises(FinancasIndisponivel):
        http.existe(9)


def test_sem_resposta_e_indisponivel(monkeypatch: pytest.MonkeyPatch) -> None:
    http, _ = _http(monkeypatch, {("GET", "/transacoes/1"): httpx.ConnectError("fora")})
    with pytest.raises(FinancasIndisponivel):
        http.existe(1)


def _despesa() -> NovaDespesa:
    return NovaDespesa(
        data=date(2026, 11, 2),
        valor=Decimal("9.98"),
        descricao="Mercado",
        pessoa_id=None,
        forma_pagamento_id=1,
        categoria_id=10,
        local_nome="MERCADO",
    )


def test_criar_despesa_manda_a_marca_e_devolve_o_id(monkeypatch: pytest.MonkeyPatch) -> None:
    http, servidor = _http(
        monkeypatch, {("POST", "/transacoes"): httpx.Response(201, json={"id": 42})}
    )
    assert http.criar_despesa(_despesa()) == 42
    _, _, kwargs = servidor.pedidos[0]
    assert kwargs["json"]["lancada_pela_nota"] is True
    assert (kwargs["json"]["tipo"], kwargs["json"]["valor"]) == ("despesa", "9.98")
    assert kwargs["params"] == {"local_nome": "MERCADO"}


def test_criar_despesa_recusada_ou_com_erro(monkeypatch: pytest.MonkeyPatch) -> None:
    http, _ = _http(
        monkeypatch, {("POST", "/transacoes"): httpx.Response(422, json={"detail": "forma"})}
    )
    with pytest.raises(FinancasRecusou):
        http.criar_despesa(_despesa())
    http, _ = _http(monkeypatch, {("POST", "/transacoes"): httpx.Response(500)})
    with pytest.raises(FinancasIndisponivel):
        http.criar_despesa(_despesa())
