"""Remoção das compras em aberto da D-23 (D-28).

Cria à mão o estado que a D-23 deixou (item com a marca de aberta, aprovado
ou não, com a transação) e confere o script: simula sem mudar nada, executa
com soft delete, preserva o que o usuário editou, e libera o id da Pluggy para
a versão lançada entrar normalmente.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
)
from app.models import Transacao as TransacaoDb
from app.pluggy.modelos import Conta as ContaRemota
from app.pluggy.modelos import Fatura, Transacao
from app.services.remover_abertas_d28 import (
    AUTOR,
    NOTA_EDITADA,
    RemoverAbertasD28Service,
)
from app.services.sync_pluggy import SyncPluggyService
from scripts import remover_abertas_d28

MARCA = "Compra em aberto na fatura (pendente na Pluggy): resto."
CARTAO = "acc-cartao"
ITEM = "item-1"


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    titular = Pessoa(nome="Titular")
    session.add(titular)
    session.flush()
    banco = Conta(nome="Banco A", tipo=TipoConta.CORRENTE, titular_id=titular.id)
    session.add(banco)
    session.flush()
    credito = FormaPagamento(
        apelido="Crédito Banco A",
        tipo=TipoPagamento.CREDITO,
        conta_id=banco.id,
        titular_id=titular.id,
        dia_fechamento=3,
        dia_vencimento=10,
    )
    session.add(credito)
    session.flush()
    session.add(
        ContaPluggy(
            pluggy_item_id=ITEM,
            pluggy_account_id=CARTAO,
            conta_id=banco.id,
            forma_pagamento_id=credito.id,
            sincronizar_desde=date(2025, 3, 4),
        )
    )
    imp = Importacao(
        arquivo_nome="d23.json",
        hash_arquivo="d23",
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()

    def criar(id_: str, status: StatusItem, *, com_transacao: bool) -> ImportacaoItem:
        transacao_id = None
        if com_transacao:
            tx = TransacaoDb(
                data=date(2025, 5, 10),
                competencia=date(2025, 6, 1),
                valor=Decimal("50.00"),
                tipo=TipoTransacao.DESPESA,
                descricao=f"COMPRA {id_}",
                descricao_original=f"COMPRA {id_}",
                forma_pagamento_id=credito.id,
                importacao_id=imp.id,
            )
            session.add(tx)
            session.flush()
            transacao_id = tx.id
        item = ImportacaoItem(
            importacao_id=imp.id,
            linha_bruta=f"COMPRA {id_}",
            data=date(2025, 5, 10),
            valor=Decimal("50.00"),
            descricao_original=f"COMPRA {id_}",
            tipo_sugerido=TipoTransacao.DESPESA,
            competencia_sugerida=date(2025, 6, 1),
            forma_pagamento_sugerida_id=credito.id,
            status=status,
            transacao_id=transacao_id,
            observacao=MARCA,
            id_externo=id_,
        )
        session.add(item)
        session.flush()
        return item

    itens = {
        "pendente": criar("a-pend", StatusItem.PENDENTE, com_transacao=False),
        "aprovado": criar("a-apr", StatusItem.APROVADO, com_transacao=True),
        "editado": criar("a-edit", StatusItem.APROVADO, com_transacao=True),
    }
    session.commit()
    # O usuário corrige o valor de uma delas na tela de transações.
    session.execute(text("SELECT set_config('app.autor', 'usuario', false)"))
    tx_editada = session.get(TransacaoDb, itens["editado"].transacao_id)
    assert tx_editada is not None
    tx_editada.valor = Decimal("48.00")
    session.commit()
    session.execute(text("SELECT set_config('app.autor', 'teste', false)"))
    return {"itens": itens, "credito": credito}


def _vivos(session: Session) -> set[str | None]:
    session.expire_all()
    return {
        i.id_externo
        for i in session.scalars(select(ImportacaoItem).where(ImportacaoItem.deleted_em.is_(None)))
    }


def _transacoes_vivas(session: Session) -> int:
    session.expire_all()
    return len(list(session.scalars(select(TransacaoDb).where(TransacaoDb.deleted_em.is_(None)))))


class TestService:
    def test_planejar_nao_muda_nada(self, session: Session, cenario: dict[str, Any]) -> None:
        plano = RemoverAbertasD28Service(session).planejar()
        session.rollback()

        assert {linha.id_externo: linha.acao.value for linha in plano.linhas} == {
            "a-pend": "remover",
            "a-apr": "remover",
            "a-edit": "manter (editada)",
        }
        assert _vivos(session) == {"a-pend", "a-apr", "a-edit"}
        assert _transacoes_vivas(session) == 2

    def test_executar_remove_o_nao_editado_e_mantem_o_editado_com_nota(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        service = RemoverAbertasD28Service(session)
        resultado = service.executar(service.planejar())
        session.commit()

        assert resultado == {"removidos": 2, "mantidos": 1, "anotados": 1}
        assert _vivos(session) == {"a-edit"}
        assert _transacoes_vivas(session) == 1
        editado = cenario["itens"]["editado"]
        session.refresh(editado)
        assert editado.status is StatusItem.APROVADO
        assert editado.observacao is not None and NOTA_EDITADA in editado.observacao

        # Fisicamente continuam lá (soft delete), com o autor do script.
        total = session.scalar(text("SELECT count(*) FROM importacao_itens"))
        assert total == 3
        autores = set(
            session.scalars(
                text(
                    "SELECT autor FROM auditoria WHERE tabela = 'importacao_itens' "
                    "AND acao = 'UPDATE'"
                )
            )
        )
        assert AUTOR in autores

    def test_rodar_de_novo_nao_repete_a_nota(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        for _ in range(2):
            service = RemoverAbertasD28Service(session)
            service.executar(service.planejar())
            session.commit()
        editado = cenario["itens"]["editado"]
        session.refresh(editado)
        assert (editado.observacao or "").count(NOTA_EDITADA) == 1

    def test_id_liberado_a_versao_lancada_entra_normal(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        service = RemoverAbertasD28Service(session)
        service.executar(service.planejar())
        session.commit()

        class Leitor:
            def listar_contas(self, item_id: str, tipo: str | None = None) -> list[ContaRemota]:
                return [
                    ContaRemota.model_validate(
                        {"id": CARTAO, "itemId": ITEM, "type": "CREDIT", "subtype": "CREDIT_CARD"}
                    )
                ]

            def listar_transacoes(self, account_id: str, desde: date, ate: date) -> list[Transacao]:
                return [
                    Transacao.model_validate(
                        {
                            "id": "a-pend",
                            "accountId": CARTAO,
                            "date": "2025-05-09T15:00:00Z",
                            "amount": Decimal("50.00"),
                            "description": "COMPRA a-pend",
                            "descriptionRaw": "COMPRA a-pend",
                            "status": "POSTED",
                            "type": "DEBIT",
                            "currencyCode": "BRL",
                            "creditCardMetadata": {"cardNumber": "1111", "billId": "f2"},
                        }
                    )
                ]

            def listar_faturas(self, account_id: str) -> list[Fatura]:
                return [
                    Fatura.model_validate(
                        {
                            "id": "f2",
                            "billClosingDate": "2025-06-03T00:00:00.000Z",
                            "dueDate": "2025-06-10T00:00:00.000Z",
                            "totalAmount": Decimal("50.00"),
                        }
                    )
                ]

        resultado = SyncPluggyService(
            session,
            Leitor(),
            hoje=date(2025, 5, 20),
            agora=lambda: datetime(2025, 5, 20, 12, tzinfo=UTC),
        ).sincronizar()
        session.commit()

        assert resultado.itens_novos == 1
        novo = session.scalar(
            select(ImportacaoItem).where(
                ImportacaoItem.id_externo == "a-pend", ImportacaoItem.deleted_em.is_(None)
            )
        )
        assert novo is not None and "Compra em aberto" not in (novo.observacao or "")


class TestScript:
    def test_simula_por_padrao(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert remover_abertas_d28.main([]) == 0
        saida = capsys.readouterr().out
        assert "SIMULAÇÃO (nada foi gravado)" in saida
        assert "remover (simulação)" in saida
        assert "manter (editada) (simulação)" in saida
        assert "seriam removidos: 2" in saida
        assert _vivos(session) == {"a-pend", "a-apr", "a-edit"}
        assert _transacoes_vivas(session) == 2

    def test_executar_grava(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert remover_abertas_d28.main(["--executar"]) == 0
        saida = capsys.readouterr().out
        assert "EXECUÇÃO" in saida
        assert "removidos: 2" in saida
        assert _vivos(session) == {"a-edit"}
        assert _transacoes_vivas(session) == 1
