"""Script d34-reaplicar: simulação de estornos e aplicações/resgates (D-34).

O cenário monta uma importação da Pluggy com conta corrente e cartão, aprova os
itens como a revisão faria e deixa o usuário editar alguns. A simulação não
grava nada; `--executar` grava só as aplicações e resgates, e recusa o estorno.
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
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    Transacao,
)
from app.services.d34_reaplicar import (
    AUTOR,
    MENSAGEM_ESTORNO_AGUARDA_SCHEMA,
    AguardaSchema,
    Compra,
    D34ReaplicarService,
    achar_original,
    estabelecimento_de,
)
from app.services.ingestao import IngestaoService
from scripts import d34_reaplicar

CORRENTE, CARTAO = "acc-corrente", "acc-cartao"
ABRIL = date(2025, 4, 1)
RENDIMENTO = ("03000000", "Proceeds interests and dividends")
INVESTIMENTO = ("07000000", "Investments")
COMPRAS = ("08000000", "Shopping")
SEM_MAPA = ("09000000", "Services")


def _tx(
    id_: str,
    conta: str,
    dia: str,
    valor: str,
    tipo: str,
    descricao: str,
    categoria: tuple[str, str],
    operacao: str | None = None,
) -> dict[str, Any]:
    dados: dict[str, Any] = {
        "id": id_,
        "accountId": conta,
        "date": f"{dia}T15:00:00Z",
        "amount": float(valor),
        "description": descricao,
        "descriptionRaw": descricao,
        "status": "POSTED",
        "type": tipo,
        "operationType": operacao,
        "currencyCode": "BRL",
        "categoryId": categoria[0],
        "category": categoria[1],
    }
    if conta == CARTAO:
        dados["creditCardMetadata"] = {"cardNumber": "1111", "billId": "f1"}
    return dados


TRANSACOES = [
    # Conta corrente.
    _tx(
        "r-resg",
        CORRENTE,
        "2025-04-02",
        "150.00",
        "CREDIT",
        "RESG A",
        INVESTIMENTO,
        "RESGATE_APLIC_FINANCEIRA",
    ),
    _tx(
        "r-rend",
        CORRENTE,
        "2025-04-03",
        "0.03",
        "CREDIT",
        "REND B",
        RENDIMENTO,
        "RESGATE_APLIC_FINANCEIRA",
    ),
    _tx(
        "r-apl",
        CORRENTE,
        "2025-04-04",
        "-80.00",
        "DEBIT",
        "APLIC C",
        INVESTIMENTO,
        "APLICACAO_FINANCEIRA",
    ),
    _tx(
        "r-edit",
        CORRENTE,
        "2025-04-05",
        "60.00",
        "CREDIT",
        "RESG D",
        INVESTIMENTO,
        "RESGATE_APLIC_FINANCEIRA",
    ),
    _tx("r-pix", CORRENTE, "2025-04-06", "-45.10", "DEBIT", "MERCADO PIX", COMPRAS, "PIX"),
    # Cartão: a compra e os estornos (crédito no cartão que não é pagamento).
    _tx("k-compra", CARTAO, "2025-04-02", "100.00", "DEBIT", "LOJA UM", COMPRAS),
    _tx("k-est-original", CARTAO, "2025-04-10", "-100.00", "CREDIT", "ESTORNO LOJA UM", COMPRAS),
    _tx("k-est-sugestao", CARTAO, "2025-04-11", "-33.00", "CREDIT", "ESTORNO OUTRA", COMPRAS),
    _tx("k-est-sem", CARTAO, "2025-04-12", "-12.00", "CREDIT", "ESTORNO SEM MAPA", SEM_MAPA),
    _tx("k-est-edit", CARTAO, "2025-04-13", "-7.00", "CREDIT", "ESTORNO EDITADO", COMPRAS),
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
    credito = FormaPagamento(
        apelido="Crédito Banco A 1111",
        tipo=TipoPagamento.CREDITO,
        conta_id=banco.id,
        titular_id=titular.id,
    )
    compras = Categoria(nome="Compras", tipo=TipoTransacao.DESPESA)
    session.add_all([pix, credito, compras])
    session.flush()
    session.add(
        CategoriaPluggy(
            pluggy_categoria_id=COMPRAS[0],
            pluggy_categoria_nome=COMPRAS[1],
            categoria_id=compras.id,
        )
    )
    importacao = Importacao(
        arquivo_nome="pluggy_20250601T100000.json",
        hash_arquivo="d34-reaplicar",
        arquivo_conteudo=_comprovante(),
        arquivo_tipo="application/json",
        origem="pluggy",
        parser_usado="pluggy_sync",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(importacao)
    session.flush()

    _autor(session, "sync_pluggy")
    itens: dict[str, ImportacaoItem] = {}
    for t in TRANSACOES:
        dia = date.fromisoformat(t["date"][:10])
        cartao = t["accountId"] == CARTAO
        despesa = t["type"] == "DEBIT"
        item = ImportacaoItem(
            importacao_id=importacao.id,
            linha_bruta=t["descriptionRaw"],
            descricao_original=t["descriptionRaw"],
            data=dia,
            valor=abs(Decimal(str(t["amount"]))),
            tipo_sugerido=TipoTransacao.DESPESA if despesa else TipoTransacao.RECEITA,
            competencia_sugerida=ABRIL,
            forma_pagamento_sugerida_id=credito.id if cartao else pix.id,
            categoria_sugerida_id=compras.id if t["id"] == "k-compra" else None,
            pessoa_sugerida_id=titular.id,
            confianca=Decimal("1.00"),
            origem_sugestao="parser",
            status=StatusItem.PENDENTE,
            id_externo=t["id"],
        )
        session.add(item)
        itens[t["id"]] = item
    session.commit()

    IngestaoService(session).aprovar([i.id for i in itens.values()])
    session.commit()
    transacoes = {
        id_externo: session.get(Transacao, item.transacao_id) for id_externo, item in itens.items()
    }

    # O usuário editou duas transações depois de aprovadas.
    _autor(session, "usuario")
    for chave in ("r-edit", "k-est-edit"):
        edit = transacoes[chave]
        assert edit is not None
        edit.descricao = "Editada à mão"
        session.commit()
    _autor(session, "teste")
    return {"itens": itens, "t": transacoes, "importacao": importacao, "compras": compras}


def _vivas(session: Session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(Transacao).where(Transacao.deleted_em.is_(None))
        )
        or 0
    )


class TestAcharOriginal:
    def _compra(self, id_: int, valor: str, lugar: str, local_id: int | None = None) -> Compra:
        return Compra(
            id=id_,
            data=date(2025, 4, 2),
            valor=Decimal(valor),
            local_id=local_id,
            estabelecimento=estabelecimento_de(lugar),
            categoria_id=None,
            pessoa_id=None,
        )

    def test_mesmo_valor_unico(self) -> None:
        achada = achar_original(
            valor=Decimal("10.00"),
            local_id=None,
            estabelecimento="",
            candidatas=[self._compra(1, "10.00", "A"), self._compra(2, "11.00", "B")],
        )
        assert achada is not None and achada.id == 1

    def test_mesmo_valor_varios_desempata_pelo_estabelecimento(self) -> None:
        candidatas = [self._compra(1, "10.00", "Loja A 1/3"), self._compra(2, "10.00", "Loja B")]
        achada = achar_original(
            valor=Decimal("10.00"),
            local_id=None,
            estabelecimento=estabelecimento_de("LOJA B"),
            candidatas=candidatas,
        )
        assert achada is not None and achada.id == 2
        # Sem como desempatar: nada.
        assert (
            achar_original(
                valor=Decimal("10.00"), local_id=None, estabelecimento="", candidatas=candidatas
            )
            is None
        )

    def test_estorno_parcial_so_no_mesmo_estabelecimento(self) -> None:
        achada = achar_original(
            valor=Decimal("5.00"),
            local_id=7,
            estabelecimento="",
            candidatas=[self._compra(1, "10.00", "X", local_id=7), self._compra(2, "9.00", "Y")],
        )
        assert achada is not None and achada.id == 1

    def test_estabelecimento_ignora_acento_parcela_e_pontuacao(self) -> None:
        assert estabelecimento_de("Padaria  São-João 2/10") == "padaria sao joao"


class TestSimulacao:
    def test_estornos(self, session: Session, cenario: dict[str, Any]) -> None:
        antes = _vivas(session)
        plano = D34ReaplicarService(session).planejar()
        session.rollback()

        por_desfecho = {e.transacao_id: e for e in plano.estornos}
        t = cenario["t"]
        assert len(plano.estornos) == 4
        original = por_desfecho[t["k-est-original"].id]
        assert (original.desfecho, original.categoria, original.pessoa) == (
            "original",
            "Compras",
            "Titular",
        )
        sugestao = por_desfecho[t["k-est-sugestao"].id]
        assert (sugestao.desfecho, sugestao.categoria, sugestao.pessoa) == (
            "sugestao",
            "Compras",
            "Titular",
        )
        assert por_desfecho[t["k-est-sem"].id].desfecho == "sem_destino"
        assert por_desfecho[t["k-est-edit"].id].desfecho == "editado"
        assert _vivas(session) == antes

    def test_aplicacoes_e_resgates(self, session: Session, cenario: dict[str, Any]) -> None:
        plano = D34ReaplicarService(session).planejar()
        session.rollback()

        t = cenario["t"]
        por_id = {a.transacao_id: a.desfecho for a in plano.aplicacoes}
        assert por_id == {
            t["r-resg"].id: "transferencia",
            t["r-rend"].id: "rendimento",
            t["r-apl"].id: "transferencia",
            t["r-edit"].id: "editado",
        }

    def test_totais_do_mes(self, session: Session, cenario: dict[str, Any]) -> None:
        plano = D34ReaplicarService(session).planejar()
        session.rollback()

        assert plano.meses() == [ABRIL]
        antes = plano.atuais[ABRIL]
        # Receitas: resgates 150 + 0,03 + 60 e os estornos 100 + 33 + 12 + 7.
        assert antes.receitas == Decimal("362.03")
        # Despesas: pix 45,10, compra 100 e a aplicação de 80.
        assert antes.despesas == Decimal("225.10")
        depois = plano.depois(ABRIL)
        # Saem das receitas o resgate (150) e os estornos não editados (145).
        assert depois.receitas == Decimal("362.03") - Decimal("150.00") - Decimal("145.00")
        # Saem das despesas a aplicação (80) e os mesmos estornos (145).
        assert depois.despesas == Decimal("225.10") - Decimal("80.00") - Decimal("145.00")

    def test_estorno_nao_executa(self, session: Session, cenario: dict[str, Any]) -> None:
        service = D34ReaplicarService(session)
        with pytest.raises(AguardaSchema, match="aguarda a mudança de schema"):
            service.executar_estornos(service.planejar())


class TestExecucao:
    def test_devolve_a_revisao_so_o_que_ninguem_editou(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        t, itens = cenario["t"], cenario["itens"]
        service = D34ReaplicarService(session)
        resultado = service.executar_aplicacoes(service.planejar())
        session.commit()
        session.expire_all()

        assert resultado == {"devolvidas_a_revisao": 2, "mudou_desde_o_plano": 0}
        for chave in ("r-resg", "r-apl"):
            transacao = session.get(Transacao, t[chave].id)
            assert transacao is not None and transacao.deleted_em is not None
            item = session.get(ImportacaoItem, itens[chave].id)
            assert item is not None
            assert item.status is StatusItem.PENDENTE and item.transacao_id is None
            assert item.tipo_sugerido is TipoTransacao.TRANSFERENCIA
            assert "D-34" in (item.observacao or "")
        for chave in ("r-rend", "r-edit", "r-pix", "k-est-original"):
            transacao = session.get(Transacao, t[chave].id)
            assert transacao is not None and transacao.deleted_em is None, chave
        importacao = session.get(Importacao, cenario["importacao"].id)
        assert importacao is not None
        assert importacao.status is StatusImportacao.AGUARDANDO_REVISAO
        assert importacao.itens_aprovados == len(TRANSACOES) - 2
        autores = set(session.scalars(select(Auditoria.autor).where(Auditoria.autor == AUTOR)))
        assert autores == {AUTOR}

    def test_rodar_de_novo_nao_muda_nada(self, session: Session, cenario: dict[str, Any]) -> None:
        service = D34ReaplicarService(session)
        service.executar_aplicacoes(service.planejar())
        session.commit()
        vivas = _vivas(session)
        segundo = service.executar_aplicacoes(service.planejar())
        assert segundo == {"devolvidas_a_revisao": 0, "mudou_desde_o_plano": 0}
        assert _vivas(session) == vivas


class TestScript:
    def test_simulacao_nao_grava_e_nao_mostra_descricao(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        vivas = _vivas(session)
        assert d34_reaplicar.main([]) == 0
        saida = capsys.readouterr().out
        assert "Nada foi gravado." in saida
        assert "ESTORNOS" in saida and "APLICAÇÕES E RESGATES" in saida
        assert "2025-04" in saida
        for descricao in ("LOJA UM", "RESG A", "REND B", "MERCADO PIX"):
            assert descricao not in saida
        session.expire_all()
        assert _vivas(session) == vivas

    def test_executar_estornos_recusa(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        vivas = _vivas(session)
        assert d34_reaplicar.main(["--executar", "--item", "estornos"]) == 2
        assert MENSAGEM_ESTORNO_AGUARDA_SCHEMA in capsys.readouterr().err
        session.expire_all()
        assert _vivas(session) == vivas

    def test_executar_grava_so_as_aplicacoes(
        self, session: Session, cenario: dict[str, Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        vivas = _vivas(session)
        assert d34_reaplicar.main(["--executar"]) == 0
        saida = capsys.readouterr().out
        assert MENSAGEM_ESTORNO_AGUARDA_SCHEMA in saida
        session.expire_all()
        # Só o resgate e a aplicação saíram; nenhum estorno foi tocado.
        assert _vivas(session) == vivas - 2
        estornos = cenario["t"]
        for chave in ("k-est-original", "k-est-sugestao", "k-est-sem", "k-est-edit"):
            transacao = session.get(Transacao, estornos[chave].id)
            assert transacao is not None and transacao.deleted_em is None
            assert transacao.tipo is TipoTransacao.RECEITA
