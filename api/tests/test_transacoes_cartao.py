"""Compra manual no cartão: a competência segue a fatura (D-34)."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import TipoPagamento
from tests.test_caixa import _bills, _comprovante, _conta, _forma, _liga_pluggy


def _post(client: TestClient, forma_id: int | None, data: str, **extra: Any) -> dict[str, Any]:
    corpo = {
        "data": data,
        "valor": "50.00",
        "descricao": "Compra manual",
        "forma_pagamento_id": forma_id,
        **extra,
    }
    resposta = client.post("/transacoes", json=corpo)
    assert resposta.status_code == 201, resposta.text
    return dict(resposta.json())


def test_pelos_dias_da_forma_antes_e_depois_do_fechamento(
    client: TestClient, session: Session
) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    session.commit()

    assert _post(client, cartao.id, "2026-10-02")["competencia"] == "2026-10-01"
    assert _post(client, cartao.id, "2026-10-03")["competencia"] == "2026-11-01"
    assert _post(client, cartao.id, "2026-10-20")["competencia"] == "2026-11-01"


def test_fatura_real_da_pluggy_vale_mais_que_os_dias_do_cadastro(
    client: TestClient, session: Session
) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    _liga_pluggy(session, cartao, banco, "acc-a")
    # O banco fechou em 07/10 e vence em 14/10; o cadastro (dia 3) erraria.
    _comprovante(
        session,
        [
            _bills(
                "acc-a",
                ("set", "2026-09-14", "2026-09-07"),
                ("out", "2026-10-14", "2026-10-07"),
                ("nov", "2026-11-14", "2026-11-07"),
            )
        ],
    )
    session.commit()

    assert _post(client, cartao.id, "2026-10-05")["competencia"] == "2026-10-01"
    assert _post(client, cartao.id, "2026-10-07")["competencia"] == "2026-11-01"
    assert _post(client, cartao.id, "2026-10-20")["competencia"] == "2026-11-01"


def test_forma_sem_datas_mantem_o_mes_da_compra(client: TestClient, session: Session) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão sem datas", TipoPagamento.CREDITO, banco)
    session.commit()

    assert _post(client, cartao.id, "2026-10-20")["competencia"] == "2026-10-01"


def test_forma_que_nao_e_credito_nao_muda(client: TestClient, session: Session) -> None:
    banco = _conta(session, "Banco")
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco, fecha=3, vence=10)
    session.commit()

    assert _post(client, pix.id, "2026-10-20")["competencia"] == "2026-10-01"
    assert _post(client, None, "2026-10-20")["competencia"] == "2026-10-01"


def test_competencia_explicita_do_usuario_vale(client: TestClient, session: Session) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    session.commit()

    tx = _post(client, cartao.id, "2026-10-20", competencia="2026-10-01")
    assert tx["competencia"] == "2026-10-01"


def test_editar_data_ou_forma_recalcula_salvo_competencia_explicita(
    client: TestClient, session: Session
) -> None:
    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    pix = _forma(session, "Pix", TipoPagamento.PIX, banco)
    session.commit()

    tx = _post(client, cartao.id, "2026-10-02")
    assert tx["competencia"] == "2026-10-01"

    # Passou do fechamento: vai para a fatura seguinte.
    depois = client.patch(f"/transacoes/{tx['id']}", json={"data": "2026-10-10"}).json()
    assert depois["competencia"] == "2026-11-01"

    # Competência explícita na edição não é recalculada.
    fixa = client.patch(
        f"/transacoes/{tx['id']}", json={"data": "2026-10-02", "competencia": "2026-12-01"}
    ).json()
    assert fixa["competencia"] == "2026-12-01"

    # Sem mexer em data nem forma, nada muda.
    outra = client.patch(f"/transacoes/{tx['id']}", json={"descricao": "Outra"}).json()
    assert outra["competencia"] == "2026-12-01"

    # Para uma forma que não é crédito, a competência fica como estava.
    pix_tx = client.patch(f"/transacoes/{tx['id']}", json={"forma_pagamento_id": pix.id}).json()
    assert pix_tx["competencia"] == "2026-12-01"


def test_editar_data_de_transacao_importada_mantem_a_competencia(
    client: TestClient, session: Session
) -> None:
    """A importada traz a competência da fatura real (billId, PDF): editar a
    data não a troca pela estimativa dos dias do cadastro."""
    from sqlalchemy import text

    from app.enums import StatusImportacao
    from app.models import Importacao

    banco = _conta(session, "Banco")
    cartao = _forma(session, "Cartão", TipoPagamento.CREDITO, banco, fecha=3, vence=10)
    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-importada-competencia",
        origem="pluggy",
        status=StatusImportacao.CONCLUIDA,
    )
    session.add(imp)
    session.commit()

    tx = _post(client, cartao.id, "2026-10-02", competencia="2026-12-01")
    session.execute(
        text("UPDATE transacoes SET importacao_id = :i WHERE id = :t"), {"i": imp.id, "t": tx["id"]}
    )
    session.commit()

    depois = client.patch(f"/transacoes/{tx['id']}", json={"data": "2026-10-10"}).json()
    assert depois["competencia"] == "2026-12-01"
