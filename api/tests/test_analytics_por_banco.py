"""Gasto por banco: cartão separado do que sai da conta, e a fila da revisão ao lado.

O Nubank é a conta por onde o dinheiro da casa entra; os outros bancos
recebem só o necessário para pagar a própria fatura. Por isso a pergunta
do painel é "quanto foi gasto em cada banco, e em quê".
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoTransacao
from app.models import Importacao, ImportacaoItem
from app.schemas.transacoes import TransacaoFiltros
from app.services.analytics import AnalyticsService

HOJE = date(2026, 11, 1)
OUTUBRO = TransacaoFiltros(competencia_inicio=date(2026, 10, 1), competencia_fim=date(2026, 10, 1))


def _post(client: TestClient, rota: str, **campos: object) -> dict:
    resposta = client.post(rota, json=campos)
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def bancos(client: TestClient, semeado: None) -> dict[str, int]:
    nubank = _post(client, "/contas", nome="Nubank", tipo="corrente")["id"]
    sicredi = _post(client, "/contas", nome="Sicredi", tipo="corrente")["id"]
    formas = {
        "nu_credito": _post(
            client, "/formas-pagamento", apelido="Nubank Gold", tipo="credito", conta_id=nubank
        ),
        "nu_pix": _post(
            client, "/formas-pagamento", apelido="Pix Nubank", tipo="pix", conta_id=nubank
        ),
        "nu_debito": _post(
            client, "/formas-pagamento", apelido="Débito Nubank", tipo="debito", conta_id=nubank
        ),
        "si_credito": _post(
            client, "/formas-pagamento", apelido="Sicredi Master", tipo="credito", conta_id=sicredi
        ),
    }
    ids = {chave: forma["id"] for chave, forma in formas.items()}
    ids |= {"nubank": nubank, "sicredi": sicredi}

    def despesa(forma: str | None, valor: str, data: str = "2026-10-05", **extra: object) -> None:
        _post(
            client,
            "/transacoes",
            data=data,
            valor=valor,
            tipo="despesa",
            descricao=f"{forma} {valor}",
            forma_pagamento_id=ids[forma] if forma else None,
            **extra,
        )

    despesa("nu_credito", "300.00")
    despesa("nu_credito", "200.00")
    despesa("nu_pix", "80.00")
    despesa("nu_debito", "20.00")
    despesa("si_credito", "150.00")
    despesa(None, "10.00")
    despesa("nu_credito", "999.00", data="2026-11-05")  # outro mês
    # Pagar a fatura do Sicredi com dinheiro do Nubank não é gasto (D-05).
    _post(
        client,
        "/transacoes",
        data="2026-10-07",
        valor="150.00",
        tipo="transferencia",
        descricao="Pix para o Sicredi",
        conta_origem_id=nubank,
        conta_destino_id=sicredi,
    )
    return ids


@pytest.fixture
def revisao(session: Session, bancos: dict[str, int]) -> None:
    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-por-banco",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()

    def item(valor: str, forma: str, **campos: object) -> None:
        dados: dict[str, object] = {
            "importacao_id": imp.id,
            "linha_bruta": f"item {valor}",
            "data": date(2026, 10, 20),
            "valor": Decimal(valor),
            "tipo_sugerido": TipoTransacao.DESPESA,
            "forma_pagamento_sugerida_id": bancos[forma],
            "status": StatusItem.PENDENTE,
        }
        session.add(ImportacaoItem(**(dados | campos)))

    item("40.00", "nu_credito")
    item("60.00", "nu_credito", competencia_sugerida=date(2026, 10, 1))
    item("25.00", "nu_pix")
    item("70.00", "nu_credito", competencia_sugerida=date(2026, 11, 1))  # novembro
    item("5.00", "nu_credito", status=StatusItem.REJEITADO)
    item("9.00", "nu_pix", tipo_sugerido=TipoTransacao.TRANSFERENCIA)
    session.commit()


def _servico(session: Session) -> AnalyticsService:
    return AnalyticsService(session, hoje=HOJE)


def test_separa_cartao_do_que_sai_da_conta(session: Session, bancos: dict[str, int]) -> None:
    painel = _servico(session).por_banco(OUTUBRO)
    assert painel.total == Decimal("760.00")
    assert painel.cartao == Decimal("650.00")
    assert painel.conta == Decimal("110.00")

    por_nome = {b.nome: b for b in painel.linhas}
    nubank = por_nome["Nubank"]
    assert (nubank.total, nubank.cartao, nubank.conta) == (
        Decimal("600.00"),
        Decimal("500.00"),
        Decimal("100.00"),
    )
    assert [f.apelido for f in nubank.formas] == ["Nubank Gold", "Pix Nubank", "Débito Nubank"]
    assert nubank.formas[0].quantidade == 2
    assert nubank.formas[0].cartao is True
    assert nubank.formas[1].cartao is False
    assert por_nome["Sicredi"].cartao == Decimal("150.00")
    assert por_nome["Sem forma de pagamento"].total == Decimal("10.00")


def test_bancos_em_ordem_de_gasto_e_percentual(session: Session, bancos: dict[str, int]) -> None:
    painel = _servico(session).por_banco(OUTUBRO)
    assert [b.nome for b in painel.linhas] == ["Nubank", "Sicredi", "Sem forma de pagamento"]
    assert painel.linhas[0].percentual == Decimal("78.9")


def test_transferencia_entre_bancos_nao_e_gasto(session: Session, bancos: dict[str, int]) -> None:
    painel = _servico(session).por_banco(OUTUBRO)
    sicredi = next(b for b in painel.linhas if b.nome == "Sicredi")
    assert sicredi.total == Decimal("150.00")  # só a compra, não o Pix que pagou a fatura


def test_ignora_o_filtro_de_forma(session: Session, bancos: dict[str, int]) -> None:
    """Clicar numa forma não pode sumir com as outras do painel."""
    filtros = OUTUBRO.model_copy(update={"forma_pagamento_ids": [bancos["nu_pix"]]})
    assert _servico(session).por_banco(filtros).total == Decimal("760.00")


def test_respeita_os_outros_filtros(session: Session, bancos: dict[str, int]) -> None:
    filtros = OUTUBRO.model_copy(update={"valor_min": Decimal("100")})
    assert _servico(session).por_banco(filtros).total == Decimal("650.00")


def test_mostra_o_que_esta_na_revisao(session: Session, revisao: None) -> None:
    """Pendente de despesa no período: fora do total, mas à vista."""
    painel = _servico(session).por_banco(OUTUBRO)
    assert painel.total == Decimal("760.00")
    assert (painel.revisao_valor, painel.revisao_quantidade) == (Decimal("125.00"), 3)

    nubank = next(b for b in painel.linhas if b.nome == "Nubank")
    assert (nubank.revisao_valor, nubank.revisao_quantidade) == (Decimal("125.00"), 3)
    gold = next(f for f in nubank.formas if f.apelido == "Nubank Gold")
    assert (gold.revisao_valor, gold.revisao_quantidade) == (Decimal("100.00"), 2)


def test_revisao_de_outro_mes_fica_fora(session: Session, revisao: None) -> None:
    novembro = TransacaoFiltros(
        competencia_inicio=date(2026, 11, 1), competencia_fim=date(2026, 11, 1)
    )
    painel = _servico(session).por_banco(novembro)
    assert painel.total == Decimal("999.00")
    assert (painel.revisao_valor, painel.revisao_quantidade) == (Decimal("70.00"), 1)


def test_banco_so_com_revisao_aparece(session: Session, bancos: dict[str, int]) -> None:
    imp = Importacao(
        arquivo_nome="p.json", hash_arquivo="h-so-rev", status=StatusImportacao.AGUARDANDO_REVISAO
    )
    session.add(imp)
    session.flush()
    session.add(
        ImportacaoItem(
            importacao_id=imp.id,
            linha_bruta="mercado",
            data=date(2026, 12, 3),
            valor=Decimal("33.00"),
            tipo_sugerido=TipoTransacao.DESPESA,
            forma_pagamento_sugerida_id=bancos["si_credito"],
            status=StatusItem.PENDENTE,
        )
    )
    session.commit()
    dezembro = TransacaoFiltros(
        competencia_inicio=date(2026, 12, 1), competencia_fim=date(2026, 12, 1)
    )
    painel = _servico(session).por_banco(dezembro)
    assert painel.total == 0
    [sicredi] = painel.linhas
    assert (sicredi.nome, sicredi.total, sicredi.revisao_valor) == (
        "Sicredi",
        Decimal("0.00"),
        Decimal("33.00"),
    )


def test_vem_no_resumo(client: TestClient, bancos: dict[str, int]) -> None:
    resposta = client.get(
        "/analytics/resumo?competencia_inicio=2026-10-01&competencia_fim=2026-10-01"
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["por_banco"]["total"] == "760.00"


def test_rota_propria(client: TestClient, bancos: dict[str, int]) -> None:
    """A tela Análises pede só o painel, com o período dela."""
    resposta = client.get(
        "/analytics/por-banco?competencia_inicio=2026-10-01&competencia_fim=2026-10-01"
    )
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert (dados["total"], dados["cartao"], dados["conta"]) == ("760.00", "650.00", "110.00")


def test_base_compra_move_o_cartao_para_o_mes_da_compra(
    session: Session, client: TestClient
) -> None:
    """D-27: compra em 28/07 com competência agosto."""
    from app.models import Transacao

    session.add(
        Transacao(
            data=date(2026, 7, 28),
            competencia=date(2026, 8, 1),
            valor=Decimal("70"),
            tipo=TipoTransacao.DESPESA,
            descricao="cartão",
            descricao_original="CARTAO",
        )
    )
    session.commit()
    julho = TransacaoFiltros(competencia_inicio=date(2026, 7, 1), competencia_fim=date(2026, 7, 1))
    agosto = TransacaoFiltros(competencia_inicio=date(2026, 8, 1), competencia_fim=date(2026, 8, 1))
    servico = AnalyticsService(session)
    assert servico.por_banco(agosto).total == Decimal("70")
    assert servico.por_banco(julho).total == Decimal("0")
    assert servico.por_banco(agosto, "compra").total == Decimal("0")
    assert servico.por_banco(julho, "compra").total == Decimal("70")

    params = {"competencia_inicio": "2026-07-01", "competencia_fim": "2026-07-01"}
    assert client.get("/analytics/por-banco", params=params | {"base": "compra"}).status_code == 200
    assert client.get("/analytics/por-banco", params=params | {"base": "x"}).status_code == 422
