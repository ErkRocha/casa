"""O que a tela de Lançamentos usa (D-22): total por dia, atalho "sem
categoria", transferências à parte e busca por valor."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import TipoConta, TipoTransacao
from app.models import Categoria, Conta, Transacao

OUTUBRO = {"competencia_inicio": "2026-10-01", "competencia_fim": "2026-10-01"}


def _semear(session: Session) -> None:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    origem = Conta(nome="Sicredi", tipo=TipoConta.CORRENTE)
    destino = Conta(nome="Nubank", tipo=TipoConta.CORRENTE)
    session.add_all([mercado, salario, origem, destino])
    session.flush()

    def lancar(dia: int, valor: str, tipo: TipoTransacao, descricao: str, **campos: Any) -> None:
        session.add(
            Transacao(
                data=date(2026, 10, dia),
                competencia=date(2026, 10, 1),
                valor=Decimal(valor),
                tipo=tipo,
                descricao=descricao,
                descricao_original=descricao.upper(),
                **campos,
            )
        )

    lancar(16, "186.40", TipoTransacao.DESPESA, "Supermercado", categoria_id=mercado.id)
    lancar(16, "1186.40", TipoTransacao.DESPESA, "Geladeira")  # sem categoria
    lancar(15, "320.00", TipoTransacao.RECEITA, "Pix recebido", categoria_id=salario.id)
    lancar(15, "47.89", TipoTransacao.DESPESA, "Farmácia")  # sem categoria
    lancar(
        15,
        "500.00",
        TipoTransacao.TRANSFERENCIA,
        "Para o Nubank",
        conta_origem_id=origem.id,
        conta_destino_id=destino.id,
    )
    # Outro mês: fora de tudo.
    session.add(
        Transacao(
            data=date(2026, 9, 30),
            competencia=date(2026, 9, 1),
            valor=Decimal("99.00"),
            tipo=TipoTransacao.DESPESA,
            descricao="Setembro",
        )
    )
    session.commit()


def test_totais_com_transferencias_a_parte(client: TestClient, session: Session) -> None:
    _semear(session)
    totais = client.get("/transacoes", params=OUTUBRO).json()["totais"]
    assert totais["total_despesa"] == "1420.69"
    assert totais["total_receita"] == "320.00"
    assert totais["total_transferencia"] == "500.00"
    assert totais["quantidade_transferencias"] == 1
    assert totais["sem_categoria"] == 2


def test_filtro_sem_categoria(client: TestClient, session: Session) -> None:
    _semear(session)
    corpo = client.get("/transacoes", params={**OUTUBRO, "sem_categoria": "true"}).json()
    assert sorted(t["descricao"] for t in corpo["items"]) == ["Farmácia", "Geladeira"]
    # A transferência não tem categoria por regra e não entra no atalho.
    assert corpo["totais"]["total_despesa"] == "1234.29"
    # O contador do atalho não muda com o próprio atalho ligado.
    assert corpo["totais"]["sem_categoria"] == 2


def test_total_por_dia(client: TestClient, session: Session) -> None:
    _semear(session)
    resposta = client.get("/transacoes/dias", params=OUTUBRO)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json() == [
        {"data": "2026-10-16", "despesas": "1372.80", "receitas": "0.00", "quantidade": 2},
        {"data": "2026-10-15", "despesas": "47.89", "receitas": "320.00", "quantidade": 3},
    ]
    so_receita = client.get("/transacoes/dias", params={**OUTUBRO, "tipos": "receita"}).json()
    assert so_receita == [
        {"data": "2026-10-15", "despesas": "0.00", "receitas": "320.00", "quantidade": 1}
    ]


def test_busca_por_valor_e_descricao_original(client: TestClient, session: Session) -> None:
    _semear(session)

    def buscar(texto: str) -> list[str]:
        corpo = client.get("/transacoes", params={**OUTUBRO, "texto": texto}).json()
        return sorted(t["descricao"] for t in corpo["items"])

    assert buscar("186,40") == ["Supermercado"]
    assert buscar("R$ 1.186,40") == ["Geladeira"]
    assert buscar("47.89") == ["Farmácia"]
    assert buscar("PARA O NUBANK") == ["Para o Nubank"]
    assert buscar("mercado") == ["Supermercado"]
