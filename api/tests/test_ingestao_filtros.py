"""Filtros da revisão de uma importação: no banco, com as contagens (regra 10)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoTransacao
from app.models import Categoria, Importacao, ImportacaoItem
from app.services.ingestao import IngestaoService


@pytest.fixture
def importacao(session: Session) -> Importacao:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add(mercado)
    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-filtros",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()

    def item(
        texto: str,
        valor: str,
        *,
        status: StatusItem = StatusItem.PENDENTE,
        tipo: TipoTransacao = TipoTransacao.DESPESA,
        categoria: bool = False,
        observacao: str | None = None,
    ) -> ImportacaoItem:
        novo = ImportacaoItem(
            importacao_id=imp.id,
            linha_bruta=texto,
            descricao_original=texto,
            data=date(2026, 9, 1),
            valor=Decimal(valor),
            tipo_sugerido=tipo,
            categoria_sugerida_id=mercado.id if categoria else None,
            observacao=observacao,
            status=status,
        )
        session.add(novo)
        return novo

    item("PADARIA DO BAIRRO", "10.00")  # sem categoria
    item("MERCADO PRONTO", "20.00", categoria=True)  # pronto
    item("MERCADO COM NOTA", "30.00", categoria=True, observacao="Confira.")
    item("PIX ENTRE CONTAS", "40.00", tipo=TipoTransacao.TRANSFERENCIA)
    item("LOJA 100%_OFF", "5.00")  # sem categoria, com caracteres de LIKE
    aprovado = item("MERCADO APROVADO", "50.00", categoria=True)
    item("TARIFA REJEITADA", "1.00", status=StatusItem.REJEITADO)
    session.commit()
    # Aprovado só pelo caminho de verdade: o banco exige a transação.
    IngestaoService(session).aprovar([aprovado.id])
    session.commit()
    return imp


def _textos(dados: dict[str, Any]) -> set[str]:
    return {i["linha_bruta"] for i in dados["itens"]}


def test_contagens_da_importacao_inteira(client: TestClient, importacao: Importacao) -> None:
    dados = client.get(f"/importacoes/{importacao.id}?falta=pronto").json()
    assert dados["contagens"]["por_status"] == {"pendente": 5, "aprovado": 1, "rejeitado": 1}
    assert dados["contagens"]["pendentes_por_falta"] == {
        "sem_categoria": 2,
        "observacao": 1,
        "transferencia": 1,
        "pronto": 1,
    }
    # Somas da importação inteira, não do filtro aberto.
    assert Decimal(dados["total_pendente"]) == Decimal("65.00")
    assert Decimal(dados["soma_lida"]) == Decimal("115.00")


@pytest.mark.parametrize(
    ("query", "esperado"),
    [
        ("", None),  # sem filtro: todos os 7
        ("apenas=pendente", 5),
        ("apenas=aprovado", {"MERCADO APROVADO"}),
        ("falta=sem_categoria", {"PADARIA DO BAIRRO", "LOJA 100%_OFF"}),
        ("falta=observacao", {"MERCADO COM NOTA"}),
        ("falta=transferencia", {"PIX ENTRE CONTAS"}),
        ("falta=pronto", {"MERCADO PRONTO"}),
        ("busca=mercado", {"MERCADO PRONTO", "MERCADO COM NOTA", "MERCADO APROVADO"}),
        ("apenas=pendente&busca=mercado", {"MERCADO PRONTO", "MERCADO COM NOTA"}),
        # % e _ são texto, não curinga do LIKE.
        ("busca=100%25_", {"LOJA 100%_OFF"}),
        ("busca=0%25", {"LOJA 100%_OFF"}),
        ("busca=_O", {"LOJA 100%_OFF"}),
    ],
)
def test_filtros(
    client: TestClient, importacao: Importacao, query: str, esperado: set[str] | int | None
) -> None:
    resposta = client.get(f"/importacoes/{importacao.id}?{query}")
    assert resposta.status_code == 200
    dados = resposta.json()
    if esperado is None:
        assert len(dados["itens"]) == 7
    elif isinstance(esperado, int):
        assert len(dados["itens"]) == esperado
    else:
        assert _textos(dados) == esperado


def test_falta_so_olha_pendentes(client: TestClient, importacao: Importacao) -> None:
    """O aprovado com categoria não é "pronto": já foi."""
    dados = client.get(f"/importacoes/{importacao.id}?apenas=aprovado&falta=pronto").json()
    assert _textos(dados) == {"MERCADO PRONTO"}


def test_filtro_desconhecido_e_422(client: TestClient, importacao: Importacao) -> None:
    assert client.get(f"/importacoes/{importacao.id}?falta=qualquer").status_code == 422


def test_lista_traz_os_pendentes(client: TestClient, importacao: Importacao) -> None:
    lista = client.get("/importacoes").json()
    assert [(i["id"], i["itens_pendentes"]) for i in lista] == [(importacao.id, 5)]
