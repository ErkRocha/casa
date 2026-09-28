"""Regras de categorização e o ciclo de aprendizado (D-09).

O que importa aqui: corrigir uma linha resolve as outras do mesmo
estabelecimento, e nada que o usuário escolheu na mão é sobrescrito.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FATURAS = Path(__file__).resolve().parents[2] / "faturas"
faturas = sorted(FATURAS.glob("Nubank_*.pdf")) if FATURAS.exists() else []
sem_pdfs = pytest.mark.skipif(not faturas, reason="faturas/ vazia")


@pytest.fixture
def categorias(client: TestClient, semeado: None) -> dict[str, int]:
    arvore = client.get("/categorias/arvore/completa").json()
    alimentacao = next(c for c in arvore if c["nome"] == "Alimentação")
    return {
        "alimentacao": alimentacao["id"],
        "mercado": next(s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Mercado"),
        "restaurante": next(
            s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Restaurante"
        ),
    }


class TestCrud:
    def test_cria_e_lista(self, client: TestClient, categorias: dict) -> None:
        resposta = client.post(
            "/regras",
            json={"padrao": "Zaffari", "categoria_id": categorias["mercado"]},
        )
        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["criada_por"] == "usuario"

        listagem = client.get("/regras").json()
        assert listagem["total"] == 1

    def test_regra_precisa_aplicar_alguma_coisa(self, client: TestClient, semeado: None) -> None:
        """Regra que não faz nada é ruído no motor."""
        resposta = client.post("/regras", json={"padrao": "Zaffari"})
        assert resposta.status_code == 422
        assert "categoria, local ou pessoa" in resposta.json()["detail"]

    def test_regex_invalida_e_recusada_no_cadastro(
        self, client: TestClient, categorias: dict
    ) -> None:
        """Se passasse, quebraria em silêncio no meio da próxima importação."""
        resposta = client.post(
            "/regras",
            json={
                "padrao": "[nao fecha",
                "tipo_match": "regex",
                "categoria_id": categorias["mercado"],
            },
        )
        assert resposta.status_code == 422
        assert "regular inválida" in resposta.json()["detail"]

    def test_padrao_duplicado_volta_409(self, client: TestClient, categorias: dict) -> None:
        corpo = {"padrao": "Zaffari", "categoria_id": categorias["mercado"]}
        client.post("/regras", json=corpo)
        assert client.post("/regras", json=corpo).status_code == 409

    def test_remover_e_soft_delete(self, client: TestClient, categorias: dict) -> None:
        regra = client.post(
            "/regras", json={"padrao": "Zaffari", "categoria_id": categorias["mercado"]}
        ).json()
        assert client.delete(f"/regras/{regra['id']}").status_code == 200
        assert client.get("/regras").json()["total"] == 0

    def test_ordem_e_a_de_execucao(self, client: TestClient, categorias: dict) -> None:
        """Menor prioridade roda primeiro — a lista mostra nessa ordem."""
        client.post(
            "/regras",
            json={"padrao": "B", "categoria_id": categorias["mercado"], "prioridade": 200},
        )
        client.post(
            "/regras",
            json={"padrao": "A", "categoria_id": categorias["mercado"], "prioridade": 10},
        )
        itens = client.get("/regras").json()["items"]
        assert [i["padrao"] for i in itens] == ["A", "B"]


class TestPadraoAprendido:
    """O padrão que a correção gera precisa ser reutilizável.

    Regressão: a primeira versão guardava a linha quase inteira. Num Pix isso
    inclui CPF mascarado, banco e agência — dados diferentes a cada
    transferência. A regra nascia de uso único: nunca mais casava com nada e
    só enchia a tabela.
    """

    @pytest.mark.parametrize(
        ("linha", "esperado"),
        [
            ("04 JUN •••• 7704 Pico R$ 50,00", "Pico"),
            ("05 JUN •••• 7924 S2p*2lasercinemas R$ 68,77", "S2p*2lasercinemas"),
            (
                "Transferência enviada pelo Pix MARCELLO STEFENON FILHO "
                "- •••.231.130-•• - BCO 225,00",
                "Transferência enviada pelo Pix MARCELLO STEFENON FILHO",
            ),
            (
                "Transferência Recebida Laura Penno - •••.246.050-•• - NU PAGAMENTOS - 2.100,00",
                "Transferência Recebida Laura Penno",
            ),
            (
                "Pagamento de boleto efetuado LUIZA CRED 82,03",
                "Pagamento de boleto efetuado LUIZA CRED",
            ),
            ("Débito em conta 25,00", "Débito em conta"),
        ],
    )
    def test_padrao_e_o_trecho_que_se_repete(self, linha: str, esperado: str) -> None:
        from app.services.ingestao import _padrao_de

        assert _padrao_de(linha) == esperado

    def test_padrao_nao_carrega_documento_mascarado(self) -> None:
        from app.services.ingestao import _padrao_de

        padrao = _padrao_de("Transferência enviada pelo Pix JOAO - •••.560.760-•• - BCO 10,00")
        assert "•••" not in padrao
        assert "BCO" not in padrao


class TestCasamento:
    @pytest.mark.parametrize(
        ("padrao", "tipo", "texto", "esperado"),
        [
            ("zaffari", "contem", "17 MAI Zaffari R$ 127,03", True),
            ("ZAFFARI", "contem", "Zaffari", True),
            ("Pão de Açúcar", "contem", "PAO DE ACUCAR centro", True),  # sem acento
            ("zaffari", "exato", "Zaffari", True),
            ("zaffari", "exato", "Zaffari centro", False),
            (r"^\d{2} MAI", "regex", "17 MAI Zaffari", True),
            ("padaria", "contem", "Zaffari", False),
        ],
    )
    def test_testar_padrao(
        self, client: TestClient, semeado: None, padrao: str, tipo: str, texto: str, esperado: bool
    ) -> None:
        resposta = client.post(
            "/regras/testar", json={"padrao": padrao, "tipo_match": tipo, "texto": texto}
        )
        assert resposta.json()["casa"] is esperado


@sem_pdfs
class TestAprendizado:
    """O ciclo da D-09, de ponta a ponta."""

    @pytest.fixture
    def importacao(self, client: TestClient, semeado: None) -> dict:
        return client.post(
            "/importacoes",
            files={"arquivo": (faturas[0].name, faturas[0].read_bytes(), "application/pdf")},
        ).json()

    def test_corrigir_um_item_resolve_os_outros_iguais(
        self, client: TestClient, importacao: dict, categorias: dict
    ) -> None:
        """O ponto inteiro do passo 5.

        Duas linhas de "Administradora" na mesma fatura: corrigir uma cria a
        regra, e reaplicar resolve a outra sem tocar nela.
        """
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        iguais = [i for i in itens if "Administradora" in i["linha_bruta"]]
        assert len(iguais) >= 2, "esperava repetição nesta fatura"

        # Nenhum tem categoria ainda.
        assert all(i["categoria_sugerida_id"] is None for i in iguais)

        # Corrige só o primeiro.
        client.patch(
            f"/importacoes/itens/{iguais[0]['id']}",
            json={"categoria_sugerida_id": categorias["mercado"]},
        )

        # A regra nasceu sozinha.
        regras = client.get("/regras").json()["items"]
        assert len(regras) == 1
        assert regras[0]["criada_por"] == "correcao_automatica"

        # Reaplicar resolve os outros.
        resultado = client.post("/regras/reaplicar").json()
        assert resultado["alterados"] >= 1

        depois = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        iguais_depois = [i for i in depois if "Administradora" in i["linha_bruta"]]
        assert all(i["categoria_sugerida_id"] == categorias["mercado"] for i in iguais_depois)

    def test_reaplicar_nao_sobrescreve_escolha_manual(
        self, client: TestClient, importacao: dict, categorias: dict
    ) -> None:
        """Se você escolheu na mão, a regra não passa por cima."""
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        alvo = itens[0]

        # Regra que casaria com tudo.
        client.post(
            "/regras",
            json={"padrao": "R$", "categoria_id": categorias["restaurante"]},
        )
        # Mas este item já tem escolha manual.
        client.patch(
            f"/importacoes/itens/{alvo['id']}",
            json={"categoria_sugerida_id": categorias["mercado"]},
        )

        client.post("/regras/reaplicar")

        depois = next(
            i
            for i in client.get(f"/importacoes/{importacao['id']}").json()["itens"]
            if i["id"] == alvo["id"]
        )
        assert depois["categoria_sugerida_id"] == categorias["mercado"]

    def test_reaplicar_nao_mexe_em_item_aprovado(
        self, client: TestClient, importacao: dict, categorias: dict
    ) -> None:
        """Item aprovado virou transação; regra nova não reescreve o passado."""
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        client.post("/importacoes/itens/aprovar", json={"ids": [itens[0]["id"]]})

        client.post("/regras", json={"padrao": "R$", "categoria_id": categorias["mercado"]})
        resultado = client.post("/regras/reaplicar").json()

        aprovado = next(
            i
            for i in client.get(f"/importacoes/{importacao['id']}").json()["itens"]
            if i["id"] == itens[0]["id"]
        )
        assert aprovado["status"] == "aprovado"
        # O aprovado nem entrou na conta.
        assert resultado["avaliados"] == len(itens) - 1

    def test_correcao_repetida_reforca_em_vez_de_duplicar(
        self, client: TestClient, importacao: dict, categorias: dict
    ) -> None:
        itens = client.get(f"/importacoes/{importacao['id']}").json()["itens"]
        iguais = [i for i in itens if "Administradora" in i["linha_bruta"]]

        for item in iguais[:2]:
            client.patch(
                f"/importacoes/itens/{item['id']}",
                json={"categoria_sugerida_id": categorias["mercado"]},
            )

        regras = client.get("/regras").json()
        assert regras["total"] == 1
        assert regras["items"][0]["acertos"] >= 1

    def test_reaplicar_so_na_importacao_pedida(
        self, client: TestClient, importacao: dict, categorias: dict
    ) -> None:
        client.post("/regras", json={"padrao": "R$", "categoria_id": categorias["mercado"]})
        resultado = client.post(f"/regras/reaplicar?importacao_id={importacao['id']}").json()
        assert resultado["avaliados"] == importacao["total_itens"]
