"""Schema da sync Pluggy (D-16, migration 0005).

Duas barreiras novas: o id externo único no staging, que impede a sync diária
de empilhar o mesmo item de novo, e o mapeamento único por conta da Pluggy.
"""

import os
from datetime import date

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from alembic import command
from app.config import get_settings, url_para_alembic
from app.db import engine
from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento
from app.models import Conta, ContaPluggy, FormaPagamento, Importacao, ImportacaoItem


def _importacao(session: Session, hash_arquivo: str = "h1") -> Importacao:
    imp = Importacao(
        arquivo_nome="pluggy_20261001T060000.json",
        hash_arquivo=hash_arquivo,
        arquivo_tipo="application/json",
        arquivo_conteudo=b'{"results": []}',
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()
    return imp


def _item(session: Session, imp: Importacao, id_externo: str | None, **kwargs: object) -> None:
    session.add(
        ImportacaoItem(importacao_id=imp.id, linha_bruta="MERCADO", id_externo=id_externo, **kwargs)
    )
    session.flush()


def _conta_e_forma(session: Session) -> tuple[Conta, FormaPagamento]:
    conta = Conta(nome="Cartão Nubank", tipo=TipoConta.CARTAO)
    session.add(conta)
    session.flush()
    forma = FormaPagamento(apelido="Nubank", tipo=TipoPagamento.CREDITO, conta_id=conta.id)
    session.add(forma)
    session.flush()
    return conta, forma


def _mapeamento(session: Session, conta: Conta, forma: FormaPagamento) -> ContaPluggy:
    cp = ContaPluggy(
        pluggy_item_id="item-1",
        pluggy_account_id="acc-1",
        conta_id=conta.id,
        forma_pagamento_id=forma.id,
        sincronizar_desde=date(2026, 10, 1),
    )
    session.add(cp)
    session.flush()
    return cp


class TestImportacaoJson:
    def test_importacao_aceita_json_como_arquivo(self, session: Session) -> None:
        """Opção (b) da Fase 5b: o JSON bruto é o comprovante, sem DDL novo."""
        imp = _importacao(session)
        session.commit()
        session.refresh(imp)
        assert imp.arquivo_tipo == "application/json"


class TestIdExterno:
    def test_duplicado_ativo_e_recusado(self, session: Session) -> None:
        imp = _importacao(session)
        _item(session, imp, "tx-1")
        session.commit()

        outra = _importacao(session, hash_arquivo="h2")
        with pytest.raises(IntegrityError):
            _item(session, outra, "tx-1")

    def test_item_rejeitado_continua_bloqueando(self, session: Session) -> None:
        """Rejeitar não pode reabrir a porta para a próxima sync."""
        imp = _importacao(session)
        _item(session, imp, "tx-1", status=StatusItem.REJEITADO)
        session.commit()

        with pytest.raises(IntegrityError):
            _item(session, imp, "tx-1")

    def test_duplicado_aceito_apos_soft_delete(self, session: Session) -> None:
        imp = _importacao(session)
        _item(session, imp, "tx-1")
        session.commit()
        session.execute(
            text("UPDATE importacao_itens SET deleted_em = now() WHERE id_externo = 'tx-1'")
        )
        session.commit()

        _item(session, imp, "tx-1")
        session.commit()  # não levanta

    def test_varios_nulos_convivem(self, session: Session) -> None:
        """Item de PDF não tem id externo e não pode esbarrar em outro."""
        imp = _importacao(session)
        _item(session, imp, None)
        _item(session, imp, None)
        _item(session, imp, None)
        session.commit()  # não levanta


class TestContasPluggy:
    def test_account_id_duplicado_ativo_e_recusado(self, session: Session) -> None:
        conta, forma = _conta_e_forma(session)
        _mapeamento(session, conta, forma)
        session.commit()

        with pytest.raises(IntegrityError):
            _mapeamento(session, conta, forma)

    def test_account_id_aceito_apos_soft_delete(self, session: Session) -> None:
        conta, forma = _conta_e_forma(session)
        cp = _mapeamento(session, conta, forma)
        session.commit()
        session.execute(
            text("UPDATE contas_pluggy SET deleted_em = now() WHERE id = :id"), {"id": cp.id}
        )
        session.commit()

        _mapeamento(session, conta, forma)
        session.commit()  # não levanta

    def test_forma_pagamento_e_obrigatoria(self, session: Session) -> None:
        conta, _ = _conta_e_forma(session)
        with pytest.raises(IntegrityError):
            session.add(
                ContaPluggy(
                    pluggy_item_id="item-1",
                    pluggy_account_id="acc-1",
                    conta_id=conta.id,
                    sincronizar_desde=date(2026, 10, 1),
                )
            )
            session.flush()

    def test_defaults_auditoria_e_atualizado_em(self, session: Session) -> None:
        conta, forma = _conta_e_forma(session)
        cp = _mapeamento(session, conta, forma)
        session.commit()
        session.refresh(cp)
        assert cp.ativo is True
        assert cp.atualizado_em is None

        session.execute(
            text("UPDATE contas_pluggy SET ultimo_sync_em = now() WHERE id = :id"), {"id": cp.id}
        )
        session.commit()
        session.refresh(cp)
        assert cp.atualizado_em is not None

        acoes = session.execute(
            text(
                "SELECT acao FROM auditoria WHERE tabela = 'contas_pluggy' "
                "AND registro_id = :id ORDER BY id"
            ),
            {"id": cp.id},
        ).scalars()
        assert list(acoes) == ["INSERT", "UPDATE"]


class TestRoleInsights:
    """D-11 vale para a tabela nova: lê, não escreve."""

    def test_role_le_e_nao_escreve_em_contas_pluggy(self) -> None:
        engine_role = create_engine(get_settings().insights_database_url)
        try:
            with engine_role.connect() as conexao:
                assert conexao.execute(text("SELECT count(*) FROM contas_pluggy")).scalar() == 0
                with pytest.raises((ProgrammingError, DBAPIError)) as erro:
                    conexao.execute(
                        text(
                            "INSERT INTO contas_pluggy (pluggy_item_id, pluggy_account_id, "
                            "conta_id, forma_pagamento_id, sincronizar_desde) "
                            "VALUES ('i', 'a', 1, 1, current_date)"
                        )
                    )
                conexao.rollback()
        finally:
            engine_role.dispose()

        assert getattr(erro.value.orig, "sqlstate", None) == "42501"
        assert "contas_pluggy" in str(erro.value.orig)


class TestMigration0005:
    def test_downgrade_e_upgrade_de_novo(self) -> None:
        """Ida e volta: 0005 desfaz tudo o que fez e reaplica limpo."""
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["DATABASE_URL"]))
        engine.dispose()

        def _estado() -> tuple[bool, bool, bool]:
            with engine.connect() as conn:
                tabela = conn.execute(text("SELECT to_regclass('contas_pluggy')")).scalar()
                coluna = conn.execute(
                    text(
                        "SELECT 1 FROM information_schema.columns "
                        "WHERE table_name = 'importacao_itens' AND column_name = 'id_externo'"
                    )
                ).scalar()
                indice = conn.execute(
                    text("SELECT to_regclass('uq_importacao_itens_id_externo')")
                ).scalar()
            engine.dispose()
            return tabela is not None, coluna is not None, indice is not None

        try:
            command.downgrade(config, "0004")
            assert _estado() == (False, False, False)
        finally:
            command.upgrade(config, "head")

        assert _estado() == (True, True, True)
        with engine.connect() as conn:
            pode_ler = conn.execute(
                text("SELECT has_table_privilege('casa_insights', 'contas_pluggy', 'SELECT')")
            ).scalar()
        assert pode_ler is True
