"""Script da proposta de categorias da Pluggy (D-21)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao
from app.models import Auditoria, Categoria, CategoriaPluggy, Importacao
from scripts import pluggy_categorias


def _transacao(id_: str, categoria_id: str, categoria: str, status: str = "POSTED") -> dict:
    return {
        "id": id_,
        "accountId": "acc-1",
        "date": "2026-09-01T15:00:00Z",
        "amount": -10,
        "status": status,
        "category": categoria,
        "categoryId": categoria_id,
    }


@pytest.fixture
def importacao(session: Session, semeado: None) -> Importacao:
    corpo = {
        "respostas": [
            {
                "metodo": "GET",
                "caminho": "/v2/transactions",
                "params": {"accountId": "acc-1"},
                "status": 200,
                "corpo": {
                    "results": [
                        _transacao("t1", "11000000", "Groceries"),
                        _transacao("t2", "11000000", "Groceries"),
                        _transacao("t3", "09010000", "Online shopping"),
                        _transacao("t4", "05070000", "Transfer - PIX"),
                        _transacao("t5", "17010000", "Account fees"),
                        _transacao("t6", "12010000", "Eating out", status="PENDING"),
                    ],
                    "next": None,
                },
            }
        ]
    }
    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-categorias",
        arquivo_conteudo=json.dumps(corpo).encode(),
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.commit()
    return imp


def test_conta_so_posted_e_sem_repetir(session: Session, importacao: Importacao) -> None:
    contagem = pluggy_categorias.contar_categorias(session)
    assert contagem[("11000000", "Groceries")] == 2
    assert ("12010000", "Eating out") not in contagem


def test_sem_aplicar_nao_grava(
    session: Session, importacao: Importacao, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pluggy_categorias.main([]) == 0
    saida = capsys.readouterr().out
    assert "proposta: Alimentação › Mercado" in saida
    assert "AMBÍGUA" in saida and "Online shopping" in saida
    assert "transferência" in saida
    # "Juros e encargos" não está no seed: proposta sem alvo.
    assert "PROPOSTA SEM ALVO" in saida
    assert session.scalar(select(func.count()).select_from(CategoriaPluggy)) == 0


def test_aplicar_grava_so_as_propostas_com_alvo_e_nao_repete(
    session: Session, importacao: Importacao
) -> None:
    assert pluggy_categorias.main(["--aplicar"]) == 0
    mapeadas = list(session.scalars(select(CategoriaPluggy)))
    assert [(m.pluggy_categoria_id, m.pluggy_categoria_nome) for m in mapeadas] == [
        ("11000000", "Groceries")
    ]
    mercado = session.get(Categoria, mapeadas[0].categoria_id)
    assert mercado is not None and mercado.nome == "Mercado"
    autores = set(
        session.scalars(select(Auditoria.autor).where(Auditoria.tabela == "categorias_pluggy"))
    )
    assert autores == {"mapeamento_categorias_pluggy"}

    assert pluggy_categorias.main(["--aplicar"]) == 0
    assert session.scalar(select(func.count()).select_from(CategoriaPluggy)) == 1
