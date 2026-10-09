"""Sincronização da Pluggy para o staging (fase 5b, passo 6).

A Pluggy é um leitor falso em memória: o que se testa aqui é a sync — janela,
deduplicação, duplicata, encargos, forma do mapeamento, isolamento de erro e
simulação —, contra o Postgres de verdade.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Auditoria,
    Categoria,
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    RegraCategorizacao,
)
from app.pluggy.modelos import Conta as ContaRemota
from app.pluggy.modelos import Fatura, Transacao
from app.services.sync_pluggy import SyncPluggyService

HOJE = date(2025, 5, 20)
ITEM = "item-1"
CORRENTE = "acc-corrente"
CARTAO = "acc-cartao"


class LeitorFalso:
    def __init__(self) -> None:
        self.contas = [
            ContaRemota.model_validate(
                {"id": CORRENTE, "itemId": ITEM, "type": "BANK", "subtype": "CHECKING_ACCOUNT"}
            ),
            ContaRemota.model_validate(
                {"id": CARTAO, "itemId": ITEM, "type": "CREDIT", "subtype": "CREDIT_CARD"}
            ),
        ]
        self.transacoes: dict[str, list[Transacao]] = {CORRENTE: [], CARTAO: []}
        self.faturas: dict[str, list[Fatura]] = {CARTAO: []}
        self.falhar: set[str] = set()
        self.pedidos: list[tuple[str, date, date]] = []

    def listar_contas(self, item_id: str, tipo: str | None = None) -> list[ContaRemota]:
        return self.contas

    def listar_transacoes(self, account_id: str, desde: date, ate: date) -> list[Transacao]:
        self.pedidos.append((account_id, desde, ate))
        if account_id in self.falhar:
            raise RuntimeError("Pluggy fora do ar para esta conta")
        return list(self.transacoes[account_id])

    def listar_faturas(self, account_id: str) -> list[Fatura]:
        if account_id in self.falhar:
            raise RuntimeError("Pluggy fora do ar para esta conta")
        return list(self.faturas.get(account_id, []))


def _tx(
    id_: str,
    conta: str,
    quando: str,
    valor: str,
    *,
    tipo: str = "DEBIT",
    status: str = "POSTED",
    descricao: str = "MERCADO EXEMPLO",
    fatura: str | None = None,
    cartao: str = "1111",
    operacao: str | None = None,
    categoria: str | None = None,
    categoria_id: str | None = None,
) -> Transacao:
    dados: dict[str, Any] = {
        "id": id_,
        "accountId": conta,
        "date": quando,
        "amount": Decimal(valor),
        "description": descricao,
        "descriptionRaw": descricao,
        "status": status,
        "type": tipo,
        "operationType": operacao,
        "category": categoria,
        "categoryId": categoria_id,
        "currencyCode": "BRL",
    }
    if conta == CARTAO:
        dados["creditCardMetadata"] = {"cardNumber": cartao, "billId": fatura}
    return Transacao.model_validate(dados)


def _fatura(id_: str, fecha: str, vence: str, total: str) -> Fatura:
    return Fatura.model_validate(
        {
            "id": id_,
            "billClosingDate": f"{fecha}T00:00:00.000Z",
            "dueDate": f"{vence}T00:00:00.000Z",
            "totalAmount": Decimal(total),
        }
    )


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    titular = Pessoa(nome="Titular")
    outra = Pessoa(nome="Outra pessoa")
    session.add_all([titular, outra])
    session.flush()
    banco = Conta(nome="Banco A", tipo=TipoConta.CORRENTE, titular_id=titular.id)
    session.add(banco)
    session.flush()
    # Crédito genérico com o menor id e outro titular: se a sync caísse nele,
    # forma e pessoa sairiam erradas e o teste perceberia.
    generico = FormaPagamento(
        apelido="Cartão de crédito genérico",
        tipo=TipoPagamento.CREDITO,
        conta_id=banco.id,
        titular_id=outra.id,
    )
    session.add(generico)
    session.flush()
    pix = FormaPagamento(
        apelido="Pix Banco A", tipo=TipoPagamento.PIX, conta_id=banco.id, titular_id=titular.id
    )
    credito = FormaPagamento(
        apelido="Crédito Banco A •••• 1111",
        tipo=TipoPagamento.CREDITO,
        conta_id=banco.id,
        titular_id=titular.id,
        dia_fechamento=3,
        dia_vencimento=10,
    )
    session.add_all([pix, credito])
    session.flush()
    mapa_corrente = ContaPluggy(
        pluggy_item_id=ITEM,
        pluggy_account_id=CORRENTE,
        conta_id=banco.id,
        forma_pagamento_id=pix.id,
        sincronizar_desde=date(2025, 3, 1),
    )
    mapa_cartao = ContaPluggy(
        pluggy_item_id=ITEM,
        pluggy_account_id=CARTAO,
        conta_id=banco.id,
        forma_pagamento_id=credito.id,
        sincronizar_desde=date(2025, 3, 4),
    )
    session.add_all([mapa_corrente, mapa_cartao])
    session.commit()
    return {
        "titular": titular,
        "generico": generico,
        "pix": pix,
        "credito": credito,
        "mapa_corrente": mapa_corrente,
        "mapa_cartao": mapa_cartao,
    }


def _sync(session: Session, leitor: LeitorFalso, *, simular: bool = False) -> Any:
    resultado = SyncPluggyService(
        session, leitor, hoje=HOJE, agora=lambda: datetime(2025, 5, 20, 12, tzinfo=UTC)
    ).sincronizar(simular=simular)
    session.commit()
    return resultado


def _itens(session: Session) -> list[ImportacaoItem]:
    return list(
        session.scalars(
            select(ImportacaoItem)
            .where(ImportacaoItem.deleted_em.is_(None))
            .order_by(ImportacaoItem.id)
        )
    )


def _conta(resultado: Any, mapa: ContaPluggy) -> Any:
    return next(c for c in resultado.contas if c.mapeamento_id == mapa.id)


class TestGravacao:
    def test_uma_importacao_json_com_os_itens_das_contas(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "87.90")]
        leitor.transacoes[CARTAO] = [
            _tx("k1", CARTAO, "2025-03-20T15:00:00Z", "87.90", fatura="f1"),
            _tx("k2", CARTAO, "2025-05-01T15:00:00Z", "12.30", status="PENDING"),
        ]

        resultado = _sync(session, leitor)

        importacoes = list(session.scalars(select(Importacao)))
        assert len(importacoes) == 1
        imp = importacoes[0]
        assert resultado.importacao_id == imp.id
        assert (imp.origem, imp.arquivo_tipo) == ("pluggy", "application/json")
        assert imp.status is StatusImportacao.AGUARDANDO_REVISAO
        assert [i.id_externo for i in _itens(session)] == ["c1", "k1"]
        assert _conta(resultado, cenario["mapa_cartao"]).pendentes_ignoradas == 1

        cartao = next(i for i in _itens(session) if i.id_externo == "k1")
        assert cartao.competencia_sugerida == date(2025, 4, 1)
        assert cartao.forma_pagamento_sugerida_id == cenario["credito"].id
        assert cartao.pessoa_sugerida_id == cenario["titular"].id

        autores = set(
            session.scalars(select(Auditoria.autor).where(Auditoria.tabela == "importacao_itens"))
        )
        assert autores == {"sync_pluggy"}

        session.refresh(cenario["mapa_corrente"])
        assert cenario["mapa_corrente"].ultimo_sync_em is not None

    def test_sem_item_novo_nao_cria_importacao(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        resultado = _sync(session, LeitorFalso())
        assert resultado.importacao_id is None
        assert session.scalar(select(func.count()).select_from(Importacao)) == 0
        # A conta foi lida sem erro: o último sync anda mesmo sem novidade.
        session.refresh(cenario["mapa_cartao"])
        assert cenario["mapa_cartao"].ultimo_sync_em is not None


class TestJanela:
    def test_janela_volta_sete_dias_do_ultimo_sync(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        mapa = cenario["mapa_corrente"]
        mapa.ultimo_sync_em = datetime(2025, 4, 20, 12, tzinfo=UTC)
        session.commit()
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("velha", CORRENTE, "2025-04-12T15:00:00Z", "-10"),
            _tx("na-sobreposicao", CORRENTE, "2025-04-14T15:00:00Z", "-20"),
        ]

        resultado = _sync(session, leitor)

        conta = _conta(resultado, mapa)
        assert conta.janela_inicio == date(2025, 4, 13)
        assert conta.fora_da_janela == 1
        assert [i.id_externo for i in _itens(session)] == ["na-sobreposicao"]
        # Pede um dia antes à Pluggy: o filtro dela é em UTC.
        assert (CORRENTE, date(2025, 4, 12), HOJE) in leitor.pedidos

    def test_nada_antes_do_corte(self, session: Session, cenario: dict[str, Any]) -> None:
        leitor = LeitorFalso()
        # 02:00 UTC de 01/03 é 23:00 de 28/02 em São Paulo: antes do corte.
        leitor.transacoes[CORRENTE] = [_tx("borda", CORRENTE, "2025-03-01T02:00:00Z", "-10")]
        resultado = _sync(session, leitor)
        assert _conta(resultado, cenario["mapa_corrente"]).fora_da_janela == 1
        assert _itens(session) == []


class TestDeduplicacao:
    @pytest.mark.parametrize(
        "status", [StatusItem.PENDENTE, StatusItem.REJEITADO, StatusItem.DUPLICADO]
    )
    def test_id_existente_em_qualquer_status_nao_volta(
        self, session: Session, cenario: dict[str, Any], status: StatusItem
    ) -> None:
        imp = Importacao(
            arquivo_nome="anterior.json",
            hash_arquivo="anterior",
            arquivo_tipo="application/json",
            origem="pluggy",
            status=StatusImportacao.AGUARDANDO_REVISAO,
        )
        session.add(imp)
        session.flush()
        session.add(
            ImportacaoItem(importacao_id=imp.id, linha_bruta="X", id_externo="c1", status=status)
        )
        session.commit()
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]

        resultado = _sync(session, leitor)

        assert _conta(resultado, cenario["mapa_corrente"]).ja_existentes == 1
        assert resultado.importacao_id is None

    def test_rodar_duas_vezes_nao_cria_nada_na_segunda(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "100.00")]
        leitor.transacoes[CARTAO] = [
            _tx("k1", CARTAO, "2025-03-20T15:00:00Z", "87.90", fatura="f1")
        ]

        _sync(session, leitor)
        antes = len(_itens(session))
        segunda = _sync(session, leitor)

        assert segunda.importacao_id is None
        assert segunda.itens_novos == 0
        assert len(_itens(session)) == antes
        assert session.scalar(select(func.count()).select_from(Importacao)) == 1


class TestFormaDoMapeamento:
    def test_cartao_virtual_usa_a_forma_do_mapeamento(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "30.00")]
        leitor.transacoes[CARTAO] = [
            _tx("v1", CARTAO, "2025-03-20T15:00:00Z", "30.00", fatura="f1", cartao="9999")
        ]

        _sync(session, leitor)

        (item,) = _itens(session)
        assert item.forma_pagamento_sugerida_id == cenario["credito"].id
        assert item.forma_pagamento_sugerida_id != cenario["generico"].id
        assert item.pessoa_sugerida_id == cenario["titular"].id

    def test_conta_corrente_usa_a_forma_do_mapeamento(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]
        _sync(session, leitor)
        (item,) = _itens(session)
        assert item.forma_pagamento_sugerida_id == cenario["pix"].id


class TestDuplicataPossivel:
    def test_no_mesmo_lote_marca_os_dois_sem_descartar(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "0")]
        leitor.transacoes[CARTAO] = [
            _tx(
                f"p{n}",
                CARTAO,
                "2025-04-10T03:00:00Z",
                "-950.40",
                tipo="CREDIT",
                descricao="Pagamento recebido",
                fatura="f1",
                operacao="PAGAMENTO_FATURA",
                categoria="Credit card payment",
            )
            for n in (1, 2)
        ]

        resultado = _sync(session, leitor)

        itens = _itens(session)
        assert [i.id_externo for i in itens] == ["p1", "p2"]
        for item in itens:
            assert item.observacao is not None and "Possível duplicata" in item.observacao
            assert item.confianca is not None and item.confianca <= Decimal("0.50")
        assert _conta(resultado, cenario["mapa_cartao"]).possiveis_duplicatas == 2

    def test_contra_o_staging(self, session: Session, cenario: dict[str, Any]) -> None:
        leitor = LeitorFalso()
        # Datas dentro da janela da segunda execução (último sync menos 7 dias).
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-05-15T15:00:00Z", "-45.10")]
        _sync(session, leitor)

        leitor.transacoes[CORRENTE] = [_tx("c2", CORRENTE, "2025-05-15T18:00:00Z", "-45.10")]
        _sync(session, leitor)

        segundo = next(i for i in _itens(session) if i.id_externo == "c2")
        assert segundo.observacao is not None and "c1" in segundo.observacao
        primeiro = next(i for i in _itens(session) if i.id_externo == "c1")
        assert primeiro.observacao is None

    def test_valor_diferente_nao_e_duplicata(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10"),
            _tx("c2", CORRENTE, "2025-04-02T16:00:00Z", "-45.11"),
        ]
        _sync(session, leitor)
        assert all(i.observacao is None for i in _itens(session))


class TestEncargos:
    def _leitor(self, total: str) -> LeitorFalso:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", total)]
        leitor.transacoes[CARTAO] = [
            _tx("k1", CARTAO, "2025-03-20T15:00:00Z", "100.00", fatura="f1"),
            _tx("k2", CARTAO, "2025-03-25T15:00:00Z", "-10.00", tipo="CREDIT", fatura="f1"),
            # Pagamento não entra na soma das compras.
            _tx(
                "pg",
                CARTAO,
                "2025-04-10T03:00:00Z",
                "-500.00",
                tipo="CREDIT",
                descricao="Pagamento recebido",
                fatura="f1",
                operacao="PAGAMENTO",
                categoria="Credit card payment",
            ),
        ]
        return leitor

    def test_total_maior_que_as_compras_gera_item(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        resultado = _sync(session, self._leitor("123.29"))

        encargo = next(i for i in _itens(session) if i.id_externo == "bill:f1:encargos")
        assert encargo.valor == Decimal("33.29")
        assert encargo.tipo_sugerido is TipoTransacao.DESPESA
        assert encargo.competencia_sugerida == date(2025, 4, 1)
        assert encargo.confianca == Decimal("0.50")  # min com a sugestão sem regra
        assert encargo.observacao is not None and "Deduzido" in encargo.observacao
        assert encargo.linha_bruta == "Encargos da fatura 04/2025"
        assert [e.valor for e in _conta(resultado, cenario["mapa_cartao"]).encargos] == [
            Decimal("33.29")
        ]

    def test_encargo_sugere_a_categoria_de_juros_mesmo_com_regra(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        juros = Categoria(nome="Juros e encargos", tipo=TipoTransacao.DESPESA)
        outra = Categoria(nome="Outra", tipo=TipoTransacao.DESPESA)
        session.add_all([juros, outra])
        session.flush()
        # Regra que casaria com o texto do encargo: a categoria fixa vence.
        session.add(RegraCategorizacao(padrao="ENCARGOS", categoria_id=outra.id))
        session.commit()

        simulado = _sync(session, self._leitor("123.29"), simular=True)
        amostra = _conta(simulado, cenario["mapa_cartao"]).amostra
        assert (
            next(a for a in amostra if a["id_externo"] == "bill:f1:encargos")["categoria_id"]
            == juros.id
        )

        _sync(session, self._leitor("123.29"))
        encargo = next(i for i in _itens(session) if i.id_externo == "bill:f1:encargos")
        assert encargo.categoria_sugerida_id == juros.id
        compra = next(i for i in _itens(session) if i.id_externo == "k1")
        assert compra.categoria_sugerida_id != juros.id

    def test_total_igual_nao_gera_nada(self, session: Session, cenario: dict[str, Any]) -> None:
        # Total com 4 casas, como a Pluggy manda: sobra menos de um centavo.
        resultado = _sync(session, self._leitor("90.0033"))
        assert not any(i.id_externo == "bill:f1:encargos" for i in _itens(session))
        assert _conta(resultado, cenario["mapa_cartao"]).encargos == []

    def test_compras_maiores_que_o_total_so_avisam(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        resultado = _sync(session, self._leitor("50.00"))
        assert not any(i.id_externo == "bill:f1:encargos" for i in _itens(session))
        conta = _conta(resultado, cenario["mapa_cartao"])
        assert any("passam do total" in a for a in conta.avisos)

    def test_encargos_nao_duplicam_ao_repetir(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = self._leitor("123.29")
        _sync(session, leitor)
        segunda = _sync(session, leitor)
        encargos = [i for i in _itens(session) if i.id_externo == "bill:f1:encargos"]
        assert len(encargos) == 1
        assert _conta(segunda, cenario["mapa_cartao"]).encargos == []

    def test_fatura_dividida_pelo_corte_nao_gera_encargo(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = self._leitor("500.00")
        # Compra de antes do corte (04/03) na mesma fatura: a diferença seria
        # compra faltando, não encargo.
        leitor.transacoes[CARTAO].append(
            _tx("antiga", CARTAO, "2025-03-02T15:00:00Z", "5.00", fatura="f1")
        )
        _sync(session, leitor)
        assert not any(i.id_externo == "bill:f1:encargos" for i in _itens(session))

    def test_fatura_aberta_nao_gera_encargo(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f9", "2025-05-25", "2025-06-01", "999.00")]
        leitor.transacoes[CARTAO] = [_tx("k1", CARTAO, "2025-05-02T15:00:00Z", "10", fatura="f9")]
        _sync(session, leitor)
        assert not any((i.id_externo or "").startswith("bill:") for i in _itens(session))


class TestErroIsolado:
    def test_erro_numa_conta_nao_derruba_as_outras(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]
        leitor.falhar.add(CARTAO)

        resultado = _sync(session, leitor)

        assert _conta(resultado, cenario["mapa_cartao"]).erro is not None
        assert _conta(resultado, cenario["mapa_corrente"]).erro is None
        assert [i.id_externo for i in _itens(session)] == ["c1"]
        session.refresh(cenario["mapa_cartao"])
        session.refresh(cenario["mapa_corrente"])
        assert cenario["mapa_cartao"].ultimo_sync_em is None
        assert cenario["mapa_corrente"].ultimo_sync_em is not None

    def test_mapeamento_desativado_nao_e_lido(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        cenario["mapa_cartao"].deleted_em = datetime(2025, 5, 1, tzinfo=UTC)
        session.commit()
        leitor = LeitorFalso()
        resultado = _sync(session, leitor)
        assert [c.mapeamento_id for c in resultado.contas] == [cenario["mapa_corrente"].id]
        assert all(conta != CARTAO for conta, *_ in leitor.pedidos)


class TestSimulacao:
    def test_simulacao_nao_grava_nada(self, session: Session, cenario: dict[str, Any]) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10")]
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "120.00")]
        leitor.transacoes[CARTAO] = [_tx("k1", CARTAO, "2025-03-20T15:00:00Z", "100", fatura="f1")]
        auditoria_antes = session.scalar(select(func.count()).select_from(Auditoria))

        resultado = _sync(session, leitor, simular=True)

        assert resultado.simulado and resultado.importacao_id is None
        assert resultado.itens_novos == 3  # c1, k1 e o encargo de 20,00
        assert session.scalar(select(func.count()).select_from(Importacao)) == 0
        assert _itens(session) == []
        assert session.scalar(select(func.count()).select_from(Auditoria)) == auditoria_antes
        session.refresh(cenario["mapa_corrente"])
        assert cenario["mapa_corrente"].ultimo_sync_em is None

        amostra = _conta(resultado, cenario["mapa_cartao"]).amostra
        assert {a["id_externo"] for a in amostra} == {"k1", "bill:f1:encargos"}
        compra = next(a for a in amostra if a["id_externo"] == "k1")
        assert compra["forma_pagamento_id"] == cenario["credito"].id
        assert compra["confianca_conversao"] == Decimal("1.00")


class TestFormaPelaOperacao:
    """D-21: na conta corrente, a forma sai do `operationType`, na própria conta."""

    def _uma(self, session: Session, operacao: str | None, id_: str = "c1") -> ImportacaoItem:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx(id_, CORRENTE, "2025-04-02T15:00:00Z", "-45.10", operacao=operacao)
        ]
        _sync(session, leitor)
        return next(i for i in _itens(session) if i.id_externo == id_)

    def test_pix_fica_na_forma_pix_do_mapeamento(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        item = self._uma(session, "PIX")
        assert item.forma_pagamento_sugerida_id == cenario["pix"].id
        assert item.observacao is None

    def test_debito_cria_a_forma_na_conta_certa_uma_vez_so(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10", operacao="CARTAO"),
            _tx("c2", CORRENTE, "2025-04-03T15:00:00Z", "-12.00", operacao="CARTAO"),
        ]
        resultado = _sync(session, leitor)

        debitos = list(
            session.scalars(
                select(FormaPagamento).where(FormaPagamento.tipo == TipoPagamento.DEBITO)
            )
        )
        assert len(debitos) == 1
        debito = debitos[0]
        assert debito.conta_id == cenario["mapa_corrente"].conta_id
        assert debito.titular_id == cenario["titular"].id
        assert debito.apelido == "Débito Banco A"
        assert {i.forma_pagamento_sugerida_id for i in _itens(session)} == {debito.id}
        assert [f.apelido for f in resultado.formas_novas] == ["Débito Banco A"]
        autores = set(
            session.scalars(
                select(Auditoria.autor).where(
                    Auditoria.tabela == "formas_pagamento", Auditoria.registro_id == debito.id
                )
            )
        )
        assert autores == {"sync_pluggy"}

    def test_forma_existente_do_tipo_na_conta_e_usada_pelo_menor_id(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        conta_id = cenario["mapa_corrente"].conta_id
        primeira = FormaPagamento(apelido="Boleto A", tipo=TipoPagamento.BOLETO, conta_id=conta_id)
        session.add(primeira)
        session.flush()
        session.add(
            FormaPagamento(apelido="Boleto B", tipo=TipoPagamento.BOLETO, conta_id=conta_id)
        )
        session.commit()

        item = self._uma(session, "BOLETO")
        assert item.forma_pagamento_sugerida_id == primeira.id

    def test_forma_de_outra_conta_nao_serve(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        outra = Conta(nome="Banco B", tipo=TipoConta.CORRENTE)
        session.add(outra)
        session.flush()
        alheia = FormaPagamento(apelido="Débito B", tipo=TipoPagamento.DEBITO, conta_id=outra.id)
        session.add(alheia)
        session.commit()

        item = self._uma(session, "CARTAO")
        assert item.forma_pagamento_sugerida_id != alheia.id
        forma = session.get(FormaPagamento, item.forma_pagamento_sugerida_id)
        assert forma is not None and forma.conta_id == cenario["mapa_corrente"].conta_id

    def test_forma_inativa_nao_e_recriada(self, session: Session, cenario: dict[str, Any]) -> None:
        session.add(
            FormaPagamento(
                apelido="Débito desligado",
                tipo=TipoPagamento.DEBITO,
                conta_id=cenario["mapa_corrente"].conta_id,
                ativo=False,
            )
        )
        session.commit()

        item = self._uma(session, "CARTAO")
        assert item.forma_pagamento_sugerida_id == cenario["pix"].id
        assert item.observacao is not None and "inativa" in item.observacao
        debitos = session.scalar(
            select(func.count())
            .select_from(FormaPagamento)
            .where(FormaPagamento.tipo == TipoPagamento.DEBITO)
        )
        assert debitos == 1

    def test_operacao_sem_forma_usa_a_do_mapeamento_com_observacao(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        item = self._uma(session, "OUTROS")
        assert item.forma_pagamento_sugerida_id == cenario["pix"].id
        assert item.observacao is not None and "forma de pagamento" in item.observacao

    def test_cartao_fica_com_a_forma_do_mapeamento(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "87.90")]
        leitor.transacoes[CARTAO] = [
            _tx("k1", CARTAO, "2025-03-20T15:00:00Z", "87.90", fatura="f1", operacao="PIX")
        ]
        _sync(session, leitor)
        (item,) = _itens(session)
        assert item.forma_pagamento_sugerida_id == cenario["credito"].id

    def test_simulacao_mostra_a_forma_nova_sem_criar(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10", operacao="CARTAO")
        ]
        antes = session.scalar(select(func.count()).select_from(FormaPagamento))

        resultado = _sync(session, leitor, simular=True)

        assert session.scalar(select(func.count()).select_from(FormaPagamento)) == antes
        assert [f.apelido for f in resultado.formas_novas] == ["Débito Banco A"]
        (amostra,) = _conta(resultado, cenario["mapa_corrente"]).amostra
        assert amostra["forma_pagamento_id"] is None
        assert amostra["forma_nova"] == "Débito Banco A"

    def test_duplicata_no_staging_vale_entre_formas_da_mesma_conta(
        self, session: Session, cenario: dict[str, Any]
    ) -> None:
        """Gêmeo com forma diferente (Pix x débito) ainda é da mesma conta."""
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("c1", CORRENTE, "2025-05-15T15:00:00Z", "-45.10", operacao="PIX")
        ]
        _sync(session, leitor)
        leitor.transacoes[CORRENTE] = [
            _tx("c2", CORRENTE, "2025-05-15T18:00:00Z", "-45.10", operacao="CARTAO")
        ]
        _sync(session, leitor)

        c2 = next(i for i in _itens(session) if i.id_externo == "c2")
        assert c2.observacao is not None and "Possível duplicata" in c2.observacao


# --------------------------------------------------------------------------
# Promoção automática do item limpo (D-21)
# --------------------------------------------------------------------------


@pytest.fixture
def mercado(session: Session) -> Categoria:
    """Categoria "Mercado" com o mapeamento de "Groceries" da Pluggy."""
    from app.models import CategoriaPluggy

    categoria = Categoria(nome="Mercado", tipo=TipoTransacao.DESPESA)
    session.add(categoria)
    session.flush()
    session.add(
        CategoriaPluggy(
            pluggy_categoria_id="11000000",
            pluggy_categoria_nome="Groceries",
            categoria_id=categoria.id,
        )
    )
    session.commit()
    return categoria


def _compra(id_: str, quando: str = "2025-03-20T15:00:00Z", valor: str = "87.90") -> Transacao:
    return _tx(
        id_, CARTAO, quando, valor, fatura="f1", categoria="Groceries", categoria_id="11000000"
    )


def _pix(id_: str, quando: str = "2025-04-02T15:00:00Z", valor: str = "-45.10") -> Transacao:
    return _tx(
        id_,
        CORRENTE,
        quando,
        valor,
        operacao="PIX",
        categoria="Groceries",
        categoria_id="11000000",
    )


def _transacoes_vivas(session: Session) -> list[Any]:
    from app.models import Transacao as TransacaoLocal

    return list(
        session.scalars(
            select(TransacaoLocal)
            .where(TransacaoLocal.deleted_em.is_(None))
            .order_by(TransacaoLocal.id)
        )
    )


class TestPromocaoAutomatica:
    def test_compra_de_cartao_limpa_vira_transacao(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "87.90")]
        leitor.transacoes[CARTAO] = [_compra("k1")]

        resultado = _sync(session, leitor)

        assert resultado.promovidos == 1
        (transacao,) = _transacoes_vivas(session)
        (item,) = _itens(session)
        assert item.status is StatusItem.APROVADO
        assert item.transacao_id == transacao.id
        assert transacao.importacao_id == resultado.importacao_id
        assert transacao.categoria_id == mercado.id
        assert transacao.forma_pagamento_id == cenario["credito"].id
        assert transacao.competencia == date(2025, 4, 1)
        autores = set(
            session.scalars(
                select(Auditoria.autor).where(
                    Auditoria.tabela == "transacoes", Auditoria.registro_id == transacao.id
                )
            )
        )
        assert autores == {"sync_pluggy"}
        imp = session.get(Importacao, resultado.importacao_id)
        assert imp is not None and imp.status is StatusImportacao.CONCLUIDA
        assert imp.itens_aprovados == 1

    def test_pix_limpo_da_conta_tambem_promove(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_pix("c1")]
        resultado = _sync(session, leitor)

        assert resultado.promovidos == 1
        (transacao,) = _transacoes_vivas(session)
        assert transacao.forma_pagamento_id == cenario["pix"].id
        assert transacao.pessoa_id == cenario["titular"].id

    def test_o_resto_fica_na_revisao_com_o_motivo(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        leitor = LeitorFalso()
        leitor.faturas[CARTAO] = [_fatura("f1", "2025-04-03", "2025-04-10", "200.00")]
        leitor.transacoes[CARTAO] = [
            _compra("limpa", valor="50.00"),
            _tx("sem-cat", CARTAO, "2025-03-21T15:00:00Z", "40.00", fatura="f1"),
            # Gêmeos da própria Pluggy: mesma data, valor e descrição.
            _compra("gemeo-a", "2025-03-22T15:00:00Z", "30.00"),
            _compra("gemeo-b", "2025-03-22T18:00:00Z", "30.00"),
            # Pagamento da fatura do lado do cartão.
            _tx(
                "pag",
                CARTAO,
                "2025-04-08T15:00:00Z",
                "-150.00",
                tipo="CREDIT",
                operacao="PAGAMENTO_FATURA",
                categoria="Credit card payment",
            ),
        ]
        leitor.transacoes[CORRENTE] = [
            _tx("outros", CORRENTE, "2025-04-02T15:00:00Z", "-10.00", operacao="OUTROS")
        ]

        resultado = _sync(session, leitor)

        assert resultado.promovidos == 1
        assert resultado.na_revisao == {
            "sem_categoria": 1,
            "possivel_duplicata": 2,
            "pagamento_fatura_cartao": 1,
            "encargos": 1,  # 200 - (50 + 40 + 30 + 30)
            "observacao": 1,
        }
        pendentes = {i.id_externo for i in _itens(session) if i.status is StatusItem.PENDENTE}
        assert pendentes == {"sem-cat", "gemeo-a", "gemeo-b", "pag", "bill:f1:encargos", "outros"}
        imp = session.get(Importacao, resultado.importacao_id)
        assert imp is not None and imp.status is StatusImportacao.AGUARDANDO_REVISAO

    def test_hash_dedup_continua_barrando(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        """Transação idêntica já em `transacoes`: o item fica `duplicado`."""
        from app.models import Transacao as TransacaoLocal

        session.add(
            TransacaoLocal(
                data=date(2025, 4, 2),
                competencia=date(2025, 4, 1),
                valor=Decimal("45.10"),
                tipo=TipoTransacao.DESPESA,
                descricao="manual",
                descricao_original="MERCADO EXEMPLO",
                forma_pagamento_id=cenario["pix"].id,
            )
        )
        session.commit()
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [_pix("c1")]

        resultado = _sync(session, leitor)

        assert resultado.promovidos == 0
        assert resultado.na_revisao == {"duplicata": 1}
        assert len(_transacoes_vivas(session)) == 1
        (item,) = _itens(session)
        assert item.status is StatusItem.DUPLICADO

    def test_regra_do_usuario_tambem_da_categoria_para_promover(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        session.add(
            RegraCategorizacao(
                padrao="MERCADO EXEMPLO", tipo_match="contem", categoria_id=mercado.id
            )
        )
        session.commit()
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _tx("c1", CORRENTE, "2025-04-02T15:00:00Z", "-45.10", operacao="PIX")
        ]
        assert _sync(session, leitor).promovidos == 1

    def test_simulacao_conta_sem_promover(
        self, session: Session, cenario: dict[str, Any], mercado: Categoria
    ) -> None:
        leitor = LeitorFalso()
        leitor.transacoes[CORRENTE] = [
            _pix("c1"),
            _tx("c2", CORRENTE, "2025-04-03T15:00:00Z", "-10.00", operacao="PIX"),
        ]
        resultado = _sync(session, leitor, simular=True)

        assert resultado.promovidos == 1
        assert resultado.na_revisao == {"sem_categoria": 1}
        assert _transacoes_vivas(session) == []
        amostra = _conta(resultado, cenario["mapa_corrente"]).amostra
        assert {a["id_externo"]: a["destino"] for a in amostra} == {
            "c1": "promover",
            "c2": "sem_categoria",
        }
