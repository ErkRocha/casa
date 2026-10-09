"""Diagnóstico e reprocessamento da primeira sync (D-21, itens 1 e 7).

A importação aqui imita a que a primeira sync gravou antes da D-21: toda
linha de conta corrente com a forma do mapeamento (Pix), nenhuma categoria
e nada promovido — e o comprovante com o JSON da Pluggy, de onde saem a
operação e a categoria de cada item.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Auditoria,
    Categoria,
    CategoriaPluggy,
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    Transacao,
)
from app.services.base import RegraViolada
from app.services.reprocessamento_pluggy import ReprocessamentoPluggyService
from scripts import pluggy_diagnostico_importacao as diagnostico
from scripts import pluggy_reprocessar

CORRENTE, CARTAO = "acc-corrente", "acc-cartao"
NOTA_GEMEO = (
    "Possível duplicata da Pluggy (no mesmo lote): mesma data, valor e descrição de b-dup2. "
    "Confira no app do banco antes de aprovar os dois."
)


def _tx(
    id_: str,
    conta: str,
    dia: str,
    valor: str,
    operacao: str | None,
    categoria: tuple[str, str] | None,
    descricao: str,
    tipo: str = "DEBIT",
) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "id": id_,
        "accountId": conta,
        "date": f"{dia}T15:00:00Z",
        "amount": float(valor),
        "description": descricao,
        "descriptionRaw": descricao,
        "status": "POSTED",
        "type": tipo,
        "operationType": operacao,
        "currencyCode": "BRL",
    }
    if categoria:
        dados["categoryId"], dados["category"] = categoria
    if conta == CARTAO:
        dados["creditCardMetadata"] = {"cardNumber": "1111", "billId": "f1"}
    return dados


GROCERIES = ("11000000", "Groceries")
TRANSACOES = [
    _tx("b-pix", CORRENTE, "2025-04-02", "-45.10", "PIX", GROCERIES, "MERCADO PIX"),
    _tx("b-deb", CORRENTE, "2025-04-03", "-12.00", "CARTAO", GROCERIES, "MERCADO DEBITO"),
    _tx("b-out", CORRENTE, "2025-04-04", "-10.00", "OUTROS", None, "TARIFA QUALQUER"),
    _tx("b-sem", CORRENTE, "2025-04-05", "-20.00", "PIX", ("09010000", "Online shopping"), "LOJA"),
    _tx("b-dup", CORRENTE, "2025-04-06", "-30.00", "PIX", GROCERIES, "MERCADO GEMEO"),
    _tx("k1", CARTAO, "2025-03-20", "87.90", None, GROCERIES, "MERCADO CARTAO"),
    _tx("k-edit", CARTAO, "2025-03-21", "15.00", None, GROCERIES, "MERCADO EDITADO"),
    _tx("k-ok", CARTAO, "2025-03-22", "5.00", None, GROCERIES, "MERCADO APROVADO"),
]


def _comprovante() -> bytes:
    respostas = [
        {
            "metodo": "GET",
            "caminho": "/accounts",
            "params": {"itemId": "item-1"},
            "status": 200,
            "corpo": {
                "results": [
                    {"id": CORRENTE, "itemId": "item-1", "type": "BANK"},
                    {"id": CARTAO, "itemId": "item-1", "type": "CREDIT"},
                ]
            },
        },
        {
            "metodo": "GET",
            "caminho": "/v2/transactions",
            "params": {"accountId": CORRENTE},
            "status": 200,
            "corpo": {"results": TRANSACOES, "next": None},
        },
        {
            "metodo": "GET",
            "caminho": "/bills",
            "params": {"accountId": CARTAO, "page": "1"},
            "status": 200,
            "corpo": {
                "results": [
                    {
                        "id": "f1",
                        "dueDate": "2025-04-10T00:00:00Z",
                        "billClosingDate": "2025-04-03T00:00:00Z",
                        "totalAmount": 120,
                    }
                ]
            },
        },
    ]
    return json.dumps({"respostas": respostas}).encode()


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    titular = Pessoa(nome="Titular")
    session.add(titular)
    session.flush()
    banco = Conta(nome="Banco A", tipo=TipoConta.CORRENTE, titular_id=titular.id)
    session.add(banco)
    session.flush()
    pix = FormaPagamento(
        apelido="Pix Banco A", tipo=TipoPagamento.PIX, conta_id=banco.id, titular_id=titular.id
    )
    credito = FormaPagamento(
        apelido="Crédito Banco A 1111",
        tipo=TipoPagamento.CREDITO,
        conta_id=banco.id,
        titular_id=titular.id,
        dia_fechamento=3,
        dia_vencimento=10,
    )
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add_all([pix, credito, mercado])
    session.flush()
    session.add_all(
        [
            ContaPluggy(
                pluggy_item_id="item-1",
                pluggy_account_id=CORRENTE,
                conta_id=banco.id,
                forma_pagamento_id=pix.id,
                sincronizar_desde=date(2025, 3, 1),
            ),
            ContaPluggy(
                pluggy_item_id="item-1",
                pluggy_account_id=CARTAO,
                conta_id=banco.id,
                forma_pagamento_id=credito.id,
                sincronizar_desde=date(2025, 3, 4),
            ),
        ]
    )
    importacao = Importacao(
        arquivo_nome="pluggy_20251006T100000.json",
        hash_arquivo="primeira-sync",
        arquivo_conteudo=_comprovante(),
        arquivo_tipo="application/json",
        origem="pluggy",
        parser_usado="pluggy_sync",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(importacao)
    session.flush()

    session.execute(text("SELECT set_config('app.autor', 'sync_pluggy', true)"))
    itens: dict[str, ImportacaoItem] = {}

    def _item(id_externo: str, dia: str, valor: str, forma: FormaPagamento, **extra: Any) -> None:
        descricao = next(
            (t["descriptionRaw"] for t in TRANSACOES if t["id"] == id_externo), "Encargos"
        )
        item = ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta=descricao,
            descricao_original=descricao,
            data=date.fromisoformat(dia),
            valor=Decimal(valor),
            tipo_sugerido=TipoTransacao.DESPESA,
            competencia_sugerida=date.fromisoformat(dia).replace(day=1),
            forma_pagamento_sugerida_id=forma.id,
            pessoa_sugerida_id=titular.id,
            confianca=Decimal("0.50"),
            origem_sugestao="parser",
            status=StatusItem.PENDENTE,
            id_externo=id_externo,
            **extra,
        )
        session.add(item)
        itens[id_externo] = item

    _item("b-pix", "2025-04-02", "45.10", pix)
    _item("b-deb", "2025-04-03", "12.00", pix)
    _item("b-out", "2025-04-04", "10.00", pix)
    _item("b-sem", "2025-04-05", "20.00", pix)
    _item("b-dup", "2025-04-06", "30.00", pix, observacao=NOTA_GEMEO)
    _item("k1", "2025-03-20", "87.90", credito)
    _item("k-edit", "2025-03-21", "15.00", credito)
    _item("k-ok", "2025-03-22", "5.00", credito)
    _item("sumiu", "2025-04-07", "1.00", pix)
    _item("bill:f1:encargos", "2025-04-03", "12.10", credito)
    session.commit()

    # O usuário mexeu em "k-edit" na revisão; "k-ok" ele aprovou.
    session.execute(text("SELECT set_config('app.autor', 'usuario', true)"))
    itens["k-edit"].pessoa_sugerida_id = None
    session.commit()
    from app.services.ingestao import IngestaoService

    IngestaoService(session).aprovar([itens["k-ok"].id])
    session.commit()

    return {
        "importacao": importacao,
        "banco": banco,
        "pix": pix,
        "credito": credito,
        "mercado": mercado,
        "itens": itens,
    }


def _mapear_groceries(session: Session, mercado: Categoria) -> None:
    session.add(
        CategoriaPluggy(
            pluggy_categoria_id="11000000",
            pluggy_categoria_nome="Groceries",
            categoria_id=mercado.id,
        )
    )
    session.commit()


class TestDiagnostico:
    def test_conta_e_responde_a_e_b(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        d = diagnostico.diagnosticar(session, cenario["importacao"].id)

        assert d.itens == 10
        assert d.por_status == {"pendente": 9, "aprovado": 1}
        # k1, k-edit, k-ok e o encargo, que é da fatura f1 do cartão.
        assert (d.cartao_itens, d.cartao_com_forma_do_mapeamento) == (4, 4)
        assert d.conta_itens == 5  # "sumiu" está fora do comprovante
        assert d.conta_por_tipo_de_forma == {"pix": 5}
        assert d.conta_operacao_x_forma[("CARTAO", "pix")] == 1
        assert d.operacoes[("BANK", "PIX")] == 3
        assert d.categorias[GROCERIES] == 6
        assert (d.encargos, d.fora_do_comprovante) == (1, 1)

        diagnostico.imprimir(d)
        saida = capsys.readouterr().out
        assert "CONFIRMADO: os 4 itens de cartão estão com a forma do cartão" in saida
        assert "CONFIRMADO: 5 de 5 itens de conta estão com forma Pix" in saida
        assert "MERCADO" not in saida  # nada de descrição no terminal

    def test_primeira_importacao_pluggy(self, session: Session, cenario: dict[str, Any]) -> None:
        assert diagnostico.primeira_importacao_pluggy(session) == cenario["importacao"].id


class TestPlano:
    def test_simulacao_conta_e_nao_grava(self, session: Session, cenario: dict[str, Any]) -> None:
        _mapear_groceries(session, cenario["mercado"])
        formas_antes = session.scalar(select(func.count()).select_from(FormaPagamento))

        plano = ReprocessamentoPluggyService(session).planejar(cenario["importacao"].id)
        session.rollback()

        assert plano.promoveria == 3  # b-pix, b-deb e k1
        assert plano.na_revisao == {
            "observacao": 1,  # b-out (OUTROS)
            "sem_categoria": 1,  # b-sem (Online shopping, ambígua)
            "possivel_duplicata": 1,  # b-dup: a nota da sync é mantida
            "encargos": 1,
        }
        assert plano.mantidos == {"editado na revisão": 1, "transação fora do comprovante": 1}
        assert [f.apelido for f in plano.formas_novas] == ["Débito Banco A"]
        assert plano.por_forma["nova: Débito Banco A (debito)"] == 1
        assert session.scalar(select(func.count()).select_from(FormaPagamento)) == formas_antes
        assert session.scalar(select(func.count()).select_from(Transacao)) == 1  # só o k-ok

    def test_com_proposta_usa_o_seed_em_memoria(
        self, session: Session, cenario: dict[str, Any], semeado: None
    ) -> None:
        sem = ReprocessamentoPluggyService(session).planejar(cenario["importacao"].id)
        com = ReprocessamentoPluggyService(session).planejar(
            cenario["importacao"].id, com_proposta=True
        )
        session.rollback()

        assert sem.promoveria == 0
        assert com.promoveria == 3
        assert com.proposta_usada == {"11000000": "Groceries"}
        assert session.scalar(select(func.count()).select_from(CategoriaPluggy)) == 0

    def test_importacao_de_pdf_e_recusada(self, session: Session, cenario: dict[str, Any]) -> None:
        cenario["importacao"].origem = "nubank_fatura"
        session.commit()
        with pytest.raises(RegraViolada):
            ReprocessamentoPluggyService(session).planejar(cenario["importacao"].id)


class TestExecucao:
    def test_executa_grava_e_promove_os_limpos(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        _mapear_groceries(session, cenario["mercado"])
        service = ReprocessamentoPluggyService(session)
        resultado = service.executar(service.planejar(cenario["importacao"].id))
        session.commit()

        assert resultado["promovidos"] == 3
        debito = session.scalar(
            select(FormaPagamento).where(FormaPagamento.tipo == TipoPagamento.DEBITO)
        )
        assert debito is not None and debito.conta_id == cenario["banco"].id
        itens = cenario["itens"]
        for chave in ("b-pix", "b-deb", "b-out", "k-edit"):
            session.refresh(itens[chave])
        assert itens["b-deb"].forma_pagamento_sugerida_id == debito.id
        assert itens["b-deb"].status is StatusItem.APROVADO
        assert itens["b-pix"].status is StatusItem.APROVADO
        assert itens["b-out"].status is StatusItem.PENDENTE
        assert itens["b-out"].observacao and "forma de pagamento" in itens["b-out"].observacao
        assert itens["k-edit"].pessoa_sugerida_id is None  # editado: intocado

        promovidas = list(
            session.scalars(
                select(Transacao).where(
                    Transacao.importacao_id == cenario["importacao"].id,
                    Transacao.deleted_em.is_(None),
                )
            )
        )
        assert len(promovidas) == 4  # 3 agora + o k-ok aprovado antes
        autores = set(
            session.scalars(
                select(Auditoria.autor).where(
                    Auditoria.tabela == "transacoes",
                    Auditoria.registro_id.in_([t.id for t in promovidas]),
                )
            )
        )
        assert "reprocessamento_pluggy" in autores

    def test_plano_com_proposta_nao_executa(
        self, session: Session, cenario: dict[str, Any], semeado: None
    ) -> None:
        service = ReprocessamentoPluggyService(session)
        plano = service.planejar(cenario["importacao"].id, com_proposta=True)
        with pytest.raises(RegraViolada, match="proposta"):
            service.executar(plano)


def test_script_simula_por_padrao(
    session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    _mapear_groceries(session, cenario["mercado"])
    assert pluggy_reprocessar.main([]) == 0
    saida = capsys.readouterr().out
    assert "SIMULAÇÃO" in saida
    assert "seriam promovidos: 3" in saida
    assert "nova: Débito Banco A (debito)" in saida
    assert session.scalar(select(func.count()).select_from(Transacao)) == 1
