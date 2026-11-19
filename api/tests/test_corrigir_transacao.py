"""Script de correção: passa pelo service e audita como a API."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import marcar_autor, sessao_com_autor
from app.enums import TipoPagamento, TipoTransacao
from app.models import Transacao
from scripts.corrigir_transacao import corrigir
from tests.test_caixa import _conta, _forma

#: O autor que a API grava (nos testes, "teste"; em produção, "usuario").
AUTOR_API = get_settings().app_autor_padrao


def _despesa(session: Session) -> tuple[int, int, int]:
    nubank = _conta(session, "Nubank")
    mp = _conta(session, "Mercado Pago")
    pix = _forma(session, "Pix Nubank", TipoPagamento.PIX, nubank)
    t = Transacao(
        data=date(2026, 1, 10),
        competencia=date(2026, 1, 1),
        valor=Decimal("834.00"),
        tipo=TipoTransacao.DESPESA,
        descricao="Transferência enviada",
        descricao_original="Transferência enviada",
        forma_pagamento_id=pix.id,
    )
    session.add(t)
    session.commit()
    return t.id, nubank.id, mp.id


def _ultima_auditoria(session: Session, id_: int) -> tuple[str, str | None, str | None]:
    linha = session.execute(
        text(
            "SELECT autor, dados_depois->>'tipo' tipo, dados_depois->>'observacao' obs "
            "FROM auditoria WHERE tabela='transacoes' AND registro_id=:i AND acao='UPDATE' "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"i": id_},
    ).first()
    return (linha.autor, linha.tipo, linha.obs) if linha else ("", None, None)


def _tipo(session: Session, id_: int) -> str:
    session.expire_all()
    return str(
        session.execute(text("SELECT tipo FROM transacoes WHERE id=:i"), {"i": id_}).scalar()
    )


def test_sessao_com_autor_audita_como_a_api(session: Session) -> None:
    id_, *_ = _despesa(session)
    with sessao_com_autor() as s:
        s.execute(text("UPDATE transacoes SET observacao='x' WHERE id=:i"), {"i": id_})
        s.commit()
    assert _ultima_auditoria(session, id_)[0] == AUTOR_API

    with sessao_com_autor("outro_script") as s:
        marcar_autor(s, "outro_script")
        s.execute(text("UPDATE transacoes SET observacao='y' WHERE id=:i"), {"i": id_})
        s.commit()
    assert _ultima_auditoria(session, id_)[0] == "outro_script"


def test_simulacao_nao_grava(session: Session) -> None:
    id_, origem, destino = _despesa(session)
    assert (
        corrigir(["transferencia", str(id_), "--origem", str(origem), "--destino", str(destino)])
        == 0
    )
    assert _tipo(session, id_) == "despesa"
    assert _ultima_auditoria(session, id_) == ("", None, None)


def test_executar_grava_com_o_autor_da_api(session: Session) -> None:
    id_, origem, destino = _despesa(session)
    corrigir(
        [
            "--executar",
            "transferencia",
            str(id_),
            "--origem",
            str(origem),
            "--destino",
            str(destino),
        ]
    )
    assert _tipo(session, id_) == "transferencia"
    assert _ultima_auditoria(session, id_)[:2] == (AUTOR_API, "transferencia")

    corrigir(["--executar", "observacao", str(id_), "Era Pix entre contas da casa."])
    assert _ultima_auditoria(session, id_) == (
        AUTOR_API,
        "transferencia",
        "Era Pix entre contas da casa.",
    )
