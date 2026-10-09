"""Mapeamento de categorias da Pluggy (D-21): service, router e enriquecimento."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido
from app.models import Categoria, CategoriaPluggy, Local, RegraCategorizacao
from app.services.base import RegraViolada
from app.services.categorias_pluggy import CategoriaPluggyService
from app.services.ingestao import _ContextoEnriquecimento


@pytest.fixture
def categorias(session: Session) -> dict[str, Categoria]:
    mercado = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    restaurante = Categoria(nome="Restaurante", tipo=TipoTransacao.DESPESA)
    salario = Categoria(nome="Salário", tipo=TipoTransacao.RECEITA)
    inativa = Categoria(nome="Velha", tipo=TipoTransacao.DESPESA, ativo=False)
    session.add_all([mercado, restaurante, salario, inativa])
    session.commit()
    return {"mercado": mercado, "restaurante": restaurante, "salario": salario, "inativa": inativa}


def _mapear(session: Session, pluggy_id: str, nome: str, categoria: Categoria) -> CategoriaPluggy:
    obj = CategoriaPluggyService(session).criar(
        {
            "pluggy_categoria_id": pluggy_id,
            "pluggy_categoria_nome": nome,
            "categoria_id": categoria.id,
        }
    )
    session.commit()
    return obj


class TestService:
    def test_cria_e_le(self, session: Session, categorias: dict[str, Categoria]) -> None:
        obj = _mapear(session, "11000000", "Groceries", categorias["mercado"])
        assert obj.ativo is True
        assert obj.categoria_id == categorias["mercado"].id

    def test_transferencia_nao_aponta_para_despesa(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        for pluggy_id, nome in [("05000000", "Transfers"), ("05070000", "Transfer - PIX")]:
            with pytest.raises(RegraViolada, match="transferência"):
                _mapear(session, pluggy_id, nome, categorias["mercado"])

    def test_transferencia_pode_apontar_para_receita(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        assert _mapear(session, "05070000", "Transfer - PIX", categorias["salario"]).id

    def test_categoria_inexistente_ou_inativa_e_recusada(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        service = CategoriaPluggyService(session)
        with pytest.raises(RegraViolada, match="não existe"):
            service.criar(
                {"pluggy_categoria_id": "1", "pluggy_categoria_nome": "x", "categoria_id": 99999}
            )
        with pytest.raises(RegraViolada, match="inativa"):
            _mapear(session, "1", "x", categorias["inativa"])

    def test_trocar_para_despesa_tambem_e_checado(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        obj = _mapear(session, "05070000", "Transfer - PIX", categorias["salario"])
        with pytest.raises(RegraViolada):
            CategoriaPluggyService(session).atualizar(
                obj.id, {"categoria_id": categorias["mercado"].id}
            )

    def test_remover_desativa_e_libera_o_id(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        obj = _mapear(session, "11000000", "Groceries", categorias["mercado"])
        CategoriaPluggyService(session).remover(obj.id)
        session.commit()
        session.refresh(obj)
        assert obj.ativo is False and obj.deleted_em is not None
        assert _mapear(session, "11000000", "Groceries", categorias["restaurante"]).id != obj.id


class TestRouter:
    def test_crud(self, client: TestClient, session: Session, categorias: dict[str, Any]) -> None:
        criado = client.post(
            "/categorias-pluggy",
            json={
                "pluggy_categoria_id": "11000000",
                "pluggy_categoria_nome": "Groceries",
                "categoria_id": categorias["mercado"].id,
            },
        )
        assert criado.status_code == 201, criado.text
        id_ = criado.json()["id"]

        assert client.get("/categorias-pluggy").json()["total"] == 1
        duplicado = client.post(
            "/categorias-pluggy",
            json={
                "pluggy_categoria_id": "11000000",
                "pluggy_categoria_nome": "Groceries",
                "categoria_id": categorias["restaurante"].id,
            },
        )
        assert duplicado.status_code == 409
        assert "já está mapeada" in duplicado.text

        alterado = client.patch(
            f"/categorias-pluggy/{id_}", json={"categoria_id": categorias["restaurante"].id}
        )
        assert alterado.json()["categoria_id"] == categorias["restaurante"].id
        assert client.delete(f"/categorias-pluggy/{id_}").json() == {"ok": True}
        assert client.get(f"/categorias-pluggy/{id_}").status_code == 404

    def test_transferencia_para_despesa_volta_422(
        self, client: TestClient, categorias: dict[str, Any]
    ) -> None:
        resposta = client.post(
            "/categorias-pluggy",
            json={
                "pluggy_categoria_id": "05000000",
                "pluggy_categoria_nome": "Transfers",
                "categoria_id": categorias["mercado"].id,
            },
        )
        assert resposta.status_code == 422


def _extraido(
    descricao: str = "PADARIA DO BAIRRO",
    tipo: TipoTransacao = TipoTransacao.DESPESA,
    categoria_externa_id: str | None = "11000000",
) -> ItemExtraido:
    return ItemExtraido(
        linha_bruta=descricao,
        linha_num=1,
        data=date(2026, 9, 1),
        valor=Decimal("10.00"),
        descricao=descricao,
        tipo=tipo,
        categoria_externa_id=categoria_externa_id,
        categoria_externa="Groceries",
    )


class TestEnriquecimento:
    """Ordem da D-21: regra do usuário > mapeamento da Pluggy > local conhecido."""

    def test_mapeamento_da_pluggy_da_a_categoria(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        _mapear(session, "11000000", "Groceries", categorias["mercado"])
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(_extraido())
        assert sugestao.categoria_id == categorias["mercado"].id
        assert sugestao.origem == "pluggy"
        assert sugestao.confianca == Decimal("0.90")

    def test_regra_do_usuario_vence_o_mapeamento(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        _mapear(session, "11000000", "Groceries", categorias["mercado"])
        session.add(
            RegraCategorizacao(
                padrao="PADARIA", tipo_match="contem", categoria_id=categorias["restaurante"].id
            )
        )
        session.commit()
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(_extraido())
        assert sugestao.categoria_id == categorias["restaurante"].id
        assert sugestao.origem == "regra"

    def test_mapeamento_vence_o_local_mas_o_local_ainda_e_casado(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        _mapear(session, "11000000", "Groceries", categorias["mercado"])
        local = Local(
            nome="Padaria do Bairro",
            nome_normalizado="PADARIA DO BAIRRO",
            categoria_padrao_id=categorias["restaurante"].id,
        )
        session.add(local)
        session.commit()
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(_extraido())
        assert sugestao.categoria_id == categorias["mercado"].id
        assert sugestao.local_id == local.id
        assert sugestao.origem == "pluggy"

    def test_sem_mapeamento_cai_no_local(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        session.add(
            Local(
                nome="Padaria do Bairro",
                nome_normalizado="PADARIA DO BAIRRO",
                categoria_padrao_id=categorias["restaurante"].id,
            )
        )
        session.commit()
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(_extraido())
        assert sugestao.categoria_id == categorias["restaurante"].id
        assert sugestao.origem == "alias"

    def test_tipo_diferente_nao_aplica(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        _mapear(session, "11000000", "Groceries", categorias["mercado"])
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(
            _extraido(tipo=TipoTransacao.RECEITA)
        )
        assert sugestao.categoria_id is None

    def test_transferencia_nao_recebe_categoria(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        _mapear(session, "05070000", "Transfer - PIX", categorias["salario"])
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(
            _extraido(tipo=TipoTransacao.TRANSFERENCIA, categoria_externa_id="05070000")
        )
        assert sugestao.categoria_id is None

    def test_mapeamento_desativado_nao_vale(
        self, session: Session, categorias: dict[str, Categoria]
    ) -> None:
        obj = _mapear(session, "11000000", "Groceries", categorias["mercado"])
        CategoriaPluggyService(session).atualizar(obj.id, {"ativo": False})
        session.commit()
        sugestao = _ContextoEnriquecimento.carregar(session).sugerir(_extraido())
        assert sugestao.categoria_id is None
