"""Correção do usuário: despesa que era dinheiro entre contas vira transferência."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.enums import TipoPagamento, TipoTransacao
from app.models import Transacao
from app.services.base import Conflito, NaoEncontrado, RegraViolada
from app.services.transacoes import TransacaoService
from tests.test_caixa import _conta, _forma


def _despesa(session: Session, forma_id: int, **campos: object) -> Transacao:
    t = Transacao(
        data=date(2026, 1, 10),
        competencia=date(2026, 1, 1),
        valor=Decimal("834.00"),
        tipo=TipoTransacao.DESPESA,
        descricao="Transferência enviada",
        descricao_original="Transferência enviada",
        forma_pagamento_id=forma_id,
        **campos,
    )
    session.add(t)
    session.flush()
    return t


def test_despesa_vira_transferencia(session: Session) -> None:
    nubank = _conta(session, "Nubank")
    mp = _conta(session, "Mercado Pago")
    pix = _forma(session, "Pix Nubank", TipoPagamento.PIX, nubank)
    t = _despesa(session, pix.id)
    session.commit()

    r = TransacaoService(session).virar_transferencia(t.id, nubank.id, mp.id)
    session.commit()

    assert r["tipo"] == "transferencia"
    assert r["categoria_id"] is None
    assert r["valor"] == Decimal("834.00")
    linha = session.execute(
        text("SELECT conta_origem_id, conta_destino_id, competencia FROM transacoes WHERE id=:i"),
        {"i": t.id},
    ).one()
    assert (linha.conta_origem_id, linha.conta_destino_id) == (nubank.id, mp.id)
    assert linha.competencia == date(2026, 1, 1)

    # A auditoria guarda a correção (UPDATE com o tipo antes e depois).
    aud = session.execute(
        text(
            "SELECT dados_antes->>'tipo' antes, dados_depois->>'tipo' depois FROM auditoria "
            "WHERE tabela='transacoes' AND registro_id=:i AND acao='UPDATE' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"i": t.id},
    ).one()
    assert (aud.antes, aud.depois) == ("despesa", "transferencia")


def test_recusa_mesma_conta_conta_inexistente_ja_transferencia(session: Session) -> None:
    nubank = _conta(session, "Nubank")
    mp = _conta(session, "Mercado Pago")
    pix = _forma(session, "Pix Nubank", TipoPagamento.PIX, nubank)
    t = _despesa(session, pix.id)
    session.commit()
    svc = TransacaoService(session)

    with pytest.raises(RegraViolada):
        svc.virar_transferencia(t.id, nubank.id, nubank.id)
    with pytest.raises(NaoEncontrado):
        svc.virar_transferencia(t.id, nubank.id, 999_999)
    with pytest.raises(NaoEncontrado):
        svc.virar_transferencia(999_999, nubank.id, mp.id)

    svc.virar_transferencia(t.id, nubank.id, mp.id)
    session.commit()
    with pytest.raises(Conflito):
        svc.virar_transferencia(t.id, nubank.id, mp.id)


def test_recusa_compra_original_de_estorno(session: Session) -> None:
    nubank = _conta(session, "Nubank")
    mp = _conta(session, "Mercado Pago")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, nubank)
    compra = _despesa(session, cartao.id)
    session.add(
        Transacao(
            data=date(2026, 1, 12),
            competencia=date(2026, 1, 1),
            valor=Decimal("834.00"),
            tipo=TipoTransacao.ESTORNO,
            descricao="Estorno",
            descricao_original="Estorno",
            forma_pagamento_id=cartao.id,
            estorno_de_id=compra.id,
        )
    )
    session.commit()

    with pytest.raises(RegraViolada):
        TransacaoService(session).virar_transferencia(compra.id, nubank.id, mp.id)
