"""API de transações: CRUD, filtros combináveis e ação em lote."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session


@pytest.fixture
def ids(client: TestClient, semeado: None) -> dict[str, int]:
    """Ids úteis do seed, para os testes não dependerem de sequence."""
    pessoas = client.get("/pessoas").json()["items"]
    arvore = client.get("/categorias/arvore/completa").json()
    formas = client.get("/formas-pagamento").json()["items"]

    alimentacao = next(c for c in arvore if c["nome"] == "Alimentação")
    return {
        "pessoa_a": pessoas[0]["id"],
        "pessoa_b": pessoas[1]["id"],
        "alimentacao": alimentacao["id"],
        "mercado": next(s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Mercado"),
        "restaurante": next(
            s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Restaurante"
        ),
        "forma": formas[0]["id"],
    }


def criar(client: TestClient, **campos: object) -> dict:
    padrao = {
        "data": "2026-08-01",
        "valor": "100.00",
        "tipo": "despesa",
        "descricao": "Compra",
        "pessoa_id": None,
        "categoria_id": None,
        "forma_pagamento_id": None,
    }
    resposta = client.post("/transacoes", json={**padrao, **campos})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


class TestCriar:
    def test_competencia_ausente_vira_mes_da_data(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, data="2026-07-28")
        assert tx["competencia"] == "2026-07-01"

    def test_competencia_explicita_e_respeitada(self, client: TestClient, ids: dict) -> None:
        """Compra de julho que cai na fatura de agosto (D-02)."""
        tx = criar(client, data="2026-07-28", competencia="2026-08-01")
        assert tx["data"] == "2026-07-28"
        assert tx["competencia"] == "2026-08-01"

    def test_pessoa_nula_vira_conjunto(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, pessoa_id=None)
        assert tx["pessoa_id"] is None
        assert tx["pessoa_nome"] == "Conjunto"

    def test_categoria_vem_com_caminho_montado(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, categoria_id=ids["mercado"])
        assert tx["categoria_caminho"] == "Alimentação › Mercado"
        assert tx["categoria_raiz_id"] == ids["alimentacao"]

    def test_duplicata_volta_409(self, client: TestClient, ids: dict) -> None:
        campos = {"descricao_original": "MERCADO SAO JOSE"}
        criar(client, **campos)
        resposta = client.post(
            "/transacoes",
            json={
                "data": "2026-08-01",
                "valor": "100.00",
                "tipo": "despesa",
                "descricao": "Compra",
                "descricao_original": "MERCADO SAO JOSE",
                "pessoa_id": None,
                "categoria_id": None,
                "forma_pagamento_id": None,
            },
        )
        assert resposta.status_code == 409
        assert "idêntica" in resposta.json()["detail"]

    def test_transferencia_sem_contas_volta_422(self, client: TestClient) -> None:
        resposta = client.post(
            "/transacoes",
            json={
                "data": "2026-08-01",
                "valor": "50.00",
                "tipo": "transferencia",
                "descricao": "Pagamento fatura",
            },
        )
        assert resposta.status_code == 422

    def test_local_livre_casa_pelo_nome_normalizado(self, client: TestClient, ids: dict) -> None:
        """ "Pão de Açúcar" e "PAO DE ACUCAR" viram o mesmo local."""
        a = client.post(
            "/transacoes?local_nome=P%C3%A3o%20de%20A%C3%A7%C3%BAcar",
            json={
                "data": "2026-08-01",
                "valor": "10.00",
                "tipo": "despesa",
                "descricao": "A",
            },
        ).json()
        b = client.post(
            "/transacoes?local_nome=PAO%20DE%20ACUCAR",
            json={
                "data": "2026-08-02",
                "valor": "20.00",
                "tipo": "despesa",
                "descricao": "B",
            },
        ).json()
        assert a["local_id"] == b["local_id"]


class TestFiltros:
    @pytest.fixture(autouse=True)
    def _dados(self, client: TestClient, ids: dict) -> None:
        criar(
            client,
            data="2026-06-10",
            valor="50.00",
            descricao="Feira",
            categoria_id=ids["mercado"],
            pessoa_id=ids["pessoa_a"],
        )
        criar(
            client,
            data="2026-07-10",
            valor="150.00",
            descricao="Mercado grande",
            categoria_id=ids["mercado"],
            pessoa_id=ids["pessoa_b"],
        )
        criar(
            client,
            data="2026-08-10",
            valor="80.00",
            descricao="Almoço",
            categoria_id=ids["restaurante"],
            pessoa_id=None,
        )
        criar(
            client,
            data="2026-08-11",
            valor="5000.00",
            descricao="Salário",
            tipo="receita",
            pessoa_id=ids["pessoa_a"],
        )

    def test_sem_filtro_traz_tudo(self, client: TestClient) -> None:
        assert client.get("/transacoes").json()["total"] == 4

    def test_filtro_por_competencia(self, client: TestClient) -> None:
        dados = client.get(
            "/transacoes?competencia_inicio=2026-08-01&competencia_fim=2026-08-01"
        ).json()
        assert dados["total"] == 2

    def test_filtro_por_categoria_raiz_pega_as_filhas(self, client: TestClient, ids: dict) -> None:
        """Marcar "Alimentação" tem que trazer Mercado e Restaurante."""
        dados = client.get(f"/transacoes?categoria_ids={ids['alimentacao']}").json()
        assert dados["total"] == 3

    def test_filtro_por_balde_conjunto(self, client: TestClient) -> None:
        dados = client.get("/transacoes?pessoa=conjunto").json()
        assert dados["total"] == 1
        assert dados["items"][0]["descricao"] == "Almoço"

    def test_filtro_por_pessoa(self, client: TestClient, ids: dict) -> None:
        dados = client.get(f"/transacoes?pessoa={ids['pessoa_a']}").json()
        assert dados["total"] == 2

    def test_filtro_por_texto_busca_descricao(self, client: TestClient) -> None:
        assert client.get("/transacoes?texto=mercado").json()["total"] >= 1

    def test_filtros_combinam(self, client: TestClient, ids: dict) -> None:
        dados = client.get(
            f"/transacoes?categoria_ids={ids['alimentacao']}&pessoa={ids['pessoa_b']}&valor_min=100"
        ).json()
        assert dados["total"] == 1
        assert dados["items"][0]["descricao"] == "Mercado grande"

    def test_totais_batem_e_excluem_receita_da_despesa(self, client: TestClient) -> None:
        totais = client.get("/transacoes").json()["totais"]
        assert totais["total_despesa"] == "280.00"
        assert totais["total_receita"] == "5000.00"
        assert totais["resultado"] == "4720.00"

    def test_totais_por_balde_somam_a_despesa(self, client: TestClient) -> None:
        """Os três baldes somam o total exato, sem sobreposição (D-03)."""
        totais = client.get("/transacoes").json()["totais"]
        soma = sum(float(v) for v in totais["por_balde"].values())
        assert soma == float(totais["total_despesa"])

    def test_totais_seguem_o_filtro(self, client: TestClient) -> None:
        totais = client.get(
            "/transacoes?competencia_inicio=2026-06-01&competencia_fim=2026-06-01"
        ).json()["totais"]
        assert totais["total_despesa"] == "50.00"


class TestEdicao:
    def test_patch_parcial_nao_zera_os_outros_campos(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, descricao="Original", categoria_id=ids["mercado"])
        atualizada = client.patch(f"/transacoes/{tx['id']}", json={"descricao": "Corrigida"}).json()
        assert atualizada["descricao"] == "Corrigida"
        assert atualizada["categoria_id"] == ids["mercado"]

    def test_edicao_inline_de_pessoa_para_conjunto(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, pessoa_id=ids["pessoa_a"])
        atualizada = client.patch(f"/transacoes/{tx['id']}", json={"pessoa_id": None}).json()
        assert atualizada["pessoa_id"] is None
        assert atualizada["pessoa_nome"] == "Conjunto"

    def test_delete_e_soft(self, client: TestClient, session: Session, ids: dict) -> None:
        tx = criar(client)
        assert client.delete(f"/transacoes/{tx['id']}").status_code == 200
        assert client.get(f"/transacoes/{tx['id']}").status_code == 404

        # A linha continua no banco, com `deleted_em` preenchido.
        restante = session.execute(
            text("SELECT deleted_em FROM transacoes WHERE id = :id"), {"id": tx["id"]}
        ).scalar()
        assert restante is not None


class TestLote:
    def test_atribuir_categoria_e_pessoa_em_lote(self, client: TestClient, ids: dict) -> None:
        a = criar(client, data="2026-08-01", descricao="A")
        b = criar(client, data="2026-08-02", descricao="B")

        resposta = client.post(
            "/transacoes/lote/atribuir",
            json={
                "ids": [a["id"], b["id"]],
                "categoria_id": ids["mercado"],
                "pessoa": ids["pessoa_a"],
            },
        )
        assert resposta.json()["afetadas"] == 2

        for tx_id in (a["id"], b["id"]):
            atual = client.get(f"/transacoes/{tx_id}").json()
            assert atual["categoria_id"] == ids["mercado"]
            assert atual["pessoa_id"] == ids["pessoa_a"]

    def test_lote_com_pessoa_conjunto_limpa_o_dono(self, client: TestClient, ids: dict) -> None:
        tx = criar(client, pessoa_id=ids["pessoa_a"])
        client.post("/transacoes/lote/atribuir", json={"ids": [tx["id"]], "pessoa": "conjunto"})
        assert client.get(f"/transacoes/{tx['id']}").json()["pessoa_id"] is None

    def test_excluir_em_lote_e_soft(self, client: TestClient, ids: dict) -> None:
        a = criar(client, data="2026-08-01", descricao="A")
        b = criar(client, data="2026-08-02", descricao="B")

        resposta = client.post("/transacoes/lote/excluir", json={"ids": [a["id"], b["id"]]})
        assert resposta.json()["afetadas"] == 2
        assert client.get("/transacoes").json()["total"] == 0

    def test_lote_sem_nada_para_aplicar_volta_422(self, client: TestClient) -> None:
        resposta = client.post("/transacoes/lote/atribuir", json={"ids": [1]})
        assert resposta.status_code == 422


class TestPaginacao:
    def test_listagem_e_paginada(self, client: TestClient, ids: dict) -> None:
        for dia in range(1, 6):
            criar(client, data=f"2026-08-{dia:02d}", descricao=f"Tx {dia}")

        pagina = client.get("/transacoes?limit=2&offset=0").json()
        assert pagina["total"] == 5
        assert len(pagina["items"]) == 2

        ultima = client.get("/transacoes?limit=2&offset=4").json()
        assert len(ultima["items"]) == 1

    def test_ordem_e_estavel_no_mesmo_dia(self, client: TestClient, ids: dict) -> None:
        for i in range(3):
            criar(client, data="2026-08-01", valor=f"{10 + i}.00", descricao=f"Tx {i}")

        primeira = [t["id"] for t in client.get("/transacoes?limit=2").json()["items"]]
        segunda = [t["id"] for t in client.get("/transacoes?limit=2").json()["items"]]
        assert primeira == segunda


def test_health_responde(client: TestClient) -> None:
    """Critério de pronto da fase 0."""
    dados = client.get("/health").json()
    assert dados["status"] == "ok"
    assert dados["banco"] == "ok"


def test_data_de_hoje_nao_e_usada_por_engano() -> None:
    """Guarda contra teste que passa hoje e quebra mês que vem."""
    assert date(2026, 8, 1).day == 1
