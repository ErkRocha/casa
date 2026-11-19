"""A simulação das notas reais roda de ponta a ponta e não deixa nada gravado."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.db import SessionLocal
from compras.models import Apelido, NotaFiscal, Produto, Variante, VarianteCodigo
from compras.services.produtos import ProdutoService
from scripts.simular_notas_reais import main
from tests.financas_apoio import FinancasFalsa


def _contar(session: Session, modelo: type) -> int:
    return int(session.scalar(select(func.count()).select_from(modelo)) or 0)


def test_simulacao_nao_grava_nada(session: Session) -> None:
    servico = ProdutoService(session)
    servico.obter_ou_criar("suco")
    servico.obter_ou_criar("pão")
    session.commit()
    antes = {
        m: _contar(session, m) for m in (Produto, NotaFiscal, Variante, VarianteCodigo, Apelido)
    }

    linhas: list[str] = []
    assert main(SessionLocal, FinancasFalsa(), linhas.append) == 0

    texto = "\n".join(linhas)
    assert "Nada foi gravado." in texto
    assert "mesma variante de outubro (mercado + código): SIM" in texto
    assert "29,98" in texto
    session.rollback()
    depois = {m: _contar(session, m) for m in antes}
    assert depois == antes
    assert depois[NotaFiscal] == 0
