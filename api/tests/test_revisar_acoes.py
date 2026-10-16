"""Decisões da tela de revisão: duplicata e transferência (D-22)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversao_pluggy import OBS_MESMA_PESSOA, OBS_PAGAMENTO_NA_CONTA, OBS_PAGAMENTO_NO_CARTAO
from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Categoria,
    Conta,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    Transacao,
)
from app.services.revisao import (
    MENSAGEM_ITENS_IDENTICOS,
    MOTIVO_FATURA_DA_PROPRIA_CONTA,
    MOTIVO_LADO_DO_CARTAO,
)

GEMEO = (
    "Possível duplicata da Pluggy (no mesmo lote): mesma data, valor e descrição de "
    "tx-2. Confira no app do banco antes de aprovar os dois."
)
DIA = date(2026, 10, 14)


class Cenario:
    """Duas contas (Sicredi e Nubank), com Pix em cada e o cartão no Nubank."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.erik = Pessoa(nome="Erik")
        self.sicredi = Conta(nome="Sicredi", tipo=TipoConta.CORRENTE)
        self.nubank = Conta(nome="Nubank", tipo=TipoConta.CORRENTE)
        self.mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
        session.add_all([self.erik, self.sicredi, self.nubank, self.mercado])
        session.flush()
        self.pix_sicredi = self._forma("Pix Sicredi", TipoPagamento.PIX, self.sicredi)
        self.debito_sicredi = self._forma("Débito Sicredi", TipoPagamento.DEBITO, self.sicredi)
        self.pix_nubank = self._forma("Pix Nubank", TipoPagamento.PIX, self.nubank)
        self.cartao = self._forma("Nubank Gold •••• 7704", TipoPagamento.CREDITO, self.nubank)

    def _forma(self, apelido: str, tipo: TipoPagamento, conta: Conta) -> FormaPagamento:
        forma = FormaPagamento(apelido=apelido, tipo=tipo, conta_id=conta.id)
        self.session.add(forma)
        self.session.flush()
        return forma

    def importacao(self, transacoes: list[dict[str, Any]] | None = None) -> Importacao:
        """Importação da Pluggy com o comprovante: o sentido de cada transação."""
        respostas = [
            {
                "metodo": "GET",
                "caminho": "/v2/transactions",
                "params": {"accountId": "conta"},
                "status": 200,
                "corpo": {"results": transacoes or [], "next": None},
            }
        ]
        n = len(self.session.scalars(select(Importacao.id)).all())
        imp = Importacao(
            arquivo_nome=f"pluggy-{n}.json",
            hash_arquivo=f"hash-{n}",
            arquivo_tipo="application/json",
            arquivo_conteudo=json.dumps({"respostas": respostas}).encode(),
            origem="pluggy",
            status=StatusImportacao.AGUARDANDO_REVISAO,
        )
        self.session.add(imp)
        self.session.flush()
        return imp

    def item(self, imp: Importacao, **campos: Any) -> ImportacaoItem:
        padrao: dict[str, Any] = {
            "linha_bruta": "SUPERMERCADO BOM PRECO",
            "data": DIA,
            "valor": Decimal("186.40"),
            "tipo_sugerido": TipoTransacao.DESPESA,
            "competencia_sugerida": date(2026, 10, 1),
            "status": StatusItem.PENDENTE,
        }
        item = ImportacaoItem(importacao_id=imp.id, **{**padrao, **campos})
        self.session.add(item)
        self.session.flush()
        return item


def _pluggy(id_: str, tipo: str, valor: str = "500.00") -> dict[str, Any]:
    return {
        "id": id_,
        "accountId": "conta",
        "date": "2026-10-14T12:00:00Z",
        "amount": valor if tipo == "CREDIT" else f"-{valor}",
        "type": tipo,
        "status": "POSTED",
    }


# --- itens -------------------------------------------------------------------


