"""Mapeamento de contas da Pluggy (fase 5b, passo 4).

O encaixe espelha o PDF: cartão não é `conta` própria, é uma forma `credito`
da conta corrente que paga a fatura. Por isso a regra central é uma só — a
forma tem que ser da conta mapeada —, testada aqui para cartão e para conta.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao, StatusItem, TipoConta, TipoPagamento, TipoTransacao
from app.models import Auditoria, Conta, ContaPluggy, FormaPagamento, Importacao, ImportacaoItem
from app.pluggy import Conta as ContaRemota
from app.services.base import Conflito, NaoEncontrado, RegraViolada
from app.services.ingestao import IngestaoService
from app.services.pluggy_mapeamento import ContaPluggyService
from scripts.pluggy_mapear import nao_mapeadas


def _conta(session: Session, nome: str, tipo: TipoConta = TipoConta.CORRENTE) -> Conta:
    conta = Conta(nome=nome, tipo=tipo)
    session.add(conta)
    session.flush()
    return conta


def _forma(
    session: Session, apelido: str, tipo: TipoPagamento, conta: Conta | None, ativo: bool = True
) -> FormaPagamento:
    forma = FormaPagamento(
        apelido=apelido, tipo=tipo, conta_id=conta.id if conta else None, ativo=ativo
    )
    session.add(forma)
    session.flush()
    return forma


@pytest.fixture
def cadastro(session: Session) -> dict[str, Any]:
    """Duas contas correntes, cada uma com seu cartão e seu Pix."""
    banco_a = _conta(session, "Banco A")
    banco_b = _conta(session, "Banco B")
    cadastro = {
        "banco_a": banco_a,
        "banco_b": banco_b,
        "credito_a": _forma(session, "Crédito Banco A •••• 0001", TipoPagamento.CREDITO, banco_a),
        "pix_a": _forma(session, "Pix Banco A", TipoPagamento.PIX, banco_a),
        "credito_b": _forma(session, "Crédito Banco B •••• 0002", TipoPagamento.CREDITO, banco_b),
    }
    session.commit()
    return cadastro


def _dados(cad: dict[str, Any], **extra: Any) -> dict[str, Any]:
    dados = {
        "pluggy_item_id": "item-a",
        "pluggy_account_id": "conta-cartao-a",
        "conta_id": cad["banco_a"].id,
        "forma_pagamento_id": cad["credito_a"].id,
        "sincronizar_desde": date(2026, 9, 1),
    }
    return dados | extra


def _transacao_de_pdf(
    session: Session, forma: FormaPagamento, data: date, origem: str = "nubank_fatura"
) -> None:
    """Uma transação promovida pelo caminho de verdade: importação -> item -> aprovar."""
    imp = Importacao(
        arquivo_nome=f"{origem}_{data}.pdf",
        hash_arquivo=f"hash-{origem}-{data}-{forma.id}",
        arquivo_tipo="application/json" if origem == "pluggy" else "application/pdf",
        origem=origem,
        status=StatusImportacao.AGUARDANDO_REVISAO,
        total_itens=1,
    )
    session.add(imp)
    session.flush()
    item = ImportacaoItem(
        importacao_id=imp.id,
        linha_bruta=f"COMPRA {data}",
        linha_num=1,
        data=data,
        valor=Decimal("10.00"),
        descricao_original=f"COMPRA {data}",
        tipo_sugerido=TipoTransacao.DESPESA,
        forma_pagamento_sugerida_id=forma.id,
        status=StatusItem.PENDENTE,
    )
    session.add(item)
    session.flush()
    resultado = IngestaoService(session).aprovar([item.id])
    assert resultado["promovidos"] == 1
    session.commit()


class TestCriar:
    def test_cartao_aponta_para_a_corrente_que_paga_a_fatura(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        obj = ContaPluggyService(session).criar(_dados(cadastro))
        session.commit()
        assert obj.conta_id == cadastro["banco_a"].id
        assert obj.forma_pagamento_id == cadastro["credito_a"].id
        assert obj.ativo is True

    def test_conta_corrente_com_forma_pix(self, session: Session, cadastro: dict[str, Any]) -> None:
        obj = ContaPluggyService(session).criar(
            _dados(
                cadastro,
                pluggy_account_id="conta-corrente-a",
                forma_pagamento_id=cadastro["pix_a"].id,
            )
        )
        assert obj.forma_pagamento_id == cadastro["pix_a"].id

    def test_forma_de_outra_conta_e_recusada(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        """O cartão do banco B não pode ser a forma padrão da conta do banco A."""
        with pytest.raises(RegraViolada, match="pertence à conta"):
            ContaPluggyService(session).criar(
                _dados(cadastro, forma_pagamento_id=cadastro["credito_b"].id)
            )

    def test_forma_sem_conta_e_recusada(self, session: Session, cadastro: dict[str, Any]) -> None:
        solta = _forma(session, "Dinheiro", TipoPagamento.DINHEIRO, None)
        with pytest.raises(RegraViolada, match="pertence à conta"):
            ContaPluggyService(session).criar(_dados(cadastro, forma_pagamento_id=solta.id))

    def test_forma_inativa_e_recusada(self, session: Session, cadastro: dict[str, Any]) -> None:
        inativa = _forma(
            session, "Crédito antigo", TipoPagamento.CREDITO, cadastro["banco_a"], ativo=False
        )
        with pytest.raises(RegraViolada, match="inativa"):
            ContaPluggyService(session).criar(_dados(cadastro, forma_pagamento_id=inativa.id))

    def test_conta_inexistente_e_recusada(self, session: Session, cadastro: dict[str, Any]) -> None:
        with pytest.raises(RegraViolada, match="não existe"):
            ContaPluggyService(session).criar(_dados(cadastro, conta_id=9999))

    def test_mesma_conta_pluggy_duas_vezes_e_conflito(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        service = ContaPluggyService(session)
        service.criar(_dados(cadastro))
        session.commit()
        with pytest.raises(Conflito, match="já está mapeada"):
            service.criar(_dados(cadastro))

    def test_grava_auditoria(self, session: Session, cadastro: dict[str, Any]) -> None:
        obj = ContaPluggyService(session).criar(_dados(cadastro))
        session.commit()
        acoes = session.scalars(
            select(Auditoria.acao).where(
                Auditoria.tabela == "contas_pluggy", Auditoria.registro_id == obj.id
            )
        ).all()
        assert acoes == ["INSERT"]


class TestEditarEDesativar:
    def test_trocar_forma_revalida_contra_a_conta(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        session.commit()
        with pytest.raises(RegraViolada, match="pertence à conta"):
            service.atualizar(obj.id, {"forma_pagamento_id": cadastro["credito_b"].id})

    def test_trocar_conta_e_forma_juntas(self, session: Session, cadastro: dict[str, Any]) -> None:
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        session.commit()
        service.atualizar(
            obj.id,
            {
                "conta_id": cadastro["banco_b"].id,
                "forma_pagamento_id": cadastro["credito_b"].id,
            },
        )
        session.commit()
        assert service.get(obj.id).conta_id == cadastro["banco_b"].id

    def test_campo_obrigatorio_nao_pode_ser_zerado(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        session.commit()
        with pytest.raises(RegraViolada, match="obrigatório"):
            service.atualizar(obj.id, {"sincronizar_desde": None})

    def test_desativar_e_soft_delete_e_libera_a_conta_pluggy(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        session.commit()
        service.remover(obj.id)
        session.commit()

        linha = session.get(ContaPluggy, obj.id)
        assert linha is not None, "soft delete não apaga a linha"
        assert linha.deleted_em is not None
        assert linha.ativo is False
        with pytest.raises(NaoEncontrado):
            service.get(obj.id)

        # O índice único é parcial: desativado, o mesmo id da Pluggy pode ser
        # mapeado de novo.
        novo = service.criar(_dados(cadastro))
        session.commit()
        assert novo.id != obj.id

    def test_listar_ignora_desativados(self, session: Session, cadastro: dict[str, Any]) -> None:
        from app.schemas.common import Paginacao

        service = ContaPluggyService(session)
        a = service.criar(_dados(cadastro))
        service.criar(_dados(cadastro, pluggy_account_id="outra"))
        session.commit()
        service.remover(a.id)
        session.commit()
        itens, total = service.listar(Paginacao())
        assert total == 1
        assert [i.pluggy_account_id for i in itens] == ["outra"]


class TestAvisoDeOrigem:
    def test_pdf_depois_de_sincronizar_desde_gera_aviso(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        _transacao_de_pdf(session, cadastro["credito_a"], date(2026, 9, 15))
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro, sincronizar_desde=date(2026, 9, 1)))

        avisos = service.avisos(obj)
        assert len(avisos) == 1
        assert "1 transação(ões)" in avisos[0]
        assert "15/09/2026" in avisos[0]

    def test_pdf_antes_de_sincronizar_desde_nao_avisa(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        _transacao_de_pdf(session, cadastro["credito_a"], date(2026, 8, 20))
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro, sincronizar_desde=date(2026, 9, 1)))
        assert service.avisos(obj) == []

    def test_pdf_de_outra_conta_nao_avisa(self, session: Session, cadastro: dict[str, Any]) -> None:
        _transacao_de_pdf(session, cadastro["credito_b"], date(2026, 9, 15))
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        assert service.avisos(obj) == []

    def test_transacao_da_propria_pluggy_nao_avisa(
        self, session: Session, cadastro: dict[str, Any]
    ) -> None:
        _transacao_de_pdf(session, cadastro["credito_a"], date(2026, 9, 15), origem="pluggy")
        service = ContaPluggyService(session)
        obj = service.criar(_dados(cadastro))
        assert service.avisos(obj) == []

    def test_aviso_nao_bloqueia(self, session: Session, cadastro: dict[str, Any]) -> None:
        _transacao_de_pdf(session, cadastro["credito_a"], date(2026, 9, 15))
        ContaPluggyService(session).criar(_dados(cadastro))
        session.commit()
        assert session.scalar(select(ContaPluggy.id)) is not None


class TestApi:
    def test_crud_completo(self, client: TestClient, cadastro: dict[str, Any]) -> None:
        corpo = _dados(cadastro, sincronizar_desde="2026-09-01")
        criado = client.post("/contas-pluggy", json=corpo)
        assert criado.status_code == 201, criado.text
        id_ = criado.json()["id"]
        assert criado.json()["avisos"] == []

        assert client.get(f"/contas-pluggy/{id_}").json()["pluggy_account_id"] == "conta-cartao-a"
        assert client.get("/contas-pluggy").json()["total"] == 1

        editado = client.patch(f"/contas-pluggy/{id_}", json={"sincronizar_desde": "2026-10-01"})
        assert editado.status_code == 200
        assert editado.json()["sincronizar_desde"] == "2026-10-01"

        assert client.delete(f"/contas-pluggy/{id_}").json() == {"ok": True}
        assert client.get(f"/contas-pluggy/{id_}").status_code == 404
        assert client.get("/contas-pluggy").json()["total"] == 0

    def test_post_devolve_aviso_de_pdf(
        self, client: TestClient, session: Session, cadastro: dict[str, Any]
    ) -> None:
        _transacao_de_pdf(session, cadastro["credito_a"], date(2026, 9, 15))
        resposta = client.post(
            "/contas-pluggy", json=_dados(cadastro, sincronizar_desde="2026-09-01")
        )
        assert resposta.status_code == 201
        assert len(resposta.json()["avisos"]) == 1

    def test_forma_errada_e_422(self, client: TestClient, cadastro: dict[str, Any]) -> None:
        corpo = _dados(
            cadastro,
            sincronizar_desde="2026-09-01",
            forma_pagamento_id=cadastro["credito_b"].id,
        )
        resposta = client.post("/contas-pluggy", json=corpo)
        assert resposta.status_code == 422
        assert "pertence à conta" in resposta.json()["detail"]

    def test_duplicado_e_409(self, client: TestClient, cadastro: dict[str, Any]) -> None:
        corpo = _dados(cadastro, sincronizar_desde="2026-09-01")
        assert client.post("/contas-pluggy", json=corpo).status_code == 201
        assert client.post("/contas-pluggy", json=corpo).status_code == 409

    def test_id_da_pluggy_nao_e_editavel(
        self, client: TestClient, cadastro: dict[str, Any]
    ) -> None:
        id_ = client.post(
            "/contas-pluggy", json=_dados(cadastro, sincronizar_desde="2026-09-01")
        ).json()["id"]
        client.patch(f"/contas-pluggy/{id_}", json={"pluggy_account_id": "trocado"})
        assert client.get(f"/contas-pluggy/{id_}").json()["pluggy_account_id"] == "conta-cartao-a"


class _LeitorFalso:
    def __init__(self, contas: dict[str, list[ContaRemota]]) -> None:
        self.contas = contas

    def listar_contas(self, item_id: str, tipo: str | None = None) -> list[ContaRemota]:
        return self.contas[item_id]

    def listar_items(self) -> list[Any]:
        raise AssertionError("não deveria listar items quando os ids foram dados")


def _remota(id_: str, tipo: str, subtipo: str) -> ContaRemota:
    return ContaRemota.model_validate(
        {"id": id_, "itemId": "item-a", "type": tipo, "subtype": subtipo, "name": "Banco"}
    )


def test_script_lista_so_as_nao_mapeadas(session: Session, cadastro: dict[str, Any]) -> None:
    ContaPluggyService(session).criar(_dados(cadastro, pluggy_account_id="ja-mapeada"))
    session.commit()
    leitor = _LeitorFalso(
        {
            "item-a": [
                _remota("ja-mapeada", "CREDIT", "CREDIT_CARD"),
                _remota("nova-corrente", "BANK", "CHECKING_ACCOUNT"),
            ],
            "item-b": [_remota("novo-cartao", "CREDIT", "CREDIT_CARD")],
        }
    )
    pendentes = nao_mapeadas(leitor, ["item-a", "item-b"], session)
    assert [(p.item_id, p.conta.id) for p in pendentes] == [
        ("item-a", "nova-corrente"),
        ("item-b", "novo-cartao"),
    ]


def test_script_volta_a_listar_conta_desativada(session: Session, cadastro: dict[str, Any]) -> None:
    service = ContaPluggyService(session)
    obj = service.criar(_dados(cadastro, pluggy_account_id="desativada"))
    session.commit()
    service.remover(obj.id)
    session.commit()
    leitor = _LeitorFalso({"item-a": [_remota("desativada", "CREDIT", "CREDIT_CARD")]})
    assert [p.conta.id for p in nao_mapeadas(leitor, ["item-a"], session)] == ["desativada"]


def test_item_da_pluggy_leva_id_externo_e_competencia_para_o_staging(
    session: Session, cadastro: dict[str, Any]
) -> None:
    """Os dois campos novos do `ItemExtraido` chegam a `importacao_itens`.

    A competência do item vence a do documento: na Pluggy cada compra aponta
    para a sua fatura. O PDF segue com `id_externo` nulo.
    """
    from app.ingestao.base import ItemExtraido
    from app.services.ingestao import _ContextoEnriquecimento

    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="hash-pluggy",
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.flush()
    contexto = _ContextoEnriquecimento.carregar(session)
    service = IngestaoService(session)

    def extraido(**kwargs: Any) -> ItemExtraido:
        return ItemExtraido(
            linha_bruta="PADARIA EXEMPLO",
            linha_num=1,
            data=date(2025, 3, 20),
            valor=Decimal("87.90"),
            descricao="PADARIA EXEMPLO",
            **kwargs,
        )

    da_pluggy = service._item(
        imp, extraido(id_externo="tx-1", competencia=date(2025, 4, 1)), date(2025, 3, 1), contexto
    )
    do_pdf = service._item(imp, extraido(), date(2025, 3, 1), contexto)

    assert (da_pluggy.id_externo, da_pluggy.competencia_sugerida) == ("tx-1", date(2025, 4, 1))
    assert (do_pdf.id_externo, do_pdf.competencia_sugerida) == (None, date(2025, 3, 1))
