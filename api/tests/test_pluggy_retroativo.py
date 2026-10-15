"""Retroativo da D-21 nas transações já promovidas da Pluggy.

O cenário imita a importação #4: itens gravados pela sync de antes da D-21
(forma Pix em toda linha de conta, sem categoria) e aprovados na revisão.
Algumas transações o usuário editou — na revisão, antes de aprovar, ou
depois, na tela de transações. O retroativo nunca pode tocar nelas.
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
from app.services.ingestao import IngestaoService
from app.services.retroativo_pluggy import AUTOR, RetroativoPluggyService
from scripts import pluggy_retroativo

CORRENTE, CARTAO = "acc-corrente", "acc-cartao"
GROCERIES = ("11000000", "Groceries")


def _tx(
    id_: str, conta: str, dia: str, valor: str, operacao: str | None, descricao: str
) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "id": id_,
        "accountId": conta,
        "date": f"{dia}T15:00:00Z",
        "amount": float(valor),
        "description": descricao,
        "descriptionRaw": descricao,
        "status": "POSTED",
        "type": "DEBIT",
        "operationType": operacao,
        "currencyCode": "BRL",
        "categoryId": GROCERIES[0],
        "category": GROCERIES[1],
    }
    if conta == CARTAO:
        dados["creditCardMetadata"] = {"cardNumber": "1111", "billId": "f1"}
    return dados


TRANSACOES = [
    # Conta corrente: a operação diz a forma.
    _tx("c-deb", CORRENTE, "2025-04-02", "-12.00", "CARTAO", "MERCADO DEBITO"),
    _tx("c-bol", CORRENTE, "2025-04-03", "-80.00", "BOLETO", "MERCADO BOLETO"),
    _tx("c-pix", CORRENTE, "2025-04-04", "-45.10", "PIX", "MERCADO PIX"),
    # Usuário editou a categoria da transação (pôs e tirou).
    _tx("c-edcat", CORRENTE, "2025-04-05", "-9.00", "CARTAO", "MERCADO EDITADO CAT"),
    # Usuário editou a forma da transação (trocou e voltou).
    _tx("c-edforma", CORRENTE, "2025-04-06", "-7.00", "BOLETO", "MERCADO EDITADO FORMA"),
    # Usuário mexeu na categoria do item na revisão, antes de aprovar.
    _tx("c-revcat", CORRENTE, "2025-04-07", "-6.00", "PIX", "MERCADO REVISAO"),
    # Já entrou com categoria.
    _tx("c-comcat", CORRENTE, "2025-04-08", "-5.00", "PIX", "MERCADO COM CATEGORIA"),
    # Cartão: só categoria, a forma é a do mapeamento.
    _tx("k1", CARTAO, "2025-03-20", "87.90", None, "MERCADO CARTAO"),
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
                        "totalAmount": 87.9,
                    }
                ]
            },
        },
    ]
    return json.dumps({"respostas": respostas}).encode()


def _autor(session: Session, autor: str) -> None:
    session.execute(text("SELECT set_config('app.autor', :a, false)"), {"a": autor})


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
    pix2 = FormaPagamento(
        apelido="Pix Banco A 2", tipo=TipoPagamento.PIX, conta_id=banco.id, titular_id=titular.id
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
    outra = Categoria(nome="Outra", tipo=TipoTransacao.DESPESA)
    session.add_all([pix, pix2, credito, mercado, outra])
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
                sincronizar_desde=date(2025, 3, 1),
            ),
            CategoriaPluggy(
                pluggy_categoria_id=GROCERIES[0],
                pluggy_categoria_nome=GROCERIES[1],
                categoria_id=mercado.id,
            ),
        ]
    )
    importacao = Importacao(
        arquivo_nome="pluggy_20251006T100000.json",
        hash_arquivo="primeira-sync-retroativo",
        arquivo_conteudo=_comprovante(),
        arquivo_tipo="application/json",
        origem="pluggy",
        parser_usado="pluggy_sync",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(importacao)
    session.flush()

    # A sync de antes da D-21: tudo Pix na conta, nada de categoria.
    _autor(session, "sync_pluggy")
    itens: dict[str, ImportacaoItem] = {}
    for t in TRANSACOES:
        dia = date.fromisoformat(t["date"][:10])
        item = ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta=t["descriptionRaw"],
            descricao_original=t["descriptionRaw"],
            data=dia,
            valor=abs(Decimal(str(t["amount"]))),
            tipo_sugerido=TipoTransacao.DESPESA,
            competencia_sugerida=dia.replace(day=1),
            forma_pagamento_sugerida_id=credito.id if t["accountId"] == CARTAO else pix.id,
            categoria_sugerida_id=outra.id if t["id"] == "c-comcat" else None,
            pessoa_sugerida_id=titular.id,
            confianca=Decimal("0.50"),
            origem_sugestao="parser",
            status=StatusItem.PENDENTE,
            id_externo=t["id"],
        )
        session.add(item)
        itens[t["id"]] = item
    session.commit()

    # Na revisão, o usuário pôs e tirou a categoria de c-revcat.
    _autor(session, "usuario")
    itens["c-revcat"].categoria_sugerida_id = outra.id
    session.commit()
    itens["c-revcat"].categoria_sugerida_id = None
    session.commit()

    IngestaoService(session).aprovar([i.id for i in itens.values()])
    session.commit()
    transacoes = {
        id_externo: session.get(Transacao, item.transacao_id) for id_externo, item in itens.items()
    }

    # Depois, na tela de transações: categoria de c-edcat e forma de c-edforma.
    t_cat, t_forma = transacoes["c-edcat"], transacoes["c-edforma"]
    assert t_cat is not None and t_forma is not None
    t_cat.categoria_id = outra.id
    session.commit()
    t_cat.categoria_id = None
    session.commit()
    t_forma.forma_pagamento_id = pix2.id
    session.commit()
    t_forma.forma_pagamento_id = pix.id
    session.commit()
    _autor(session, "teste")

    return {
        "banco": banco,
        "pix": pix,
        "credito": credito,
        "mercado": mercado,
        "outra": outra,
        "itens": itens,
        "t": transacoes,
    }


def _retroativas(session: Session) -> int:
    return int(
        session.scalar(select(func.count()).select_from(Auditoria).where(Auditoria.autor == AUTOR))
        or 0
    )


class TestPlano:
    def test_conta_sem_gravar(self, session: Session, cenario: dict[str, Any]) -> None:
        formas_antes = session.scalar(select(func.count()).select_from(FormaPagamento))
        plano = RetroativoPluggyService(session).planejar()
        session.rollback()

        assert plano.avaliadas == len(TRANSACOES)
        # c-deb, c-bol, c-pix, c-edforma e k1.
        assert plano.ganham_categoria == 5
        assert plano.por_categoria == {"Mercado": 5}
        assert plano.por_origem == {"pluggy": 5}
        # c-deb e c-edcat (débito, forma nova) e c-bol (boleto, forma nova).
        assert plano.mudam_forma == 3
        assert plano.por_forma == {
            ("Pix Banco A (pix)", "nova: Débito Banco A (debito)"): 2,
            ("Pix Banco A (pix)", "nova: Boleto Banco A (boleto)"): 1,
        }
        assert plano.pulados_por_edicao == {"categoria": 2, "forma": 1}
        assert session.scalar(select(func.count()).select_from(FormaPagamento)) == formas_antes
        assert _retroativas(session) == 0

    def test_ids_das_editadas_ficam_de_fora(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        plano = RetroativoPluggyService(session).planejar()
        session.rollback()
        t = cenario["t"]
        por_id = {m.transacao_id: m for m in plano.mudancas}

        for editada in ("c-edcat", "c-revcat"):
            m = por_id.get(t[editada].id)
            assert m is None or m.categoria_id is None, editada
        m = por_id.get(t["c-edforma"].id)
        assert m is not None and not m.muda_forma  # ganha categoria, forma não
        assert t["c-comcat"].id not in por_id
        assert not por_id[t["k1"].id].muda_forma


class TestExecucao:
    def test_grava_so_o_que_ninguem_editou(self, session: Session, cenario: dict[str, Any]) -> None:
        t, mercado, outra, pix = cenario["t"], cenario["mercado"], cenario["outra"], cenario["pix"]
        service = RetroativoPluggyService(session)
        resultado = service.executar(service.planejar())
        session.commit()
        session.expire_all()

        assert resultado["categorias"] == 5
        assert resultado["formas"] == 3
        assert resultado["erros"] == []

        for nome in ("c-deb", "c-bol", "c-pix", "c-edforma", "k1"):
            assert t[nome].categoria_id == mercado.id, nome
        # O que o usuário editou ficou exatamente como ele deixou.
        assert t["c-edcat"].categoria_id is None
        assert t["c-revcat"].categoria_id is None
        assert t["c-edforma"].forma_pagamento_id == pix.id
        assert t["c-comcat"].categoria_id == outra.id

        debito = session.scalar(
            select(FormaPagamento).where(FormaPagamento.tipo == TipoPagamento.DEBITO)
        )
        boleto = session.scalar(
            select(FormaPagamento).where(FormaPagamento.tipo == TipoPagamento.BOLETO)
        )
        assert debito is not None and debito.conta_id == cenario["banco"].id
        assert boleto is not None
        assert t["c-deb"].forma_pagamento_id == debito.id
        assert t["c-edcat"].forma_pagamento_id == debito.id  # a forma não foi editada
        assert t["c-bol"].forma_pagamento_id == boleto.id
        assert t["c-pix"].forma_pagamento_id == pix.id
        assert t["k1"].forma_pagamento_id == cenario["credito"].id

        autores = set(
            session.scalars(
                select(Auditoria.autor).where(
                    Auditoria.tabela == "transacoes",
                    Auditoria.acao == "UPDATE",
                    Auditoria.registro_id == t["c-deb"].id,
                )
            )
        )
        assert autores == {AUTOR}
        tocadas = set(
            session.scalars(
                select(Auditoria.registro_id).where(
                    Auditoria.tabela == "transacoes", Auditoria.autor == AUTOR
                )
            )
        )
        assert t["c-revcat"].id not in tocadas
        assert t["c-comcat"].id not in tocadas

    def test_rodar_de_novo_nao_muda_nada(self, session: Session, cenario: dict[str, Any]) -> None:
        service = RetroativoPluggyService(session)
        service.executar(service.planejar())
        session.commit()

        segundo = RetroativoPluggyService(session).planejar()
        session.rollback()
        assert segundo.mudancas == []
        # A forma que o próprio retroativo trocou não vira "editada".
        assert segundo.pulados_por_edicao == {"categoria": 2, "forma": 1}

    def test_edicao_entre_planejar_e_executar_vence(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        t, outra = cenario["t"], cenario["outra"]
        service = RetroativoPluggyService(session)
        plano = service.planejar()

        t["c-pix"].categoria_id = outra.id
        session.flush()
        resultado = service.executar(plano)
        session.commit()
        session.expire_all()

        assert t["c-pix"].categoria_id == outra.id
        assert resultado["mudou_desde_o_plano"] == 1

    def test_forma_que_colidiria_fica(self, session: Session, cenario: dict[str, Any]) -> None:
        """Já existe débito idêntico: trocar a forma bateria no `hash_dedup`."""
        t = cenario["t"]["c-deb"]
        debito = FormaPagamento(
            apelido="Débito Banco A",
            tipo=TipoPagamento.DEBITO,
            conta_id=cenario["banco"].id,
        )
        session.add(debito)
        session.flush()
        session.add(
            Transacao(
                data=t.data,
                competencia=t.competencia,
                valor=t.valor,
                tipo=TipoTransacao.DESPESA,
                descricao="lançada à mão",
                descricao_original=t.descricao_original,
                forma_pagamento_id=debito.id,
            )
        )
        session.commit()

        plano = RetroativoPluggyService(session).planejar()
        session.rollback()
        assert plano.forma_mantida["colidiria com transação idêntica"] == 1
        m = next(m for m in plano.mudancas if m.transacao_id == t.id)
        assert not m.muda_forma and m.categoria_id is not None


class TestScript:
    def test_simula_por_padrao(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert pluggy_retroativo.main([]) == 0
        saida = capsys.readouterr().out
        assert "SIMULAÇÃO (nada foi gravado)" in saida
        assert "ganhariam categoria: 5" in saida
        assert "Pix Banco A (pix) -> nova: Débito Banco A (debito)" in saida
        assert "puladas por edição do usuário: categoria 2, forma 1" in saida
        assert "MERCADO" not in saida  # nada de descrição no terminal
        assert _retroativas(session) == 0

    def test_executar_grava(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert pluggy_retroativo.main(["--executar"]) == 0
        assert "gravado: categoria em 5, forma em 3" in capsys.readouterr().out
        assert _retroativas(session) > 0
