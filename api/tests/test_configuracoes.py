"""Telas de configuração (D-22): contas por banco, uso das categorias,
categorias da Pluggy e histórico de atualizações."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
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
from app.services.configuracoes import TITULO_MANUAIS, ConfiguracoesService

HOJE = date(2026, 10, 16)
n_importacao = 0


def _comprovante(session: Session, transacoes: list[dict[str, Any]], **campos: Any) -> Importacao:
    global n_importacao
    n_importacao += 1
    corpo = {
        "respostas": [
            {
                "metodo": "GET",
                "caminho": "/v2/transactions",
                "params": {"accountId": "x"},
                "status": 200,
                "corpo": {"results": transacoes, "next": None},
            }
        ]
    }
    imp = Importacao(
        arquivo_nome=f"pluggy-{n_importacao}.json",
        hash_arquivo=f"hash-config-{n_importacao}",
        arquivo_tipo="application/json",
        arquivo_conteudo=json.dumps(corpo).encode(),
        origem="pluggy",
        **{"status": StatusImportacao.CONCLUIDA, **campos},
    )
    session.add(imp)
    session.flush()
    return imp


def _tx(id_: str, conta: str, **campos: Any) -> dict[str, Any]:
    return {
        "id": id_,
        "accountId": conta,
        "date": "2026-10-10T12:00:00Z",
        "amount": "-10.00",
        "type": "DEBIT",
        "status": "POSTED",
        **campos,
    }


# --- contas e cartões --------------------------------------------------------


def test_contas_por_banco(session: Session) -> None:
    erik = Pessoa(nome="Erik")
    session.add(erik)
    session.flush()
    nubank = Conta(nome="Nubank", tipo=TipoConta.CORRENTE, titular_id=erik.id)
    sicredi = Conta(nome="Sicredi Conta Corrente", tipo=TipoConta.CORRENTE, titular_id=erik.id)
    poupanca = Conta(nome="Sicredi Poupança", tipo=TipoConta.POUPANCA, titular_id=erik.id)
    antiga = Conta(nome="Conta Corrente", tipo=TipoConta.CORRENTE)
    session.add_all([nubank, sicredi, poupanca, antiga])
    session.flush()

    def forma(apelido: str, tipo: TipoPagamento, conta: Conta) -> FormaPagamento:
        f = FormaPagamento(apelido=apelido, tipo=tipo, conta_id=conta.id)
        session.add(f)
        session.flush()
        return f

    pix_nu = forma("Pix Nubank", TipoPagamento.PIX, nubank)
    gold = forma("Nubank Gold •••• 7704", TipoPagamento.CREDITO, nubank)
    pix_sic = forma("Pix Sicredi", TipoPagamento.PIX, sicredi)
    forma("Débito Sicredi", TipoPagamento.DEBITO, sicredi)
    master = forma("Mastercard •••• 0117", TipoPagamento.CREDITO, sicredi)
    poup = forma("Transferência Poupança", TipoPagamento.TRANSFERENCIA, poupanca)

    def mapa(item: str, conta_pluggy: str, conta: Conta, f: FormaPagamento, **campos: Any) -> None:
        session.add(
            ContaPluggy(
                pluggy_item_id=item,
                pluggy_account_id=conta_pluggy,
                conta_id=conta.id,
                forma_pagamento_id=f.id,
                sincronizar_desde=campos.pop("desde", date(2025, 10, 1)),
                **campos,
            )
        )

    mapa("nu", "nu-conta", nubank, pix_nu)
    mapa("nu", "nu-cartao", nubank, gold, desde=date(2025, 10, 11))
    mapa("sic", "sic-cc", sicredi, pix_sic, desde=date(2026, 1, 1))
    mapa("sic", "sic-poup", poupanca, poup, desde=date(2026, 1, 1))
    mapa("sic", "sic-cartao", sicredi, master, deleted_em=datetime(2026, 10, 6, tzinfo=UTC))
    session.flush()

    def lancar(f: FormaPagamento, quando: date) -> None:
        session.add(
            Transacao(
                data=quando,
                competencia=quando.replace(day=1),
                valor=Decimal("10"),
                tipo=TipoTransacao.DESPESA,
                descricao="x",
                descricao_original=f"X {f.id} {quando}",
                forma_pagamento_id=f.id,
            )
        )

    lancar(pix_nu, date(2026, 10, 5))
    lancar(gold, date(2026, 10, 8))
    lancar(pix_sic, date(2026, 9, 30))
    lancar(master, date(2025, 1, 10))
    _comprovante(
        session,
        [
            _tx("c1", "nu-cartao", creditCardMetadata={"cardNumber": "•••• 7704"}),
            _tx("c2", "nu-cartao", creditCardMetadata={"cardNumber": "**** 7924"}),
            _tx("c3", "nu-cartao", creditCardMetadata={"cardNumber": "4216"}),
            _tx("c4", "nu-conta"),
        ],
    )
    session.commit()

    grupos = ConfiguracoesService(session, hoje=HOJE).contas().grupos
    assert [g.titulo for g in grupos] == ["Nubank", "Sicredi", TITULO_MANUAIS]

    nu = grupos[0]
    assert (nu.pluggy_item_id, nu.desde, nu.situacao) == ("nu", date(2025, 10, 1), "funcionando")
    conta_nu, cartao_nu = nu.itens
    assert (conta_nu.tipo, conta_nu.nome, conta_nu.titular) == ("conta", "Nubank", "Erik")
    assert conta_nu.situacao == "sincronizando"
    assert conta_nu.formas == [TipoPagamento.PIX]
    assert conta_nu.cartoes == ["Nubank Gold •••• 7704"]
    assert (cartao_nu.tipo, cartao_nu.paga_por, cartao_nu.forma_pagamento_id) == (
        "cartao",
        "Nubank",
        gold.id,
    )
    assert cartao_nu.cartoes_virtuais == ["4216", "7924"]
    assert cartao_nu.ultimo_movimento == date(2026, 10, 8)

    sic = grupos[1]
    assert (sic.desde, sic.situacao) == (date(2026, 1, 1), "parcial")
    por_nome = {i.nome: i for i in sic.itens}
    assert [i.nome for i in sic.itens] == [
        "Sicredi Conta Corrente",
        "Sicredi Poupança",
        "Mastercard •••• 0117",
    ]
    assert por_nome["Sicredi Conta Corrente"].formas == [TipoPagamento.DEBITO, TipoPagamento.PIX]
    assert por_nome["Sicredi Poupança"].situacao == "sem_movimento"
    assert por_nome["Mastercard •••• 0117"].situacao == "pausado"

    manual = grupos[2]
    assert (manual.situacao, [i.nome for i in manual.itens]) == ("manual", ["Conta Corrente"])
    assert manual.itens[0].situacao == "manual"


def test_contas_endpoint_vazio(client: TestClient) -> None:
    assert client.get("/configuracoes/contas").json() == {"grupos": []}


# --- categorias ---------------------------------------------------------------


def test_uso_das_categorias_no_mes(client: TestClient, session: Session) -> None:
    alimentacao = Categoria(nome="Alimentação", tipo=TipoTransacao.DESPESA)
    casa = Categoria(nome="Casa", tipo=TipoTransacao.DESPESA)
    a = Conta(nome="A", tipo=TipoConta.CORRENTE)
    b = Conta(nome="B", tipo=TipoConta.CORRENTE)
    session.add_all([alimentacao, casa, a, b])
    session.flush()
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA, categoria_pai_id=alimentacao.id)
    session.add(mercado)
    session.flush()

    contador = iter(range(100))

    def lancar(
        cat: Categoria | None, mes: date, tipo: TipoTransacao = TipoTransacao.DESPESA, **c: Any
    ) -> None:
        n = next(contador)
        session.add(
            Transacao(
                data=mes.replace(day=5),
                competencia=mes,
                valor=Decimal("10"),
                tipo=tipo,
                descricao=f"t{n}",
                descricao_original=f"T{n}",
                categoria_id=cat.id if cat else None,
                **c,
            )
        )
        session.flush()

    out, setembro = date(2026, 10, 1), date(2026, 9, 1)
    lancar(mercado, out)
    lancar(mercado, out)
    lancar(alimentacao, out)
    lancar(casa, out)
    lancar(None, out)
    lancar(None, out, TipoTransacao.TRANSFERENCIA, conta_origem_id=a.id, conta_destino_id=b.id)
    lancar(casa, setembro)
    session.commit()

    corpo = client.get("/configuracoes/categorias", params={"competencia": "2026-10-16"}).json()
    assert corpo["competencia"] == "2026-10-01"
    assert corpo["sem_categoria"] == 1
    assert {c["categoria_id"]: c["lancamentos"] for c in corpo["categorias"]} == {
        mercado.id: 2,
        alimentacao.id: 3,
        casa.id: 1,
    }


def test_categorias_que_o_banco_envia(client: TestClient, session: Session) -> None:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    restaurante = Categoria(nome="Restaurante", tipo=TipoTransacao.DESPESA)
    session.add_all([mercado, restaurante])
    session.flush()
    session.add_all(
        [
            CategoriaPluggy(
                pluggy_categoria_id="11000000",
                pluggy_categoria_nome="Groceries",
                categoria_id=mercado.id,
            ),
            # Mapeada, mas sem nenhuma transação nos comprovantes.
            CategoriaPluggy(
                pluggy_categoria_id="12000000",
                pluggy_categoria_nome="Eating out",
                categoria_id=restaurante.id,
            ),
        ]
    )
    groceries = {"categoryId": "11000000", "category": "Groceries"}
    _comprovante(
        session,
        [
            _tx("g1", "x", **groceries),
            _tx("g2", "x", **groceries),
            _tx("s1", "x", categoryId="99000000", category="Services"),
            _tx("t1", "x", categoryId="05000000", category="Transfers"),
            _tx("p1", "x", status="PENDING", **groceries),
        ],
    )
    # A mesma transação em outro comprovante conta uma vez só.
    _comprovante(session, [_tx("g1", "x", **groceries)])
    session.commit()

    linhas = {
        c["pluggy_categoria_id"]: c for c in client.get("/configuracoes/categorias-pluggy").json()
    }
    assert linhas["11000000"]["transacoes"] == 2
    assert linhas["11000000"]["categoria_nome"] == "Mercado"
    assert linhas["12000000"]["transacoes"] == 0
    assert linhas["99000000"]["mapeamento_id"] is None
    assert linhas["99000000"]["pluggy_categoria_nome"] == "Services"
    assert linhas["05000000"]["transferencia"] is True
    assert linhas["11000000"]["transferencia"] is False
    assert next(iter(linhas)) == "11000000"  # mais usada primeiro


# --- histórico ------------------------------------------------------------------


def test_historico_de_atualizacoes(client: TestClient, session: Session) -> None:
    agora = datetime.now(UTC)
    com_pendencia = _comprovante(session, [], total_itens=3, criado_em=agora - timedelta(hours=1))
    vazia = _comprovante(session, [], total_itens=0, criado_em=agora - timedelta(days=1))
    desfeita = _comprovante(
        session,
        [],
        total_itens=1,
        status=StatusImportacao.CANCELADA,
        criado_em=agora - timedelta(days=2),
    )
    _comprovante(session, [], total_itens=5, criado_em=agora - timedelta(days=40))  # fora

    def item(imp: Importacao, status: StatusItem, **c: Any) -> None:
        session.add(ImportacaoItem(importacao_id=imp.id, linha_bruta="L", status=status, **c))

    item(com_pendencia, StatusItem.APROVADO)
    item(com_pendencia, StatusItem.APROVADO)
    item(com_pendencia, StatusItem.PENDENTE)
    item(desfeita, StatusItem.APROVADO, deleted_em=agora)
    session.commit()

    linhas = client.get("/sincronizacao/historico", params={"dias": 30}).json()
    assert [linha["importacao_id"] for linha in linhas] == [com_pendencia.id, vazia.id, desfeita.id]
    primeira, segunda, terceira = linhas
    assert (primeira["entraram"], primeira["revisar"], primeira["situacao"]) == (
        2,
        1,
        "com_pendencias",
    )
    assert primeira["pode_desfazer"] is True
    assert (segunda["situacao"], segunda["pode_desfazer"]) == ("nada_novo", False)
    # Desfeita: mostra o que tinha trazido, sem oferecer desfazer de novo.
    assert (terceira["situacao"], terceira["entraram"], terceira["pode_desfazer"]) == (
        "desfeita",
        1,
        False,
    )
    assert client.get("/sincronizacao/historico", params={"dias": 0}).status_code == 422
