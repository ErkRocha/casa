"""Agregações de Analytics.

O que mais importa aqui: transferência fora de todo cálculo de gasto, e os
três baldes somando o total exato.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import TipoPessoa
from app.models import Pessoa
from app.schemas.transacoes import TransacaoFiltros
from app.services.analytics import AnalyticsService

#: "Hoje" fixo, para o teste não mudar de resultado ao virar o mês.
HOJE = date(2026, 8, 6)


@pytest.fixture
def ids(client: TestClient, semeado: None) -> dict[str, int]:
    pessoas = client.get("/pessoas").json()["items"]
    arvore = client.get("/categorias/arvore/completa").json()
    contas = client.get("/contas").json()["items"]
    alimentacao = next(c for c in arvore if c["nome"] == "Alimentação")
    transporte = next(c for c in arvore if c["nome"] == "Transporte")

    return {
        "pessoa_a": pessoas[0]["id"],
        "pessoa_b": pessoas[1]["id"],
        "alimentacao": alimentacao["id"],
        "mercado": next(s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Mercado"),
        "restaurante": next(
            s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Restaurante"
        ),
        "transporte": transporte["id"],
        "combustivel": next(
            s["id"] for s in transporte["subcategorias"] if s["nome"] == "Combustível"
        ),
        "conta_a": contas[0]["id"],
        "conta_b": contas[1]["id"],
    }


def criar(client: TestClient, **campos: object) -> dict:
    padrao = {"data": "2026-08-01", "valor": "100.00", "tipo": "despesa", "descricao": "Compra"}
    resposta = client.post("/transacoes", json={**padrao, **campos})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def cenario(client: TestClient, ids: dict) -> dict:
    """Julho e agosto de 2026, com um pouco de tudo."""
    # Julho
    criar(
        client,
        data="2026-07-05",
        valor="300.00",
        categoria_id=ids["mercado"],
        pessoa_id=ids["pessoa_a"],
        descricao="Mercado jul",
    )
    criar(
        client,
        data="2026-07-06",
        valor="200.00",
        categoria_id=ids["combustivel"],
        pessoa_id=ids["pessoa_b"],
        descricao="Posto jul",
    )
    criar(
        client,
        data="2026-07-07",
        valor="500.00",
        categoria_id=ids["mercado"],
        pessoa_id=None,
        descricao="Mercado conjunto jul",
    )

    # Agosto
    criar(
        client,
        data="2026-08-01",
        valor="100.00",
        categoria_id=ids["mercado"],
        pessoa_id=ids["pessoa_a"],
        descricao="Mercado ago",
    )
    criar(
        client,
        data="2026-08-02",
        valor="150.00",
        categoria_id=ids["restaurante"],
        pessoa_id=ids["pessoa_b"],
        descricao="Almoço ago",
    )
    criar(
        client,
        data="2026-08-03",
        valor="250.00",
        categoria_id=ids["combustivel"],
        pessoa_id=None,
        descricao="Posto ago",
    )

    # Receita: não é gasto.
    criar(
        client,
        data="2026-08-05",
        valor="5000.00",
        tipo="receita",
        pessoa_id=ids["pessoa_a"],
        descricao="Salário",
    )

    # Transferência: pagar fatura não é despesa nova (D-05).
    criar(
        client,
        data="2026-08-04",
        valor="900.00",
        tipo="transferencia",
        descricao="Pagamento da fatura",
        conta_origem_id=ids["conta_a"],
        conta_destino_id=ids["conta_b"],
    )
    return ids


def servico(session: Session) -> AnalyticsService:
    return AnalyticsService(session, hoje=HOJE)


VAZIO = TransacaoFiltros()


class TestRegraDeOuro:
    def test_transferencia_fica_fora_do_gasto(self, session: Session, cenario: dict) -> None:
        evolucao = servico(session).evolucao_mensal(VAZIO)
        agosto = next(p for p in evolucao.pontos if p.competencia == date(2026, 8, 1))
        # 100 + 150 + 250 = 500. A transferência de 900 e o salário de 5000
        # não entram.
        assert agosto.total == 500

    def test_receita_fica_fora_do_gasto(self, session: Session, cenario: dict) -> None:
        composicao = servico(session).composicao_categoria(VAZIO)
        nomes = {linha.nome for linha in composicao.linhas}
        assert "Receita" not in nomes


class TestEvolucaoMensal:
    def test_baldes_somam_o_total_do_mes(self, session: Session, cenario: dict) -> None:
        """Sem sobreposição possível — é o ponto de D-03."""
        for ponto in servico(session).evolucao_mensal(VAZIO).pontos:
            assert ponto.pessoa_a + ponto.pessoa_b + ponto.conjunto == ponto.total

    def test_mes_corrente_vem_marcado(self, session: Session, cenario: dict) -> None:
        pontos = servico(session).evolucao_mensal(VAZIO).pontos
        em_curso = [p for p in pontos if p.em_curso]
        assert len(em_curso) == 1
        assert em_curso[0].competencia == date(2026, 8, 1)

    def test_meses_sem_lancamento_aparecem_zerados(self, session: Session, cenario: dict) -> None:
        """O eixo não pode pular buraco."""
        pontos = servico(session).evolucao_mensal(VAZIO).pontos
        assert len(pontos) == 12
        assert any(p.total == 0 for p in pontos)

    def test_rotulos_usam_o_nome_cadastrado(self, session: Session, cenario: dict) -> None:
        """O rótulo sai do cadastro, não de constante no código.

        Lê o nome do banco em vez de fixar "Laura"/"Erik": o teste tem que
        continuar valendo para quem renomear as pessoas pelo painel, que é
        justamente o comportamento que ele protege.
        """
        pessoas = [
            p.nome
            for p in session.scalars(
                select(Pessoa)
                .where(Pessoa.tipo == TipoPessoa.INDIVIDUAL, Pessoa.deleted_em.is_(None))
                .order_by(Pessoa.id)
            )
        ]
        evolucao = servico(session).evolucao_mensal(VAZIO)
        assert evolucao.rotulo_a == pessoas[0]
        assert evolucao.rotulo_b == pessoas[1]


class TestComposicao:
    def test_nivel_raiz_agrupa_pela_categoria_pai(self, session: Session, cenario: dict) -> None:
        composicao = servico(session).composicao_categoria(VAZIO)
        por_nome = {linha.nome: linha.valor for linha in composicao.linhas}
        # Mercado 300 + 500 + 100, Restaurante 150 => Alimentação 1050
        assert por_nome["Alimentação"] == 1050
        assert por_nome["Transporte"] == 450

    def test_ordenado_por_valor_desc(self, session: Session, cenario: dict) -> None:
        valores = [linha.valor for linha in servico(session).composicao_categoria(VAZIO).linhas]
        assert valores == sorted(valores, reverse=True)

    def test_percentuais_somam_cem(self, session: Session, cenario: dict) -> None:
        linhas = servico(session).composicao_categoria(VAZIO).linhas
        assert abs(sum(linha.percentual for linha in linhas) - 100) < 1

    def test_drill_down_desce_para_as_filhas(self, session: Session, cenario: dict) -> None:
        composicao = servico(session).composicao_categoria(VAZIO, cenario["alimentacao"])
        assert composicao.categoria_pai is not None
        assert composicao.categoria_pai.nome == "Alimentação"
        por_nome = {linha.nome: linha.valor for linha in composicao.linhas}
        assert por_nome == {"Mercado": 900, "Restaurante": 150}

    def test_cor_vem_do_cadastro_e_nao_do_ranking(self, session: Session, cenario: dict) -> None:
        """Filtrar reordena as barras, mas ninguém troca de cor."""
        todas = servico(session).composicao_categoria(VAZIO)
        cor_alimentacao = next(linha.cor for linha in todas.linhas if linha.nome == "Alimentação")

        so_transporte = TransacaoFiltros(categoria_ids=[cenario["transporte"]])
        filtrada = servico(session).composicao_categoria(so_transporte)
        assert all(linha.nome == "Transporte" for linha in filtrada.linhas)

        # A cor de Alimentação continua a mesma coisa quando ela reaparece.
        de_novo = servico(session).composicao_categoria(VAZIO)
        assert (
            next(linha.cor for linha in de_novo.linhas if linha.nome == "Alimentação")
            == cor_alimentacao
        )


class TestDivisaoPessoas:
    def test_tres_baldes_somam_cem_por_cento(self, session: Session, cenario: dict) -> None:
        divisao = servico(session).divisao_pessoas(VAZIO)
        assert len(divisao.linhas) == 3
        assert abs(sum(linha.percentual for linha in divisao.linhas) - 100) < 1

    def test_traz_o_mes_anterior_para_o_delta(self, session: Session, cenario: dict) -> None:
        divisao = servico(session).divisao_pessoas(VAZIO)
        conjunto = next(linha for linha in divisao.linhas if linha.balde == "conjunto")
        assert conjunto.valor == 250  # agosto
        assert conjunto.valor_anterior == 500  # julho

    def test_total_bate_com_a_soma_dos_baldes(self, session: Session, cenario: dict) -> None:
        divisao = servico(session).divisao_pessoas(VAZIO)
        assert sum(linha.valor for linha in divisao.linhas) == divisao.total


class TestOrcamento:
    def test_realizado_soma_as_subcategorias(
        self, client: TestClient, session: Session, cenario: dict
    ) -> None:
        """Meta em "Alimentação" tem que contar Mercado e Restaurante."""
        client.post(
            "/orcamentos",
            json={
                "categoria_id": cenario["alimentacao"],
                "competencia": "2026-08-01",
                "valor_meta": "500.00",
            },
        )
        progresso = servico(session).orcamento(date(2026, 8, 1))
        linha = progresso.linhas[0]
        assert linha.realizado == 250  # 100 mercado + 150 restaurante
        assert linha.percentual == 50
        assert linha.status == "ok"

    def test_status_acompanha_o_percentual(
        self, client: TestClient, session: Session, cenario: dict
    ) -> None:
        client.post(
            "/orcamentos",
            json={
                "categoria_id": cenario["transporte"],
                "competencia": "2026-08-01",
                "valor_meta": "100.00",
            },
        )
        linha = servico(session).orcamento(date(2026, 8, 1)).linhas[0]
        assert linha.realizado == 250
        assert linha.status == "estourado"

    def test_fracao_decorrida_reflete_o_dia(self, session: Session, cenario: dict) -> None:
        """Dia 6 de 31 — sem isso, 50% da meta assusta à toa no começo do mês."""
        progresso = servico(session).orcamento(date(2026, 8, 1))
        assert abs(float(progresso.fracao_decorrida) - 6 / 31) < 0.01

    def test_orcamento_em_subcategoria_e_recusado(self, client: TestClient, cenario: dict) -> None:
        resposta = client.post(
            "/orcamentos",
            json={
                "categoria_id": cenario["mercado"],
                "competencia": "2026-08-01",
                "valor_meta": "100.00",
            },
        )
        assert resposta.status_code == 422
        assert "categoria raiz" in resposta.json()["detail"]


class TestComparativo:
    def test_compara_mes_atual_com_anterior(self, session: Session, cenario: dict) -> None:
        linhas = {linha.chave: linha for linha in servico(session).comparativo(VAZIO).linhas}
        assert linhas["mes_atual"].valor == 500
        assert linhas["mes_anterior"].valor == 1000
        assert linhas["mes_atual"].valor_base == 1000

    def test_media_do_grafico_bate_com_a_do_card(self, session: Session, cenario: dict) -> None:
        """A linha tracejada e o card mostram a mesma coisa.

        Regressão: a evolução dividia pela janela inteira (12) e o comparativo
        fazia AVG só sobre os meses com lançamento. Com dois meses de dados a
        tela mostrava 91,67 no gráfico e 550,00 no card — dois números para a
        mesma grandeza, lado a lado.
        """
        svc = servico(session)
        media_grafico = svc.evolucao_mensal(VAZIO).media_total
        media_card = next(
            linha.valor for linha in svc.comparativo(VAZIO).linhas if linha.chave == "media_12m"
        )
        assert media_grafico == media_card
        # (1000 de julho + 500 de agosto) / 2 meses com lançamento
        assert media_grafico == Decimal("750.00")


class TestFiltrosCompartilhados:
    def test_filtro_de_categoria_afeta_a_evolucao(self, session: Session, cenario: dict) -> None:
        filtros = TransacaoFiltros(categoria_ids=[cenario["transporte"]])
        evolucao = servico(session).evolucao_mensal(filtros)
        agosto = next(p for p in evolucao.pontos if p.competencia == date(2026, 8, 1))
        assert agosto.total == 250

    def test_filtro_de_pessoa_afeta_a_composicao(self, session: Session, cenario: dict) -> None:
        filtros = TransacaoFiltros(pessoa=cenario["pessoa_a"])
        composicao = servico(session).composicao_categoria(filtros)
        assert composicao.total_nivel == 400  # 300 jul + 100 ago


class TestGuardaDoCasal:
    def test_terceira_pessoa_falha_alto(self, client: TestClient, cenario: dict) -> None:
        """Melhor recusar do que dissolver o gasto de alguém em silêncio."""
        client.post("/pessoas", json={"nome": "Pessoa C"})
        resposta = client.get("/analytics/resumo")
        assert resposta.status_code == 422
        assert "duas pessoas" in resposta.json()["detail"]


class TestEndpointResumo:
    def test_resumo_traz_os_cinco_paineis(self, client: TestClient, cenario: dict) -> None:
        dados = client.get("/analytics/resumo").json()
        assert set(dados) == {
            "evolucao_mensal",
            "composicao_categoria",
            "divisao_pessoas",
            "orcamento",
            "comparativo",
        }

    def test_resumo_aceita_os_mesmos_filtros_da_listagem(
        self, client: TestClient, cenario: dict
    ) -> None:
        resposta = client.get(
            f"/analytics/resumo?categoria_ids={cenario['transporte']}"
            f"&pessoa=conjunto&competencia_inicio=2026-08-01&competencia_fim=2026-08-01"
        )
        assert resposta.status_code == 200
