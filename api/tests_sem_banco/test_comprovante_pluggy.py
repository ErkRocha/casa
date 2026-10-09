"""Leitura do comprovante JSON da sync (D-16, D-21) — sem banco."""

from __future__ import annotations

import json
from decimal import Decimal

from app.services.comprovante_pluggy import ler_comprovante


def _comprovante() -> bytes:
    """No formato que `SyncPluggyService._comprovante` grava."""
    return json.dumps(
        {
            "gerado_em": "2026-10-06T10:00:00-03:00",
            "contas": [],
            "respostas": [
                {
                    "metodo": "GET",
                    "caminho": "/accounts",
                    "params": {"itemId": "item-1"},
                    "status": 200,
                    "corpo": {
                        "results": [
                            {"id": "acc-b", "itemId": "item-1", "type": "BANK"},
                            {"id": "acc-c", "itemId": "item-1", "type": "CREDIT"},
                        ]
                    },
                },
                {
                    "metodo": "GET",
                    "caminho": "/v2/transactions",
                    "params": {"accountId": "acc-b"},
                    "status": 200,
                    "corpo": {
                        "results": [
                            {
                                "id": "t1",
                                "accountId": "acc-b",
                                "date": "2026-09-01T15:00:00Z",
                                "amount": -45.1,
                                "operationType": "PIX",
                                "category": "Groceries",
                                "categoryId": "11000000",
                            },
                            {"id": "quebrada", "accountId": "acc-b"},
                        ],
                        "next": None,
                    },
                },
                {
                    "metodo": "GET",
                    "caminho": "/bills",
                    "params": {"accountId": "acc-c", "page": "1"},
                    "status": 200,
                    "corpo": {
                        "results": [
                            {
                                "id": "f1",
                                "dueDate": "2026-09-20T00:00:00Z",
                                "totalAmount": 1234.5678,
                            }
                        ]
                    },
                },
            ],
        }
    ).encode()


def test_le_contas_transacoes_e_faturas() -> None:
    c = ler_comprovante(_comprovante())
    assert set(c.contas) == {"acc-b", "acc-c"}
    assert c.contas["acc-c"].e_cartao
    t = c.transacoes["t1"]
    assert (t.operation_type, t.category_id, t.category) == ("PIX", "11000000", "Groceries")
    assert c.conta_da_fatura("f1") == "acc-c"
    assert c.invalidos == 1  # a transação sem data nem valor


def test_dinheiro_chega_em_decimal() -> None:
    c = ler_comprovante(_comprovante())
    assert c.transacoes["t1"].amount == Decimal("-45.1")
    assert c.faturas["f1"].total_amount == Decimal("1234.5678")


def test_comprovante_vazio_ou_quebrado_nao_derruba() -> None:
    assert ler_comprovante(None).transacoes == {}
    assert ler_comprovante(b"").transacoes == {}
    assert ler_comprovante(b"nao e json").invalidos == 1
    assert ler_comprovante(b'{"respostas": "x"}').transacoes == {}
