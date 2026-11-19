"""Migration 0009: tipo estorno, ligação com a compra original e views líquidas (D-34)."""

from __future__ import annotations

import os
from datetime import date
from decimal import Decimal

import pytest
from alembic.config import Config
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from app.config import url_para_alembic
from app.db import engine
from app.enums import TipoTransacao
from app.models import Categoria, Orcamento, Pessoa, Transacao
from app.views import vw_gasto_por_pessoa, vw_orcamento_mes

JUL = date(2026, 7, 1)


def _tx(
    session: Session,
    tipo: TipoTransacao,
    valor: str,
    categoria: Categoria,
    pessoa: Pessoa | None,
    **extra: object,
) -> Transacao:
    t = Transacao(
        data=date(2026, 7, 10),
        competencia=JUL,
        valor=Decimal(valor),
        tipo=tipo,
        descricao="x",
        descricao_original=f"x-{tipo.value}-{valor}",
        categoria_id=categoria.id,
        pessoa_id=pessoa.id if pessoa else None,
        **extra,
    )
    session.add(t)
    session.flush()
    return t


@pytest.fixture
def base(session: Session) -> dict[str, object]:
    pessoa = Pessoa(nome="Ana")
    categoria = Categoria(nome="Compras", tipo=TipoTransacao.DESPESA)
    session.add_all([pessoa, categoria])
    session.flush()
    return {"pessoa": pessoa, "categoria": categoria}


def test_views_somam_o_gasto_liquido(session: Session, base: dict[str, object]) -> None:
    pessoa, categoria = base["pessoa"], base["categoria"]
    assert isinstance(pessoa, Pessoa) and isinstance(categoria, Categoria)
    original = _tx(session, TipoTransacao.DESPESA, "100.00", categoria, pessoa)
    _tx(session, TipoTransacao.ESTORNO, "30.00", categoria, pessoa, estorno_de_id=original.id)
    _tx(session, TipoTransacao.RECEITA, "999.00", categoria, pessoa)
    session.add(Orcamento(categoria_id=categoria.id, competencia=JUL, valor_meta=Decimal("200")))
    session.flush()

    linhas = session.execute(select(vw_gasto_por_pessoa)).all()
    assert [(r.balde_nome, r.total) for r in linhas] == [("Ana", Decimal("70.00"))]

    orcamento = session.execute(select(vw_orcamento_mes)).one()
    assert orcamento.realizado == Decimal("70.00")
    assert orcamento.percentual == Decimal("35.0")


def test_estorno_so_estorno_aponta_para_a_original(
    session: Session, base: dict[str, object]
) -> None:
    pessoa, categoria = base["pessoa"], base["categoria"]
    assert isinstance(pessoa, Pessoa) and isinstance(categoria, Categoria)
    original = _tx(session, TipoTransacao.DESPESA, "100.00", categoria, pessoa)
    with pytest.raises(DBAPIError) as erro:
        _tx(session, TipoTransacao.DESPESA, "5.00", categoria, pessoa, estorno_de_id=original.id)
    assert "ck_transacoes_estorno_de_so_estorno" in str(erro.value)


def test_estorno_nao_tem_conta_de_origem(session: Session, base: dict[str, object]) -> None:
    from app.enums import TipoConta
    from app.models import Conta

    pessoa, categoria = base["pessoa"], base["categoria"]
    assert isinstance(pessoa, Pessoa) and isinstance(categoria, Categoria)
    conta = Conta(nome="C", tipo=TipoConta.CORRENTE)
    session.add(conta)
    session.flush()
    with pytest.raises(DBAPIError) as erro:
        _tx(session, TipoTransacao.ESTORNO, "5.00", categoria, pessoa, conta_origem_id=conta.id)
    assert "ck_transacoes_transferencia_coerente" in str(erro.value)


def _estado() -> tuple[bool, bool]:
    with engine.connect() as conn:
        coluna = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transacoes' AND column_name = 'estorno_de_id'"
            )
        ).scalar()
        total = conn.execute(text("SELECT pg_get_viewdef('vw_gasto_por_pessoa')")).scalar()
    engine.dispose()
    return coluna is not None, "estorno" in str(total)


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["DATABASE_URL"]))
    engine.dispose()
    return config


class TestMigration0009:
    def test_downgrade_e_upgrade_de_novo(self) -> None:
        config = _config()
        try:
            command.downgrade(config, "0008")
            assert _estado() == (False, False)
        finally:
            command.upgrade(config, "head")
        assert _estado() == (True, True)
        with engine.connect() as conn:
            pode_ler = conn.execute(
                text("SELECT has_table_privilege('casa_insights', 'vw_gasto_por_pessoa', 'SELECT')")
            ).scalar()
        assert pode_ler is True

    def test_downgrade_recusa_com_estorno(self, session: Session, base: dict[str, object]) -> None:
        pessoa, categoria = base["pessoa"], base["categoria"]
        assert isinstance(pessoa, Pessoa) and isinstance(categoria, Categoria)
        _tx(session, TipoTransacao.ESTORNO, "30.00", categoria, pessoa)
        session.commit()
        config = _config()
        with pytest.raises(RuntimeError, match="recusado"):
            command.downgrade(config, "0008")
        assert _estado() == (True, True)
