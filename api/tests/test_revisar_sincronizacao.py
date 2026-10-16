"""Resumo da revisão, estado da sincronização e conta da forma (D-22)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_PAGAMENTO_NO_CARTAO
from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Categoria,
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Transacao,
)

GEMEO = "Possível duplicata da Pluggy (no mesmo lote): mesma data... aprovar os dois."


def _importacao(session: Session, hash_: str, *, apagada: bool = False) -> Importacao:
    imp = Importacao(
        arquivo_nome=f"{hash_}.json",
        hash_arquivo=hash_,
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()
    if apagada:
        imp.deleted_em = func.now()
    return imp


def _item(session: Session, imp: Importacao, **campos: object) -> None:
    session.add(ImportacaoItem(importacao_id=imp.id, linha_bruta="LINHA", **campos))


def test_resumo_da_revisao_por_motivo(client: TestClient, session: Session) -> None:
    categoria = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add(categoria)
    session.flush()
    imp = _importacao(session, "viva")
    pendente = {"status": StatusItem.PENDENTE}
    transferencia = {**pendente, "tipo_sugerido": TipoTransacao.TRANSFERENCIA}
    _item(session, imp, observacao=GEMEO, categoria_sugerida_id=categoria.id, **pendente)
    _item(session, imp, observacao=GEMEO, **pendente)
    _item(session, imp, id_externo="bill:f1:encargos", observacao="deduzido", **pendente)
    _item(session, imp, observacao=OBS_PAGAMENTO_NO_CARTAO, **transferencia)
    _item(session, imp, observacao="pagamento de fatura na conta", **transferencia)
    _item(session, imp, observacao="Competência estimada", **pendente)
    _item(session, imp, **pendente)  # sem categoria
    _item(session, imp, categoria_sugerida_id=categoria.id, **pendente)  # outros
    # Não contam: rejeitado, apagado e de importação apagada.
    _item(session, imp, status=StatusItem.REJEITADO)
    _item(session, imp, deleted_em=datetime(2026, 10, 1, tzinfo=UTC), **pendente)
    _item(session, _importacao(session, "apagada", apagada=True), **pendente)
    session.commit()

    resposta = client.get("/revisar/resumo")
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["total"] == 8
    assert [(m["motivo"], m["quantidade"]) for m in corpo["motivos"]] == [
        ("possivel_duplicata", 2),
        ("encargos", 1),
        ("pagamento_fatura_cartao", 1),
        ("transferencia", 1),
        ("observacao", 1),
        ("sem_categoria", 1),
        ("outros", 1),
    ]
    assert corpo["motivos"][0]["rotulo"]


def test_revisao_vazia(client: TestClient) -> None:
    assert client.get("/revisar/resumo").json() == {"total": 0, "motivos": []}


def test_estado_da_sincronizacao(client: TestClient, session: Session) -> None:
    assert client.get("/sincronizacao/estado").json() == {
        "ultima_atualizacao": None,
        "conexoes_ativas": 0,
        "automatica": False,
    }

    conta = Conta(nome="Banco", tipo=TipoConta.CORRENTE)
    session.add(conta)
    session.flush()
    forma = FormaPagamento(apelido="Pix Banco", tipo=TipoPagamento.PIX, conta_id=conta.id)
    session.add(forma)
    session.flush()

    def mapa(conta_pluggy: str, quando: datetime, *, ativo: bool = True) -> None:
        session.add(
            ContaPluggy(
                pluggy_item_id="item",
                pluggy_account_id=conta_pluggy,
                conta_id=conta.id,
                forma_pagamento_id=forma.id,
                sincronizar_desde=date(2025, 10, 1),
                ultimo_sync_em=quando,
                ativo=ativo,
            )
        )

    mapa("a", datetime(2026, 10, 15, 9, tzinfo=UTC))
    mapa("b", datetime(2026, 10, 16, 9, tzinfo=UTC))
    mapa("c", datetime(2026, 10, 20, 9, tzinfo=UTC), ativo=False)  # desativado não conta
    session.commit()

    corpo = client.get("/sincronizacao/estado").json()
    assert corpo["conexoes_ativas"] == 2
    assert corpo["ultima_atualizacao"].startswith("2026-10-16T09:00:00")
    assert corpo["automatica"] is False


def test_transacao_traz_a_conta_da_forma(client: TestClient, session: Session) -> None:
    conta = Conta(nome="Nubank", tipo=TipoConta.CORRENTE)
    session.add(conta)
    session.flush()
    cartao = FormaPagamento(
        apelido="Nubank Gold 7704", tipo=TipoPagamento.CREDITO, conta_id=conta.id
    )
    session.add(cartao)
    session.flush()
    session.add_all(
        [
            Transacao(
                data=date(2026, 10, 1),
                competencia=date(2026, 10, 1),
                valor=Decimal("10.00"),
                tipo=TipoTransacao.DESPESA,
                descricao="com forma",
                forma_pagamento_id=cartao.id,
            ),
            Transacao(
                data=date(2026, 10, 2),
                competencia=date(2026, 10, 1),
                valor=Decimal("11.00"),
                tipo=TipoTransacao.DESPESA,
                descricao="sem forma",
            ),
        ]
    )
    session.commit()

    itens = {t["descricao"]: t for t in client.get("/transacoes").json()["items"]}
    assert itens["com forma"]["forma_pagamento_conta_nome"] == "Nubank"
    assert itens["com forma"]["forma_pagamento_tipo"] == "credito"
    assert itens["sem forma"]["forma_pagamento_conta_nome"] is None
    detalhe = client.get(f"/transacoes/{itens['com forma']['id']}").json()
    assert detalhe["forma_pagamento_conta_nome"] == "Nubank"
