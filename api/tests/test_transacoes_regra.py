"""Editar a categoria na tela de transações ensina uma regra (D-09, D-21)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.models import Categoria, Pessoa, RegraCategorizacao, Transacao
from app.services.ingestao import _padrao_de


@pytest.fixture
def dados(session: Session) -> dict[str, Any]:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    padaria = Categoria(nome="Padaria", tipo=TipoTransacao.DESPESA)
    pessoa = Pessoa(nome="Titular")
    session.add_all([mercado, padaria, pessoa])
    session.flush()

    def _t(descricao_original: str | None, dia: int, valor: str = "10.00") -> Transacao:
        t = Transacao(
            data=date(2026, 9, dia),
            competencia=date(2026, 9, 1),
            valor=Decimal(valor),
            tipo=TipoTransacao.DESPESA,
            descricao=descricao_original or "Lançamento manual",
            descricao_original=descricao_original,
            categoria_id=mercado.id,
            pessoa_id=pessoa.id,
        )
        session.add(t)
        return t

    importada = _t("PADARIA DO BAIRRO", 1)
    outra = _t("PADARIA DO BAIRRO", 2, "12.00")
    manual = _t(None, 3)
    session.commit()
    return {
        "mercado": mercado,
        "padaria": padaria,
        "pessoa": pessoa,
        "importada": importada,
        "outra": outra,
        "manual": manual,
    }


def _regras(session: Session) -> list[RegraCategorizacao]:
    session.expire_all()
    return list(
        session.scalars(
            select(RegraCategorizacao)
            .where(RegraCategorizacao.deleted_em.is_(None))
            .order_by(RegraCategorizacao.id)
        )
    )


def test_trocar_categoria_cria_regra(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    resposta = client.patch(
        f"/transacoes/{dados['importada'].id}", json={"categoria_id": dados["padaria"].id}
    )
    assert resposta.status_code == 200, resposta.text

    (regra,) = _regras(session)
    assert regra.padrao == _padrao_de("PADARIA DO BAIRRO")
    assert regra.categoria_id == dados["padaria"].id
    assert regra.pessoa_id == dados["pessoa"].id
    assert regra.criada_por == "correcao_automatica"


def test_segunda_correcao_reforca_a_mesma_regra(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    for chave in ("importada", "outra"):
        client.patch(f"/transacoes/{dados[chave].id}", json={"categoria_id": dados["padaria"].id})
    (regra,) = _regras(session)
    assert regra.acertos == 1


def test_mesma_categoria_nao_ensina_nada(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    client.patch(f"/transacoes/{dados['importada'].id}", json={"categoria_id": dados["mercado"].id})
    client.patch(f"/transacoes/{dados['importada'].id}", json={"observacao": "conferido"})
    assert _regras(session) == []


def test_lancamento_manual_nao_vira_regra(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    client.patch(f"/transacoes/{dados['manual'].id}", json={"categoria_id": dados["padaria"].id})
    assert _regras(session) == []


def test_lote_ensina_e_respeita_conjunto(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    resposta = client.post(
        "/transacoes/lote/atribuir",
        json={
            "ids": [dados["importada"].id, dados["outra"].id, dados["manual"].id],
            "categoria_id": dados["padaria"].id,
            "pessoa": "conjunto",
        },
    )
    assert resposta.json() == {"afetadas": 3}

    (regra,) = _regras(session)
    assert regra.categoria_id == dados["padaria"].id
    assert regra.pessoa_id is None  # conjunto (D-03)
    assert regra.acertos == 1  # duas linhas do mesmo estabelecimento


def test_lote_so_de_pessoa_nao_ensina(
    client: TestClient, session: Session, dados: dict[str, Any]
) -> None:
    client.post(
        "/transacoes/lote/atribuir",
        json={"ids": [dados["importada"].id], "pessoa": "conjunto"},
    )
    assert _regras(session) == []
