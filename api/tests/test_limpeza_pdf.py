"""Limpeza dos dados de PDF dentro da janela da Pluggy (fase 5b, passo 7)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import (
    Auditoria,
    Conta,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Transacao,
)
from app.services.base import RegraViolada
from app.services.ingestao import IngestaoService
from app.services.limpeza_pdf import LimpezaPdfService

CORTE = date(2025, 10, 11)


@pytest.fixture
def cenario(session: Session) -> dict[str, Any]:
    antiga = Conta(nome="Conta Corrente", tipo=TipoConta.CORRENTE)
    banco = Conta(nome="Banco B", tipo=TipoConta.CORRENTE)
    session.add_all([antiga, banco])
    session.flush()
    forma_seed = FormaPagamento(
        apelido="Cartão de crédito - seed", tipo=TipoPagamento.CREDITO, conta_id=antiga.id
    )
    forma_nova = FormaPagamento(
        apelido="Crédito Banco B •••• 2222", tipo=TipoPagamento.CREDITO, conta_id=banco.id
    )
    session.add_all([forma_seed, forma_nova])
    session.flush()
    mapa = ContaPluggy(
        pluggy_item_id="item",
        pluggy_account_id="cartao",
        conta_id=banco.id,
        forma_pagamento_id=forma_nova.id,
        sincronizar_desde=CORTE,
    )
    session.add(mapa)
    session.commit()
    return {"forma_seed": forma_seed, "mapa": mapa}


def _importacao(session: Session, origem: str, nome: str) -> Importacao:
    imp = Importacao(
        arquivo_nome=nome,
        hash_arquivo=f"hash-{nome}",
        arquivo_tipo="application/pdf",
        arquivo_conteudo=b"%PDF-1.4 teste",
        origem=origem,
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()
    return imp


def _item(
    session: Session, imp: Importacao, data: date, forma: FormaPagamento, valor: str = "10.00"
) -> ImportacaoItem:
    item = ImportacaoItem(
        importacao_id=imp.id,
        linha_bruta=f"COMPRA {data} {valor}",
        data=data,
        valor=Decimal(valor),
        descricao_original=f"COMPRA {data} {valor}",
        tipo_sugerido=TipoTransacao.DESPESA,
        forma_pagamento_sugerida_id=forma.id,
        status=StatusItem.PENDENTE,
    )
    session.add(item)
    session.flush()
    return item


def _aprovado(session: Session, imp: Importacao, data: date, forma: FormaPagamento) -> None:
    item = _item(session, imp, data, forma, "50.00")
    assert IngestaoService(session).aprovar([item.id])["promovidos"] == 1


def _vivos(session: Session, modelo: Any) -> int:
    return len(list(session.scalars(select(modelo).where(modelo.deleted_em.is_(None)))))


@pytest.fixture
def dados_pdf(session: Session, cenario: dict[str, Any]) -> dict[str, Importacao]:
    forma = cenario["forma_seed"]
    dentro = _importacao(session, "nubank_fatura", "dentro.pdf")
    _item(session, dentro, date(2026, 5, 14), forma)
    _item(session, dentro, date(2026, 5, 20), forma)
    _aprovado(session, dentro, date(2026, 6, 4), forma)

    # Atravessa o corte: o que é anterior fica, e a importação não é cancelada.
    dividida = _importacao(session, "nubank_fatura", "dividida.pdf")
    _item(session, dividida, date(2025, 10, 5), forma)
    _aprovado(session, dividida, date(2025, 10, 1), forma)
    _item(session, dividida, date(2025, 10, 12), forma)

    sem_mapa = _importacao(session, "outro_banco_fatura", "outro.pdf")
    _item(session, sem_mapa, date(2026, 5, 14), forma)
    session.commit()
    return {"dentro": dentro, "dividida": dividida, "sem_mapa": sem_mapa}


def test_simulacao_conta_e_nao_grava(
    session: Session, cenario: dict[str, Any], dados_pdf: dict[str, Importacao]
) -> None:
    itens_antes, tx_antes = _vivos(session, ImportacaoItem), _vivos(session, Transacao)

    r = LimpezaPdfService(session).limpar({"nubank_fatura": cenario["mapa"].id}, simular=True)
    session.commit()

    (origem,) = r.origens
    assert (origem.transacoes, origem.itens) == (1, 4)
    assert origem.itens_por_status == {"pendente": 3, "aprovado": 1}
    assert (origem.transacoes_preservadas, origem.itens_preservados) == (1, 2)
    assert origem.importacoes_canceladas == [dados_pdf["dentro"].id]
    assert r.nao_tocadas == ["outro_banco_fatura"]
    assert (_vivos(session, ImportacaoItem), _vivos(session, Transacao)) == (itens_antes, tx_antes)


def test_execucao_faz_soft_delete_com_auditoria(
    session: Session, cenario: dict[str, Any], dados_pdf: dict[str, Importacao]
) -> None:
    r = LimpezaPdfService(session).limpar({"nubank_fatura": cenario["mapa"].id}, simular=False)
    session.commit()
    assert (r.transacoes, r.itens) == (1, 4)

    # Nada sumiu de verdade: as linhas estão lá, com `deleted_em`.
    apagados = list(
        session.scalars(select(ImportacaoItem).where(ImportacaoItem.deleted_em.is_not(None)))
    )
    assert len(apagados) == 4
    assert all(i.data >= CORTE for i in apagados)
    preservados = list(
        session.scalars(
            select(ImportacaoItem).where(
                ImportacaoItem.deleted_em.is_(None),
                ImportacaoItem.importacao_id == dados_pdf["dividida"].id,
            )
        )
    )
    assert sorted(i.data for i in preservados) == [date(2025, 10, 1), date(2025, 10, 5)]
    assert _vivos(session, Transacao) == 1  # a de 01/10/2025, antes do corte

    session.refresh(dados_pdf["dentro"])
    session.refresh(dados_pdf["dividida"])
    assert dados_pdf["dentro"].status is StatusImportacao.CANCELADA
    assert dados_pdf["dentro"].deleted_em is None, "a importação fica, com o PDF"
    assert dados_pdf["dividida"].status is StatusImportacao.AGUARDANDO_REVISAO

    autores = set(
        session.scalars(
            select(Auditoria.autor).where(
                Auditoria.tabela.in_(["importacao_itens", "transacoes"]),
                Auditoria.acao == "UPDATE",
                # Só o soft delete: a aprovação do preparo também é UPDATE.
                Auditoria.dados_depois["deleted_em"].astext.is_not(None),
            )
        )
    )
    assert autores == {"limpeza_pdf"}


def test_origem_sem_correspondencia_e_pluggy_nao_sao_tocadas(
    session: Session, cenario: dict[str, Any], dados_pdf: dict[str, Importacao]
) -> None:
    pluggy = _importacao(session, "pluggy", "sync.json")
    _item(session, pluggy, date(2026, 5, 14), cenario["forma_seed"])
    session.commit()

    LimpezaPdfService(session).limpar({"nubank_fatura": cenario["mapa"].id}, simular=False)
    session.commit()

    for imp in (dados_pdf["sem_mapa"], pluggy):
        vivos = list(
            session.scalars(
                select(ImportacaoItem).where(
                    ImportacaoItem.importacao_id == imp.id, ImportacaoItem.deleted_em.is_(None)
                )
            )
        )
        assert len(vivos) == 1


def test_rodar_de_novo_nao_muda_nada(
    session: Session, cenario: dict[str, Any], dados_pdf: dict[str, Importacao]
) -> None:
    servico = LimpezaPdfService(session)
    servico.limpar({"nubank_fatura": cenario["mapa"].id}, simular=False)
    session.commit()
    segunda = servico.limpar({"nubank_fatura": cenario["mapa"].id}, simular=False)
    session.commit()
    assert (segunda.transacoes, segunda.itens) == (0, 0)
    assert segunda.origens[0].importacoes_canceladas == []


def test_recusa_pluggy_e_mapeamento_desativado(session: Session, cenario: dict[str, Any]) -> None:
    servico = LimpezaPdfService(session)
    with pytest.raises(RegraViolada, match="pluggy"):
        servico.limpar({"pluggy": cenario["mapa"].id})
    cenario["mapa"].deleted_em = datetime(2026, 1, 1, tzinfo=UTC)
    session.commit()
    with pytest.raises(RegraViolada, match="desativado"):
        servico.limpar({"nubank_fatura": cenario["mapa"].id})
    with pytest.raises(RegraViolada, match="não existe"):
        servico.limpar({"nubank_fatura": 9999})
