"""Desfazer importação (D-21): soft delete de transações e itens, com auditoria."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoTransacao
from app.models import Auditoria, Importacao, ImportacaoItem, Transacao


def _importacao(session: Session, hash_: str) -> Importacao:
    imp = Importacao(
        arquivo_nome=f"{hash_}.json",
        hash_arquivo=hash_,
        arquivo_tipo="application/json",
        arquivo_conteudo=b"{}",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()
    return imp


def _transacao(session: Session, imp: Importacao, descricao: str) -> Transacao:
    t = Transacao(
        data=date(2026, 9, 1),
        competencia=date(2026, 9, 1),
        valor=Decimal("10.00"),
        tipo=TipoTransacao.DESPESA,
        descricao=descricao,
        descricao_original=descricao,
        importacao_id=imp.id,
    )
    session.add(t)
    session.flush()
    return t


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    alvo = _importacao(session, "alvo")
    outra = _importacao(session, "outra")
    promovida = _transacao(session, alvo, "MERCADO A")
    alheia = _transacao(session, outra, "MERCADO B")
    session.add_all(
        [
            ImportacaoItem(
                importacao_id=alvo.id,
                linha_bruta="MERCADO A",
                status=StatusItem.APROVADO,
                transacao_id=promovida.id,
                id_externo="t1",
            ),
            ImportacaoItem(
                importacao_id=alvo.id,
                linha_bruta="PIX FULANO",
                status=StatusItem.PENDENTE,
                id_externo="t2",
            ),
            ImportacaoItem(
                importacao_id=outra.id,
                linha_bruta="MERCADO B",
                status=StatusItem.APROVADO,
                transacao_id=alheia.id,
                id_externo="t3",
            ),
        ]
    )
    session.commit()
    return {"alvo": alvo, "outra": outra, "promovida": promovida, "alheia": alheia}


def test_desfaz_so_a_importacao_pedida(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    resposta = client.post(f"/importacoes/{cenario['alvo'].id}/desfazer")
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"transacoes": 1, "itens": 2}

    session.expire_all()
    alvo = session.get(Importacao, cenario["alvo"].id)
    assert alvo is not None
    assert alvo.status is StatusImportacao.CANCELADA
    assert alvo.deleted_em is None  # a importação e o comprovante ficam
    assert session.get(Transacao, cenario["promovida"].id).deleted_em is not None  # type: ignore[union-attr]
    assert session.get(Transacao, cenario["alheia"].id).deleted_em is None  # type: ignore[union-attr]
    vivos = list(
        session.scalars(
            select(ImportacaoItem.id_externo).where(ImportacaoItem.deleted_em.is_(None))
        )
    )
    assert vivos == ["t3"]


def test_cada_linha_fica_na_auditoria_com_autor_proprio(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    client.post(f"/importacoes/{cenario['alvo'].id}/desfazer")
    linhas = session.execute(
        select(Auditoria.tabela, Auditoria.registro_id).where(
            Auditoria.autor == "desfazer_importacao", Auditoria.acao == "UPDATE"
        )
    ).all()
    tabelas = sorted(t for t, _ in linhas)
    assert tabelas == ["importacao_itens", "importacao_itens", "importacoes", "transacoes"]


def test_repetir_nao_apaga_mais_nada(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    client.post(f"/importacoes/{cenario['alvo'].id}/desfazer")
    segunda = client.post(f"/importacoes/{cenario['alvo'].id}/desfazer")
    assert segunda.json() == {"transacoes": 0, "itens": 0}


def test_id_externo_liberado_para_a_proxima_sync(
    client: TestClient, session: Session, cenario: dict[str, Any]
) -> None:
    """Consequência documentada na D-21: o item apagado libera o id."""
    client.post(f"/importacoes/{cenario['alvo'].id}/desfazer")
    session.add(
        ImportacaoItem(
            importacao_id=cenario["outra"].id,
            linha_bruta="MERCADO A",
            status=StatusItem.PENDENTE,
            id_externo="t1",
        )
    )
    session.commit()


def test_importacao_inexistente_404(client: TestClient) -> None:
    assert client.post("/importacoes/9999/desfazer").status_code == 404