def test_itens_por_motivo_com_nomes(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    sem = c.item(
        imp,
        linha_bruta="Ec *Padaria Central",
        pessoa_sugerida_id=c.erik.id,
        forma_pagamento_sugerida_id=c.debito_sicredi.id,
    )
    c.item(imp, categoria_sugerida_id=c.mercado.id, observacao="Competência estimada.")
    session.commit()

    corpo = client.get("/revisar/itens", params={"motivo": "sem_categoria"}).json()
    assert [i["id"] for i in corpo] == [sem.id]
    item = corpo[0]
    assert item["motivo"] == "sem_categoria"
    assert item["descricao"] == "Padaria Central"
    assert item["pessoa_nome"] == "Erik"
    assert item["forma_pagamento_tipo"] == "debito"
    assert item["forma_pagamento_apelido"] == "Débito Sicredi"
    assert item["conta_nome"] == "Sicredi"
    assert item["valor"] == "186.40"

    todos = client.get("/revisar/itens").json()
    assert {i["motivo"] for i in todos} == {"sem_categoria", "observacao"}
    assert client.get("/revisar/itens", params={"motivo": "inventado"}).status_code == 422


# --- duplicatas --------------------------------------------------------------


def test_manter_so_um(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    comum = {
        "categoria_sugerida_id": c.mercado.id,
        "forma_pagamento_sugerida_id": c.cartao.id,
    }
    a = c.item(imp, observacao=GEMEO, id_externo="tx-1", **comum)
    b = c.item(imp, observacao=GEMEO, id_externo="tx-2", **comum)
    c.item(imp, linha_bruta="OUTRA COISA", **comum)  # fora do grupo
    session.commit()

    grupos = client.get("/revisar/duplicatas").json()
    assert len(grupos) == 1
    grupo = grupos[0]
    assert [i["id"] for i in grupo["itens"]] == [a.id, b.id]
    assert grupo["ja_lancado"] is False
    assert grupo["podem_ser_dois"] is False  # mesma forma: o banco recusa a segunda

    resposta = client.post(
        "/revisar/duplicatas/resolver", json={"manter_ids": [a.id], "descartar_ids": [b.id]}
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"aprovados": 1, "descartados": 1, "pendentes": 0, "erros": []}

    session.expire_all()
    mantido, descartado = session.get(ImportacaoItem, a.id), session.get(ImportacaoItem, b.id)
    assert mantido is not None and descartado is not None
    assert mantido.status is StatusItem.APROVADO
    assert mantido.observacao is None
    assert descartado.status is StatusItem.REJEITADO
    assert f"#{a.id}" in (descartado.motivo_rejeicao or "")
    assert client.get("/revisar/duplicatas").json() == []


def test_sao_dois_identicos_e_recusado(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    comum = {"categoria_sugerida_id": c.mercado.id, "forma_pagamento_sugerida_id": c.cartao.id}
    a = c.item(imp, observacao=GEMEO, id_externo="tx-1", **comum)
    b = c.item(imp, observacao=GEMEO, id_externo="tx-2", **comum)
    session.commit()

    resposta = client.post("/revisar/duplicatas/resolver", json={"manter_ids": [a.id, b.id]})
    assert resposta.status_code == 422
    assert MENSAGEM_ITENS_IDENTICOS in resposta.text
    session.expire_all()
    assert session.get(ImportacaoItem, a.id).status is StatusItem.PENDENTE  # type: ignore[union-attr]


def test_sao_dois_com_formas_diferentes(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    a = c.item(
        imp,
        observacao=GEMEO,
        id_externo="tx-1",
        categoria_sugerida_id=c.mercado.id,
        forma_pagamento_sugerida_id=c.pix_sicredi.id,
    )
    b = c.item(
        imp,
        observacao=GEMEO,
        id_externo="tx-2",
        categoria_sugerida_id=c.mercado.id,
        forma_pagamento_sugerida_id=c.debito_sicredi.id,
    )
    session.commit()

    assert client.get("/revisar/duplicatas").json()[0]["podem_ser_dois"] is True
    resposta = client.post("/revisar/duplicatas/resolver", json={"manter_ids": [a.id, b.id]})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["aprovados"] == 2
    vivas = session.scalars(select(Transacao).where(Transacao.deleted_em.is_(None))).all()
    assert len(vivas) == 2


def test_gemeo_ja_lancado(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    comum = {"categoria_sugerida_id": c.mercado.id, "forma_pagamento_sugerida_id": c.cartao.id}
    antigo = c.item(imp, id_externo="tx-1", **comum)
    novo = c.item(imp, observacao=GEMEO, id_externo="tx-2", **comum)
    session.commit()
    assert client.post("/importacoes/itens/aprovar", json={"ids": [antigo.id]}).status_code == 200
    session.expire_all()
    transacao_id = session.get(ImportacaoItem, antigo.id).transacao_id  # type: ignore[union-attr]

    grupo = client.get("/revisar/duplicatas").json()[0]
    assert grupo["ja_lancado"] is True
    assert [i["status"] for i in grupo["itens"]] == ["aprovado", "pendente"]

    # O que já é transação não se descarta por aqui.
    recusa = client.post(
        "/revisar/duplicatas/resolver",
        json={"manter_ids": [novo.id], "descartar_ids": [antigo.id]},
    )
    assert recusa.status_code == 422

    resposta = client.post(
        "/revisar/duplicatas/resolver",
        json={"manter_ids": [antigo.id], "descartar_ids": [novo.id]},
    )
    assert resposta.json() == {"aprovados": 0, "descartados": 1, "pendentes": 0, "erros": []}
    session.expire_all()
    descartado = session.get(ImportacaoItem, novo.id)
    assert descartado is not None
    assert f"transação #{transacao_id}" in (descartado.motivo_rejeicao or "")


def test_mantido_com_outro_motivo_segue_na_revisao(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    a = c.item(imp, observacao=f"Compra em USD. {GEMEO}", id_externo="tx-1")
    b = c.item(imp, observacao=GEMEO, id_externo="tx-2")
    session.commit()

    resposta = client.post(
        "/revisar/duplicatas/resolver", json={"manter_ids": [a.id], "descartar_ids": [b.id]}
    )
    assert resposta.json() == {"aprovados": 0, "descartados": 1, "pendentes": 1, "erros": []}
    session.expire_all()
    mantido = session.get(ImportacaoItem, a.id)
    assert mantido is not None
    assert mantido.status is StatusItem.PENDENTE
    assert mantido.observacao == "Compra em USD."


def test_resolver_itens_de_fora_do_grupo(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()
    a = c.item(imp, observacao=GEMEO, id_externo="tx-1")
    solto = c.item(imp, linha_bruta="OUTRA")
    session.commit()
    resposta = client.post(
        "/revisar/duplicatas/resolver", json={"manter_ids": [a.id], "descartar_ids": [solto.id]}
    )
    assert resposta.status_code == 422
    resposta = client.post(
        "/revisar/duplicatas/resolver", json={"manter_ids": [a.id], "descartar_ids": [a.id]}
    )
    assert resposta.status_code == 422


# --- transferências ----------------------------------------------------------


def _transferencia(c: Cenario, imp: Importacao, **campos: Any) -> ImportacaoItem:
    return c.item(
        imp,
        tipo_sugerido=TipoTransacao.TRANSFERENCIA,
        valor=Decimal("500.00"),
        **campos,
    )


def test_as_duas_pontas_viram_uma_transferencia(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao([_pluggy("tx-saida", "DEBIT"), _pluggy("tx-entrada", "CREDIT")])
    saida = _transferencia(
        c,
        imp,
        linha_bruta="PIX ENVIADO ERIK",
        observacao=OBS_MESMA_PESSOA,
        id_externo="tx-saida",
        forma_pagamento_sugerida_id=c.pix_sicredi.id,
        pessoa_sugerida_id=c.erik.id,
    )
    entrada = _transferencia(
        c,
        imp,
        linha_bruta="PIX RECEBIDO ERIK",
        data=date(2026, 10, 15),
        observacao=OBS_MESMA_PESSOA,
        id_externo="tx-entrada",
        forma_pagamento_sugerida_id=c.pix_nubank.id,
    )
    session.commit()

    lista = {t["item"]["id"]: t for t in client.get("/revisar/transferencias").json()}
    assert lista[saida.id]["tipo"] == "mesma_pessoa"
    assert lista[saida.id]["direcao"] == "saida"
    assert lista[saida.id]["origem"] == {"id": c.sicredi.id, "nome": "Sicredi"}
    assert lista[saida.id]["destino"] == {"id": c.nubank.id, "nome": "Nubank"}
    assert lista[saida.id]["par_item_id"] == entrada.id
    assert lista[entrada.id]["origem"]["nome"] == "Sicredi"
    assert lista[entrada.id]["ao_confirmar"] == "transferencia"

    resposta = client.post(
        "/revisar/transferencias/confirmar",
        json={"itens": [{"item_id": saida.id}, {"item_id": entrada.id}]},
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == {"aprovados": 1, "descartados": 1, "pendentes": 0, "erros": []}

    transacao = session.scalars(select(Transacao)).one()
    assert transacao.tipo is TipoTransacao.TRANSFERENCIA
    assert (transacao.conta_origem_id, transacao.conta_destino_id) == (c.sicredi.id, c.nubank.id)
    assert transacao.categoria_id is None
    assert transacao.pessoa_id == c.erik.id
    session.expire_all()
    outra = session.get(ImportacaoItem, entrada.id)
    assert outra is not None and outra.status is StatusItem.REJEITADO
    assert f"#{transacao.id}" in (outra.motivo_rejeicao or "")
    assert client.get("/revisar/transferencias").json() == []


def test_pagamento_de_fatura_da_propria_conta(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao([_pluggy("tx-conta", "DEBIT"), _pluggy("tx-cartao", "CREDIT", "731.10")])
    conta = _transferencia(
        c,
        imp,
        linha_bruta="Pagamento de fatura",
        observacao=OBS_PAGAMENTO_NA_CONTA,
        id_externo="tx-conta",
        forma_pagamento_sugerida_id=c.pix_nubank.id,
    )
    cartao = _transferencia(
        c,
        imp,
        linha_bruta="Pagamento recebido",
        valor=Decimal("731.10"),
        observacao=OBS_PAGAMENTO_NO_CARTAO,
        id_externo="tx-cartao",
        forma_pagamento_sugerida_id=c.cartao.id,
    )
    session.commit()

    lista = {t["item"]["id"]: t for t in client.get("/revisar/transferencias").json()}
    lado_conta, lado_cartao = lista[conta.id], lista[cartao.id]
    assert lado_conta["tipo"] == "pagamento_fatura_conta"
    assert lado_conta["origem"]["nome"] == "Nubank"
    assert lado_conta["destino"] is None
    assert lado_conta["fatura_de"] == "Nubank Gold •••• 7704"
    assert lado_conta["ao_confirmar"] == "descartar"
    assert lado_cartao["tipo"] == "pagamento_fatura_cartao"
    assert lado_cartao["item"]["motivo"] == "pagamento_fatura_cartao"
    assert lado_cartao["fatura_de"] == "Nubank Gold •••• 7704"
    assert lado_cartao["ao_confirmar"] == "descartar"

    resposta = client.post(
        "/revisar/transferencias/confirmar",
        json={"itens": [{"item_id": conta.id}, {"item_id": cartao.id}]},
    )
    assert resposta.json() == {"aprovados": 0, "descartados": 2, "pendentes": 0, "erros": []}
    session.expire_all()
    assert session.get(ImportacaoItem, conta.id).motivo_rejeicao == MOTIVO_FATURA_DA_PROPRIA_CONTA  # type: ignore[union-attr]
    assert session.get(ImportacaoItem, cartao.id).motivo_rejeicao == MOTIVO_LADO_DO_CARTAO  # type: ignore[union-attr]
    assert session.scalars(select(Transacao)).all() == []


def test_transferencia_sem_sentido_conhecido(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao()  # comprovante sem a transação: sentido desconhecido
    item = _transferencia(c, imp, forma_pagamento_sugerida_id=c.pix_sicredi.id)
    session.commit()

    atual = client.get("/revisar/transferencias").json()[0]
    assert atual["tipo"] == "outra"
    assert atual["direcao"] is None
    assert atual["origem"] is None and atual["destino"] is None

    sem_contas = client.post(
        "/revisar/transferencias/confirmar", json={"itens": [{"item_id": item.id}]}
    ).json()
    assert sem_contas["aprovados"] == 0
    assert sem_contas["erros"][0]["item_id"] == item.id

    mesma = client.post(
        "/revisar/transferencias/confirmar",
        json={
            "itens": [
                {
                    "item_id": item.id,
                    "conta_origem_id": c.sicredi.id,
                    "conta_destino_id": c.sicredi.id,
                }
            ]
        },
    ).json()
    assert "mesma conta" in mesma["erros"][0]["erro"]

    resposta = client.post(
        "/revisar/transferencias/confirmar",
        json={
            "itens": [
                {
                    "item_id": item.id,
                    "conta_origem_id": c.sicredi.id,
                    "conta_destino_id": c.nubank.id,
                }
            ]
        },
    ).json()
    assert resposta == {"aprovados": 1, "descartados": 0, "pendentes": 0, "erros": []}
    transacao = session.scalars(select(Transacao)).one()
    assert transacao.conta_destino_id == c.nubank.id


def test_nao_e_transferencia(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao([_pluggy("tx-1", "DEBIT")])
    item = _transferencia(
        c,
        imp,
        observacao=f"Outra nota. {OBS_MESMA_PESSOA}",
        id_externo="tx-1",
        forma_pagamento_sugerida_id=c.pix_sicredi.id,
    )
    desconhecido = _transferencia(c, imp, linha_bruta="TED", id_externo="tx-fora")
    session.commit()

    resposta = client.post(f"/revisar/transferencias/{item.id}/nao-e", json={})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["tipo_sugerido"] == "despesa"
    assert corpo["observacao"] == "Outra nota."
    assert corpo["motivo"] == "observacao"

    # Sem sentido conhecido, quem decide diz o tipo.
    recusa = client.post(f"/revisar/transferencias/{desconhecido.id}/nao-e", json={})
    assert recusa.status_code == 422
    receita = client.post(
        f"/revisar/transferencias/{desconhecido.id}/nao-e", json={"tipo": "receita"}
    ).json()
    assert receita["tipo_sugerido"] == "receita"
    assert receita["motivo"] == "sem_categoria"

    # Fora da aba de transferências não se aplica.
    assert client.post(f"/revisar/transferencias/{item.id}/nao-e", json={}).status_code == 422


def test_fatura_paga_por_outra_conta(client: TestClient, session: Session) -> None:
    """Sicredi paga a fatura do cartão do Nubank: as duas pontas casam."""
    c = Cenario(session)
    imp = c.importacao([_pluggy("tx-conta", "DEBIT"), _pluggy("tx-cartao", "CREDIT")])
    conta = _transferencia(
        c,
        imp,
        linha_bruta="Pagamento de fatura",
        observacao=OBS_PAGAMENTO_NA_CONTA,
        id_externo="tx-conta",
        forma_pagamento_sugerida_id=c.pix_sicredi.id,
    )
    cartao = _transferencia(
        c,
        imp,
        linha_bruta="Pagamento recebido",
        observacao=OBS_PAGAMENTO_NO_CARTAO,
        id_externo="tx-cartao",
        forma_pagamento_sugerida_id=c.cartao.id,
    )
    session.commit()

    lista = {t["item"]["id"]: t for t in client.get("/revisar/transferencias").json()}
    for lado in (lista[conta.id], lista[cartao.id]):
        assert lado["origem"]["nome"] == "Sicredi"
        assert lado["destino"]["nome"] == "Nubank"
        assert lado["fatura_de"] == "Nubank Gold •••• 7704"
        assert lado["ao_confirmar"] == "transferencia"
    assert lista[conta.id]["par_item_id"] == cartao.id

    resposta = client.post(
        "/revisar/transferencias/confirmar", json={"itens": [{"item_id": conta.id}]}
    ).json()
    assert resposta == {"aprovados": 1, "descartados": 1, "pendentes": 0, "erros": []}
    transacao = session.scalars(select(Transacao)).one()
    assert (transacao.conta_origem_id, transacao.conta_destino_id) == (c.sicredi.id, c.nubank.id)


def test_lados_da_fatura_na_mesma_conta_casam(client: TestClient, session: Session) -> None:
    c = Cenario(session)
    imp = c.importacao([_pluggy("tx-conta", "DEBIT"), _pluggy("tx-cartao", "CREDIT")])
    conta = _transferencia(
        c,
        imp,
        observacao=OBS_PAGAMENTO_NA_CONTA,
        id_externo="tx-conta",
        forma_pagamento_sugerida_id=c.pix_nubank.id,
    )
    cartao = _transferencia(
        c,
        imp,
        observacao=OBS_PAGAMENTO_NO_CARTAO,
        id_externo="tx-cartao",
        forma_pagamento_sugerida_id=c.cartao.id,
    )
    session.commit()

    lista = {t["item"]["id"]: t for t in client.get("/revisar/transferencias").json()}
    assert lista[cartao.id]["par_item_id"] == conta.id
    assert lista[cartao.id]["origem"]["nome"] == "Nubank"
    assert lista[cartao.id]["ao_confirmar"] == "descartar"
    assert lista[conta.id]["ao_confirmar"] == "descartar"
