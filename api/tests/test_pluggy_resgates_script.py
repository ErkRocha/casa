"""Investigação dos resgates da Pluggy: leitura do banco, e nada gravado."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Auditoria,
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
)
from app.services.ingestao import IngestaoService
from scripts import pluggy_resgates

CORRENTE = "acc-corrente"


def _tx(id_: str, dia: str, valor: str, tipo: str, operacao: str) -> dict[str, Any]:
    return {
        "id": id_,
        "accountId": CORRENTE,
        "date": f"{dia}T15:00:00Z",
        "amount": float(valor),
        "description": f"DESCRICAO {id_}",
        "status": "POSTED",
        "type": tipo,
        "operationType": operacao,
        "category": "Proceeds interests and dividends" if tipo == "CREDIT" else None,
    }


TRANSACOES = [
    # Resgate que cobre um pagamento do mesmo valor.
    _tx("r-casa", "2025-04-02", "120.00", "CREDIT", "RESGATE_APLIC_FINANCEIRA"),
    _tx("pag", "2025-04-02", "-120.00", "DEBIT", "PIX"),
    # Rendimento de centavos, sem saída.
    _tx("r-cent", "2025-04-03", "0.02", "CREDIT", "RESGATE_APLIC_FINANCEIRA"),
]


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    banco = Conta(nome="Banco A", tipo=TipoConta.CORRENTE)
    session.add(banco)
    session.flush()
    pix = FormaPagamento(apelido="Pix Banco A", tipo=TipoPagamento.PIX, conta_id=banco.id)
    session.add(pix)
    session.flush()
    session.add(
        ContaPluggy(
            pluggy_item_id="item-1",
            pluggy_account_id=CORRENTE,
            conta_id=banco.id,
            forma_pagamento_id=pix.id,
            sincronizar_desde=date(2025, 3, 1),
        )
    )
    corpo = {
        "respostas": [
            {
                "metodo": "GET",
                "caminho": "/accounts",
                "params": {"itemId": "item-1"},
                "status": 200,
                "corpo": {"results": [{"id": CORRENTE, "itemId": "item-1", "type": "BANK"}]},
            },
            {
                "metodo": "GET",
                "caminho": "/v2/transactions",
                "params": {"accountId": CORRENTE},
                "status": 200,
                "corpo": {"results": TRANSACOES, "next": None},
            },
        ]
    }
    importacao = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-resgates",
        arquivo_conteudo=json.dumps(corpo).encode(),
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(importacao)
    session.flush()
    itens = {}
    for id_, valor, tipo in (
        ("r-casa", "120.00", TipoTransacao.RECEITA),
        ("r-cent", "0.02", TipoTransacao.RECEITA),
    ):
        item = ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta=f"DESCRICAO {id_}",
            descricao_original=f"DESCRICAO {id_}",
            data=date(2025, 4, 2),
            valor=Decimal(valor),
            tipo_sugerido=tipo,
            forma_pagamento_sugerida_id=pix.id,
            status=StatusItem.PENDENTE,
            id_externo=id_,
        )
        session.add(item)
        itens[id_] = item
    session.commit()
    IngestaoService(session).aprovar([itens["r-casa"].id])
    session.commit()
    return {"itens": itens}


def test_carrega_o_gravado_e_casa(session: Session, cenario: dict[str, Any]) -> None:
    movimentos, gravados, contas = pluggy_resgates.carregar(session)
    session.rollback()

    assert gravados["r-casa"].tipo == "receita" and gravados["r-casa"].virou_transacao
    assert gravados["r-cent"].status == "pendente" and not gravados["r-cent"].virou_transacao
    assert "pag" not in gravados  # só operação de aplicação
    assert contas[CORRENTE] == "Banco A (BANK)"

    analise = pluggy_resgates.analisar(movimentos, gravados, contas)
    por_id = {linha.movimento.id: linha.contraparte for linha in analise.linhas}
    assert por_id == {"r-casa": "igual", "r-cent": "sem_contraparte"}


def test_main_so_le(
    session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    antes = session.scalar(select(func.count()).select_from(Auditoria))
    assert pluggy_resgates.main([]) == 0
    saida = capsys.readouterr().out
    assert "conclusão:" in saida and "Nada foi gravado." in saida
    assert "DESCRICAO" not in saida
    assert session.scalar(select(func.count()).select_from(Auditoria)) == antes
