"""Estorno (D-34): promoção do item, ligação com a compra original e lançamento manual."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.enums import (
    StatusImportacao,
    StatusItem,
    TipoConta,
    TipoPagamento,
    TipoTransacao,
)
from app.models import (
    Categoria,
    Conta,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Local,
    Pessoa,
    Transacao,
)
from app.services.ingestao import ORIGEM_USUARIO, IngestaoService

D = TipoTransacao.DESPESA
OUTUBRO = date(2026, 10, 1)


@pytest.fixture
def base(session: Session) -> dict[str, Any]:
    ana, bia = Pessoa(nome="Ana"), Pessoa(nome="Bia")
    compras = Categoria(nome="Compras", tipo=TipoTransacao.DESPESA)
    lazer = Categoria(nome="Lazer", tipo=TipoTransacao.DESPESA)
    banco = Conta(nome="Banco", tipo=TipoConta.CORRENTE, titular_id=None)
    session.add_all([ana, bia, compras, lazer, banco])
    session.flush()
    # Cartão sem titular próprio: o titular vem da conta.
    banco.titular_id = ana.id
    cartao = FormaPagamento(apelido="Cartão", tipo=TipoPagamento.CREDITO, conta_id=banco.id)
    session.add(cartao)
    importacao = Importacao(
        arquivo_nome="x.json",
        hash_arquivo="estorno",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(importacao)
    session.flush()
    return {
        "ana": ana,
        "bia": bia,
        "compras": compras,
        "lazer": lazer,
        "cartao": cartao,
        "importacao": importacao,
    }


def _compra(
    session: Session, b: dict[str, Any], dia: int, valor: str, lugar: str, **extra: Any
) -> Transacao:
    t = Transacao(
        data=date(2026, 10, dia),
        competencia=OUTUBRO,
        valor=Decimal(valor),
        tipo=D,
        descricao=lugar,
        descricao_original=lugar,
        forma_pagamento_id=b["cartao"].id,
        categoria_id=extra.pop("categoria_id", b["compras"].id),
        pessoa_id=extra.pop("pessoa_id", b["bia"].id),
        **extra,
    )
    session.add(t)
    session.flush()
    return t


_seq = iter(range(1, 1000))


def _item_estorno(
    session: Session, b: dict[str, Any], dia: int, valor: str, lugar: str, **extra: Any
) -> ImportacaoItem:
    n = next(_seq)
    item = ImportacaoItem(
        importacao_id=b["importacao"].id,
        linha_bruta=lugar,
        linha_num=n,
        data=date(2026, 10, dia),
        valor=Decimal(valor),
        descricao_original=lugar,
        tipo_sugerido=TipoTransacao.ESTORNO,
        competencia_sugerida=OUTUBRO,
        forma_pagamento_sugerida_id=b["cartao"].id,
        categoria_sugerida_id=extra.pop("categoria_sugerida_id", b["lazer"].id),
        pessoa_sugerida_id=extra.pop("pessoa_sugerida_id", b["ana"].id),
        confianca=Decimal("0.70"),
        origem_sugestao=extra.pop("origem_sugestao", "pluggy"),
        status=StatusItem.PENDENTE,
        id_externo=f"est-{n}",
        **extra,
    )
    session.add(item)
    session.flush()
    return item


def _aprovar(session: Session, *itens: ImportacaoItem) -> list[Transacao]:
    resultado = IngestaoService(session).aprovar([i.id for i in itens])
    assert resultado["erros"] == [] and resultado["promovidos"] == len(itens), resultado
    session.flush()
    return [session.get(Transacao, i.transacao_id) for i in itens]  # type: ignore[misc]


class TestPromocao:
    def test_liga_a_original_e_copia_categoria_e_pessoa(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        compra = _compra(session, base, 2, "100.00", "LOJA UM")
        item = _item_estorno(session, base, 10, "100.00", "ESTORNO LOJA UM")
        (estorno,) = _aprovar(session, item)
        assert estorno.tipo is TipoTransacao.ESTORNO
        assert estorno.estorno_de_id == compra.id
        assert estorno.categoria_id == base["compras"].id  # e não a Lazer, da Pluggy
        assert estorno.pessoa_id == base["bia"].id  # e não a Ana, do cartão

    def test_escolha_do_usuario_na_revisao_vale_mais_que_a_original(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        compra = _compra(session, base, 2, "100.00", "LOJA UM")
        item = _item_estorno(session, base, 10, "100.00", "ESTORNO LOJA UM")
        IngestaoService(session).ajustar(item.id, {"categoria_sugerida_id": base["lazer"].id})
        assert item.origem_sugestao == ORIGEM_USUARIO
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id == compra.id  # a ligação continua
        assert estorno.categoria_id == base["lazer"].id
        assert estorno.pessoa_id == base["ana"].id

    def test_desempata_pelo_estabelecimento(self, session: Session, base: dict[str, Any]) -> None:
        _compra(session, base, 2, "50.00", "LOJA A")
        alvo = _compra(session, base, 3, "50.00", "LOJA B")
        item = _item_estorno(session, base, 10, "50.00", "LOJA B")
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id == alvo.id

    def test_empate_sem_estabelecimento_nao_adivinha(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        _compra(session, base, 2, "50.00", "LOJA A")
        _compra(session, base, 3, "50.00", "LOJA B")
        item = _item_estorno(session, base, 10, "50.00", "ESTORNO OUTRO")
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id is None
        assert estorno.categoria_id == base["lazer"].id
        assert estorno.pessoa_id == base["ana"].id

    def test_estorno_parcial_na_unica_compra_maior_do_estabelecimento(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        local = Local(nome="Loja C", nome_normalizado="LOJA C")
        session.add(local)
        session.flush()
        compra = _compra(session, base, 2, "200.00", "LOJA C", local_id=local.id)
        _compra(session, base, 3, "300.00", "OUTRA LOJA")
        item = _item_estorno(
            session, base, 10, "80.00", "ESTORNO PARCIAL", local_sugerido_id=local.id
        )
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id == compra.id
        assert estorno.valor == Decimal("80.00")

    def test_compra_fora_dos_90_dias_nao_conta(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        _compra(session, base, 2, "100.00", "LOJA UM")
        item = _item_estorno(session, base, 10, "100.00", "LOJA UM")
        item.data = date(2027, 2, 1)
        item.competencia_sugerida = date(2027, 2, 1)
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id is None

    def test_sem_original_e_sem_pessoa_vale_o_titular_do_cartao(
        self, session: Session, base: dict[str, Any]
    ) -> None:
        item = _item_estorno(session, base, 10, "33.00", "ESTORNO SOLTO", pessoa_sugerida_id=None)
        item.pessoa_sugerida_id = None
        (estorno,) = _aprovar(session, item)
        assert estorno.estorno_de_id is None
        assert estorno.categoria_id == base["lazer"].id
        assert estorno.pessoa_id == base["ana"].id  # a conta do cartão é da Ana

    def test_a_compra_do_mesmo_lote_e_achada(self, session: Session, base: dict[str, Any]) -> None:
        """Estorno e compra aprovados juntos: a compra entra primeiro, qualquer que seja a ordem."""
        n = next(_seq)
        compra_item = ImportacaoItem(
            importacao_id=base["importacao"].id,
            linha_bruta="LOJA NOVA",
            linha_num=n,
            data=date(2026, 10, 2),
            valor=Decimal("70.00"),
            descricao_original="LOJA NOVA",
            tipo_sugerido=D,
            competencia_sugerida=OUTUBRO,
            forma_pagamento_sugerida_id=base["cartao"].id,
            categoria_sugerida_id=base["compras"].id,
            pessoa_sugerida_id=base["bia"].id,
            confianca=Decimal("1.00"),
            status=StatusItem.PENDENTE,
            id_externo=f"compra-{n}",
        )
        session.add(compra_item)
        session.flush()
        estorno_item = _item_estorno(session, base, 10, "70.00", "ESTORNO LOJA NOVA")
        resultado = IngestaoService(session).aprovar([estorno_item.id, compra_item.id])
        assert resultado["promovidos"] == 2
        estorno = session.get(Transacao, estorno_item.transacao_id)
        assert estorno is not None
        assert estorno.estorno_de_id == compra_item.transacao_id
        assert estorno.pessoa_id == base["bia"].id

    def test_estorno_nao_conta_como_receita(self, session: Session, base: dict[str, Any]) -> None:
        item = _item_estorno(session, base, 10, "33.00", "ESTORNO SOLTO")
        _aprovar(session, item)
        receitas = session.scalar(
            select_count(session, TipoTransacao.RECEITA),
        )
        assert receitas == 0


def select_count(session: Session, tipo: TipoTransacao) -> Any:
    from sqlalchemy import select

    return select(func.count()).select_from(Transacao).where(Transacao.tipo == tipo)


class TestSugestaoDeCategoria:
    def test_estorno_recebe_a_categoria_de_despesa_do_mapeamento_da_pluggy(self) -> None:
        from app.ingestao.base import ItemExtraido
        from app.services.ingestao import _ContextoEnriquecimento

        contexto = _ContextoEnriquecimento([], [], [], {"08000000": (7, TipoTransacao.DESPESA)})
        item = ItemExtraido(
            linha_bruta="ESTORNO X",
            linha_num=1,
            data=date(2026, 10, 10),
            valor=Decimal("10.00"),
            descricao="Estorno X",
            tipo=TipoTransacao.ESTORNO,
            categoria_externa_id="08000000",
        )
        sugestao = contexto.sugerir(item)
        assert (sugestao.categoria_id, sugestao.origem) == (7, "pluggy")


# --------------------------------------------------------------------------
# API manual
# --------------------------------------------------------------------------


def _post(client: TestClient, **campos: Any) -> Any:
    corpo = {"data": "2026-10-10", "valor": "30.00", "descricao": "Estorno", **campos}
    return client.post("/transacoes", json=corpo)


class TestApiManual:
    def test_cria_estorno_ligado_a_uma_despesa_viva(self, client: TestClient) -> None:
        compra = _post(client, tipo="despesa", valor="100.00", descricao="Compra")
        assert compra.status_code == 201
        r = _post(client, tipo="estorno", estorno_de_id=compra.json()["id"])
        assert r.status_code == 201, r.text
        assert r.json()["tipo"] == "estorno"

    def test_estorno_sem_original_vale(self, client: TestClient) -> None:
        assert _post(client, tipo="estorno").status_code == 201

    def test_estorno_de_id_so_para_estorno(self, client: TestClient) -> None:
        compra = _post(client, tipo="despesa", valor="100.00").json()
        assert _post(client, tipo="despesa", estorno_de_id=compra["id"]).status_code == 422

    def test_original_inexistente_receita_ou_apagada_da_422(self, client: TestClient) -> None:
        receita = _post(client, tipo="receita", valor="100.00").json()
        apagada = _post(client, tipo="despesa", valor="101.00").json()
        assert client.delete(f"/transacoes/{apagada['id']}").status_code == 200
        for original in (999999, receita["id"], apagada["id"]):
            r = _post(client, tipo="estorno", estorno_de_id=original)
            assert r.status_code == 422, (original, r.text)

    def test_patch_liga_o_estorno_e_recusa_em_despesa(self, client: TestClient) -> None:
        compra = _post(client, tipo="despesa", valor="100.00").json()
        estorno = _post(client, tipo="estorno").json()
        r = client.patch(f"/transacoes/{estorno['id']}", json={"estorno_de_id": compra["id"]})
        assert r.status_code == 200, r.text
        r = client.patch(f"/transacoes/{compra['id']}", json={"estorno_de_id": compra["id"]})
        assert r.status_code == 422

    def test_listagem_filtra_por_tipo_estorno(self, client: TestClient) -> None:
        _post(client, tipo="despesa", valor="100.00")
        estorno = _post(client, tipo="estorno").json()
        r = client.get("/transacoes", params={"tipos": "estorno"})
        assert r.status_code == 200, r.text
        assert [t["id"] for t in r.json()["items"]] == [estorno["id"]]
        assert r.json()["totais"]["total_despesa"] == "-30.00"
