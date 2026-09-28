"""Fluxo de ingestão de ponta a ponta, com os PDFs reais.

O que estes testes garantem, e que é o coração da D-07: o arquivo entra em
staging, e **nada chega em `transacoes` sem aprovação**.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

FATURAS = Path(__file__).resolve().parents[2] / "faturas"
faturas = sorted(FATURAS.glob("Nubank_*.pdf")) if FATURAS.exists() else []
extratos = sorted(FATURAS.glob("NU_*.pdf")) if FATURAS.exists() else []

sem_pdfs = pytest.mark.skipif(
    not faturas, reason="faturas/ vazia — os PDFs reais não são versionados"
)


def _upload(client: TestClient, caminho: Path):
    return client.post(
        "/importacoes",
        files={"arquivo": (caminho.name, caminho.read_bytes(), "application/pdf")},
    )


@sem_pdfs
class TestUpload:
    def test_importa_e_fica_aguardando_revisao(self, client: TestClient, semeado: None) -> None:
        resposta = _upload(client, faturas[0])
        assert resposta.status_code == 201, resposta.text
        dados = resposta.json()
        assert dados["status"] == "aguardando_revisao"
        assert dados["origem"] == "nubank_fatura"
        assert dados["total_itens"] > 0
        # Sem erro: a soma bateu com o total do documento.
        assert dados["erro_mensagem"] is None

    def test_nada_entra_em_transacoes_sem_aprovar(self, client: TestClient, semeado: None) -> None:
        """A regra 5 do CLAUDE.md, verificada."""
        _upload(client, faturas[0])
        assert client.get("/transacoes").json()["total"] == 0

    def test_reimportar_o_mesmo_arquivo_volta_409(self, client: TestClient, semeado: None) -> None:
        _upload(client, faturas[0])
        resposta = _upload(client, faturas[0])
        assert resposta.status_code == 409
        assert "já foi importado" in resposta.json()["detail"]

    def test_arquivo_que_nao_e_pdf_e_recusado(self, client: TestClient, semeado: None) -> None:
        resposta = client.post(
            "/importacoes",
            files={"arquivo": ("nota.txt", b"isto nao e um pdf", "text/plain")},
        )
        assert resposta.status_code == 422

    def test_total_declarado_vira_gabarito_na_tela(self, client: TestClient, semeado: None) -> None:
        dados = _upload(client, faturas[0]).json()
        assert Decimal(dados["total_declarado"]) > 0


@sem_pdfs
class TestRevisao:
    @pytest.fixture
    def importacao(self, client: TestClient, semeado: None) -> dict:
        return _upload(client, faturas[0]).json()

    def test_detalhe_traz_itens_e_total_pendente(
        self, client: TestClient, importacao: dict
    ) -> None:
        dados = client.get(f"/importacoes/{importacao['id']}").json()
        assert len(dados["itens"]) == importacao["total_itens"]
        assert all(item["status"] == "pendente" for item in dados["itens"])
        # O que entra de despesa se aprovar tudo.
        assert Decimal(dados["total_pendente"]) == Decimal(importacao["total_declarado"])

    def test_itens_trazem_a_linha_crua_para_conferencia(
        self, client: TestClient, importacao: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        for item in itens:
            assert item["linha_bruta"].strip()
            assert item["data"] is not None
            assert Decimal(item["valor"]) > 0

    def test_competencia_sugerida_e_o_mes_do_vencimento(
        self, client: TestClient, importacao: dict
    ) -> None:
        """Compra de junho na fatura de julho é despesa de julho (D-02)."""
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        competencias = {item["competencia_sugerida"] for item in itens}
        assert len(competencias) == 1
        assert next(iter(competencias)).endswith("-01")

    def test_ajustar_categoria_cria_regra(
        self, client: TestClient, importacao: dict, session: Session
    ) -> None:
        """Correção do usuário vira regra (D-09)."""
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        arvore = client.get("/categorias/arvore/completa").json()
        mercado = next(
            s["id"]
            for c in arvore
            if c["nome"] == "Alimentação"
            for s in c["subcategorias"]
            if s["nome"] == "Mercado"
        )

        resposta = client.patch(
            f"/importacoes/itens/{itens[0]['id']}",
            json={"categoria_sugerida_id": mercado},
        )
        assert resposta.status_code == 200
        assert resposta.json()["categoria_sugerida_id"] == mercado

        regras = session.execute(
            text("SELECT padrao, categoria_id, criada_por FROM regras_categorizacao")
        ).all()
        assert len(regras) == 1
        assert regras[0].categoria_id == mercado
        assert regras[0].criada_por == "correcao_automatica"

    def test_rejeitar_nao_promove(self, client: TestClient, importacao: dict) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        resposta = client.post(
            "/importacoes/itens/rejeitar",
            json={"ids": [itens[0]["id"]], "motivo": "não reconheço"},
        )
        assert resposta.json()["afetadas"] == 1
        assert client.get("/transacoes").json()["total"] == 0


@sem_pdfs
class TestPromocao:
    @pytest.fixture
    def importacao(self, client: TestClient, semeado: None) -> dict:
        return _upload(client, faturas[0]).json()

    def test_aprovar_cria_transacoes_com_o_total_certo(
        self, client: TestClient, importacao: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        resultado = client.post(
            "/importacoes/itens/aprovar", json={"ids": [i["id"] for i in itens]}
        ).json()

        assert resultado["erros"] == []
        assert resultado["promovidos"] == len(itens)

        listagem = client.get("/transacoes").json()
        assert listagem["total"] == len(itens)
        # O total no painel bate com o total da fatura.
        assert Decimal(listagem["totais"]["total_despesa"]) == Decimal(
            importacao["total_declarado"]
        )

    def test_transacao_guarda_a_linha_crua_e_a_origem(
        self, client: TestClient, importacao: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        client.post("/importacoes/itens/aprovar", json={"ids": [itens[0]["id"]]})

        transacao = client.get("/transacoes").json()["items"][0]
        assert transacao["descricao_original"] == itens[0]["linha_bruta"]
        assert transacao["descricao"] != transacao["descricao_original"]

    def test_item_aprovado_aponta_para_a_transacao(
        self, client: TestClient, importacao: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        client.post("/importacoes/itens/aprovar", json={"ids": [itens[0]["id"]]})

        atualizado = client.get(f"/importacoes/{importacao['id']}").json()["itens"][0]
        assert atualizado["status"] == "aprovado"
        assert atualizado["transacao_id"] is not None

    def test_aprovar_duas_vezes_nao_duplica(self, client: TestClient, importacao: dict) -> None:
        """O `hash_dedup` protege a promoção (D-07)."""
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        ids = [i["id"] for i in itens]
        client.post("/importacoes/itens/aprovar", json={"ids": ids})
        antes = client.get("/transacoes").json()["total"]

        segunda = client.post("/importacoes/itens/aprovar", json={"ids": ids})
        assert segunda.status_code == 422  # itens já aprovados
        assert client.get("/transacoes").json()["total"] == antes

    def test_importacao_conclui_quando_nao_sobra_pendente(
        self, client: TestClient, importacao: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        client.post("/importacoes/itens/aprovar", json={"ids": [i["id"] for i in itens]})

        atual = client.get(f"/importacoes/{importacao['id']}").json()["importacao"]
        assert atual["status"] == "concluida"
        assert atual["itens_aprovados"] == len(itens)


@pytest.mark.skipif(not extratos, reason="faturas/ sem extratos")
class TestExtratoNaoContaEmDobro:
    def test_pagamento_de_fatura_nao_vira_despesa(self, client: TestClient, semeado: None) -> None:
        """A regra de ouro (D-05), verificada de ponta a ponta.

        O pagamento da fatura é transferência: promovê-lo exige contas de
        origem e destino, então ele nunca escorrega para despesa por descuido.
        """
        importacao = _upload(client, extratos[0]).json()
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]

        pagamentos = [
            item for item in itens if "pagamento de fatura" in item["linha_bruta"].lower()
        ]
        assert pagamentos, "esperava um pagamento de fatura neste extrato"
        for item in pagamentos:
            assert item["tipo_sugerido"] == "transferencia"

        resultado = client.post(
            "/importacoes/itens/aprovar", json={"ids": [pagamentos[0]["id"]]}
        ).json()
        assert resultado["promovidos"] == 0
        assert "origem e destino" in resultado["erros"][0]["erro"]

    def test_despesas_do_extrato_promovem_normal(self, client: TestClient, semeado: None) -> None:
        importacao = _upload(client, extratos[0]).json()
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        despesas = [i for i in itens if i["tipo_sugerido"] == "despesa"]

        resultado = client.post(
            "/importacoes/itens/aprovar", json={"ids": [i["id"] for i in despesas]}
        ).json()
        assert resultado["promovidos"] == len(despesas)
        assert resultado["erros"] == []
