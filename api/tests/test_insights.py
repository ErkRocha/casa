"""Fase 6 — tools SQL, detecções sem LLM e o harness em volta do modelo.

O que estes testes protegem, em ordem de importância:

1. o agente **não consegue** escrever (D-11) — verificado contra o Postgres,
   não contra a intenção do código;
2. nenhum número do relatório vem do modelo (regra 7);
3. o harness rejeita saída inválida e tenta de novo (D-12, regra 8).

Nenhum teste aqui chama modelo de verdade. O backend é substituído por uma
função que devolve o texto que o teste quiser — inclusive texto quebrado, que
é o caso interessante.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from app.insights import harness, tools
from app.insights.db import sessao_leitura
from app.insights.deteccoes import alertas_deterministicos, reais, relatorio_sem_ia
from app.schemas.insights import RelatorioGerado
from app.services.base import RegraViolada
from app.services.insights import RelatorioService

COMPETENCIA = date(2026, 7, 1)
HOJE = date(2026, 8, 16)


@pytest.fixture
def ids(client: TestClient, semeado: None) -> dict[str, int]:
    pessoas = client.get("/pessoas").json()["items"]
    arvore = client.get("/categorias/arvore/completa").json()
    alimentacao = next(c for c in arvore if c["nome"] == "Alimentação")
    transporte = next(c for c in arvore if c["nome"] == "Transporte")
    return {
        "pessoa_a": pessoas[0]["id"],
        "pessoa_b": pessoas[1]["id"],
        "alimentacao": alimentacao["id"],
        "mercado": next(s["id"] for s in alimentacao["subcategorias"] if s["nome"] == "Mercado"),
        "transporte": transporte["id"],
        "combustivel": next(
            s["id"] for s in transporte["subcategorias"] if s["nome"] == "Combustível"
        ),
    }


def criar(client: TestClient, **campos: object) -> dict:
    padrao = {"data": "2026-07-05", "valor": "100.00", "tipo": "despesa", "descricao": "Compra"}
    resposta = client.post("/transacoes", json={**padrao, **campos})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


@pytest.fixture
def cenario(client: TestClient, ids: dict) -> dict:
    """Junho e julho de 2026, com categoria, pessoa e uma receita."""
    criar(
        client,
        data="2026-06-10",
        valor="300.00",
        categoria_id=ids["mercado"],
        pessoa_id=ids["pessoa_a"],
        descricao="Mercado jun",
    )
    criar(
        client,
        data="2026-06-12",
        valor="200.00",
        categoria_id=ids["combustivel"],
        pessoa_id=None,
        descricao="Posto jun",
    )
    criar(
        client,
        data="2026-07-05",
        valor="400.00",
        categoria_id=ids["mercado"],
        pessoa_id=ids["pessoa_a"],
        descricao="Mercado jul",
    )
    criar(
        client,
        data="2026-07-06",
        valor="100.00",
        categoria_id=ids["combustivel"],
        pessoa_id=ids["pessoa_b"],
        descricao="Posto jul",
    )
    # Sem categoria — é o que derruba a cobertura.
    criar(client, data="2026-07-20", valor="250.00", descricao="Algo não classificado")
    criar(
        client,
        data="2026-07-01",
        valor="5000.00",
        tipo="receita",
        categoria_id=None,
        descricao="Salário",
    )
    return ids


class TestRoleReadOnly:
    """D-11: a impossibilidade de escrever é do Postgres, não do prompt."""

    def test_a_sessao_de_insights_le(self, cenario: dict) -> None:
        with sessao_leitura() as leitura:
            resumo = tools.resumo_mensal(leitura, COMPETENCIA, HOJE)
        assert resumo.despesas > 0

    def test_a_transacao_de_leitura_recusa_escrita(self, cenario: dict) -> None:
        """Trava externa: `postgresql_readonly` na engine.

        `25006 read_only_sql_transaction` — a transação inteira é READ ONLY,
        então nem chega a consultar permissão.
        """
        from sqlalchemy import text

        with sessao_leitura() as leitura, pytest.raises((ProgrammingError, DBAPIError)) as erro:
            leitura.execute(text("INSERT INTO pessoas (nome) VALUES ('invasor')"))

        assert getattr(erro.value.orig, "sqlstate", None) == "25006"

    def test_a_role_por_si_so_nao_escreve(self, cenario: dict) -> None:
        """Trava interna: a permissão da role na tabela alvo (D-11).

        Este teste existe porque o de cima **não** prova o que parece provar.
        As travas estão em série e a READ ONLY dispara primeiro: se alguém
        der INSERT à role amanhã, aquele teste continua verde e a garantia
        estrutural teria sumido sem nenhum sinal. Aqui a conexão é aberta sem
        a opção de transação read-only, de propósito, para o Postgres ter que
        decidir pela permissão.

        A asserção cita **a tabela** por um motivo específico, descoberto
        testando o próprio teste: com `GRANT INSERT ON pessoas` a escrita
        continua falhando com `42501`, mas por causa da terceira trava — o
        trigger de auditoria, que insere em `auditoria` e esbarra na
        permissão de lá. Verificar só o código do erro daria verde nas duas
        situações e não distinguiria "a role não escreve" de "a role não
        escreve *nesta* tabela".

        O nome da tabela é o que se checa porque o texto "permission denied"
        muda com o idioma do servidor; o identificador, não.
        """
        from sqlalchemy import create_engine, text

        from app.config import get_settings

        engine_crua = create_engine(get_settings().insights_database_url)
        try:
            with engine_crua.connect() as conexao:
                with pytest.raises((ProgrammingError, DBAPIError)) as erro:
                    conexao.execute(text("INSERT INTO pessoas (nome) VALUES ('invasor')"))
                conexao.rollback()
        finally:
            engine_crua.dispose()

        assert getattr(erro.value.orig, "sqlstate", None) == "42501"
        assert "pessoas" in str(erro.value.orig), (
            "a escrita foi barrada, mas não pela permissão em `pessoas` — "
            f"conferir o que realmente recusou: {erro.value.orig}"
        )


class TestTools:
    def test_resumo_separa_receita_de_despesa(self, cenario: dict, session: Session) -> None:
        resumo = tools.resumo_mensal(session, COMPETENCIA, HOJE)
        assert resumo.despesas == Decimal("750.00")
        assert resumo.receitas == Decimal("5000.00")
        assert resumo.saldo == Decimal("4250.00")
        assert resumo.em_curso is False

    def test_mes_corrente_vem_marcado(self, cenario: dict, session: Session) -> None:
        """Sem esta marca o texto trataria um mês pela metade como fechado."""
        resumo = tools.resumo_mensal(session, date(2026, 8, 1), HOJE)
        assert resumo.em_curso is True

    def test_gasto_agrupa_na_categoria_raiz(self, cenario: dict, session: Session) -> None:
        gasto = tools.gasto_por_categoria(session, COMPETENCIA)
        por_nome = {linha.categoria: linha.total for linha in gasto.linhas}
        assert por_nome["Alimentação"] == Decimal("400.00")
        assert por_nome["Transporte"] == Decimal("100.00")
        assert por_nome["Sem categoria"] == Decimal("250.00")

    def test_cobertura_mede_o_que_falta_categorizar(self, cenario: dict, session: Session) -> None:
        cobertura = tools.cobertura_categorias(session, COMPETENCIA)
        assert cobertura.total == Decimal("750.00")
        assert cobertura.sem_categoria == Decimal("250.00")
        assert cobertura.transacoes_sem_categoria == 1
        # 500 de 750.
        assert cobertura.percentual == Decimal("66.7")

    def test_transferencia_fica_fora_do_gasto(
        self, client: TestClient, cenario: dict, session: Session
    ) -> None:
        """D-05: pagar fatura não é despesa nova."""
        contas = client.get("/contas").json()["items"]
        criar(
            client,
            data="2026-07-15",
            valor="900.00",
            tipo="transferencia",
            categoria_id=None,
            conta_origem_id=contas[0]["id"],
            conta_destino_id=contas[1]["id"],
            descricao="Pagamento de fatura",
        )
        assert tools.resumo_mensal(session, COMPETENCIA, HOJE).despesas == Decimal("750.00")

    def test_divisao_usa_conjunto_para_pessoa_nula(self, cenario: dict, session: Session) -> None:
        divisao = tools.divisao_pessoas(session, date(2026, 6, 1))
        assert "Conjunto" in {linha.pessoa for linha in divisao.linhas}

    def test_comparacao_com_mes_anterior(self, cenario: dict, session: Session) -> None:
        comparacao = tools.comparar_periodos(session, COMPETENCIA)
        assert comparacao.total_atual == Decimal("750.00")
        assert comparacao.total_anterior == Decimal("500.00")
        assert comparacao.diferenca == Decimal("250.00")
        assert comparacao.variacao_pct == Decimal("50.0")

    def test_variacao_e_nula_sem_base(self, cenario: dict, session: Session) -> None:
        """Mês sem anterior não "aumentou 0%" — não dá para comparar."""
        comparacao = tools.comparar_periodos(session, date(2026, 6, 1))
        assert comparacao.total_anterior == Decimal("0.00")
        assert comparacao.variacao_pct is None

    def test_media_ignora_mes_sem_lancamento(self, cenario: dict, session: Session) -> None:
        """Mês zerado quase sempre é "não importei", não "não gastei"."""
        comparacao = tools.comparar_periodos(session, COMPETENCIA, meses=12)
        assert comparacao.meses_na_media == 1
        assert comparacao.media_janela == Decimal("500.00")

    def test_atipicas_calam_sem_historico(self, cenario: dict, session: Session) -> None:
        """Com um mês de base não existe padrão, logo não existe desvio.

        Regressão do que os dados reais mostraram: 1 mês de base marcava 10
        de 33 lançamentos como anomalia.
        """
        atipicas = tools.transacoes_atipicas(session, COMPETENCIA)
        assert atipicas.meses_de_base < tools.MINIMO_MESES_BASE
        assert atipicas.linhas == []

    def test_orcamento_distingue_ausencia_de_disciplina(
        self, cenario: dict, session: Session
    ) -> None:
        orcamento = tools.status_orcamento(session, COMPETENCIA)
        assert orcamento.tem_orcamento is False
        assert orcamento.estourados == 0

    def test_orcamento_estourado(self, client: TestClient, cenario: dict, session: Session) -> None:
        client.post(
            "/orcamentos",
            json={
                "categoria_id": cenario["alimentacao"],
                "competencia": "2026-07-01",
                "valor_meta": "100.00",
            },
        )
        orcamento = tools.status_orcamento(session, COMPETENCIA)
        assert orcamento.estourados == 1
        assert orcamento.linhas[0].situacao == "estourado"


class TestDeteccoes:
    """Funções puras: sem banco, sem modelo, sem relógio."""

    @pytest.mark.parametrize(
        ("valor", "esperado"),
        [
            (Decimal("0.00"), "R$ 0,00"),
            (Decimal("9.90"), "R$ 9,90"),
            (Decimal("1874.77"), "R$ 1.874,77"),
            (Decimal("1234567.89"), "R$ 1.234.567,89"),
            (Decimal("-52.15"), "-R$ 52,15"),
        ],
    )
    def test_formata_em_pt_br(self, valor: Decimal, esperado: str) -> None:
        assert reais(valor) == esperado

    def test_cobertura_baixa_vira_alerta_de_prioridade_alta(
        self, cenario: dict, session: Session
    ) -> None:
        dossie = tools.montar_dossie(session, COMPETENCIA, hoje=HOJE)
        alertas = alertas_deterministicos(dossie)
        cobertura = [a for a in alertas if a.tipo == "cobertura"]
        assert cobertura and cobertura[0].prioridade == "alta"
        # Vem primeiro: o resto do relatório depende de saber disso.
        assert alertas[0].tipo == "cobertura"

    def test_relatorio_sem_ia_sai_completo(self, cenario: dict, session: Session) -> None:
        dossie = tools.montar_dossie(session, COMPETENCIA, hoje=HOJE)
        texto = relatorio_sem_ia(dossie)
        assert "R$ 750,00" in texto
        assert "Alimentação" in texto
        assert "apenas SQL agregado" in texto


class TestHarness:
    """D-12: o modelo é uma peça no meio de código testável."""

    def _execucao(self) -> harness.Execucao:
        return harness.Execucao(
            backend="claude_code", modelo="modelo-de-teste", prompt_versao="v_teste"
        )

    def _resposta_valida(self) -> str:
        return RelatorioGerado(
            titulo="Julho de 2026",
            resumo="Um resumo com tamanho suficiente para passar na validação.",
            analise="Uma análise com mais de cinquenta caracteres para validar o schema.",
            alertas=["um alerta"],
        ).model_dump_json()

    def test_remove_a_cerca_de_markdown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """O modelo cerca o JSON mesmo instruído a não cercar."""
        cercado = f"```json\n{self._resposta_valida()}\n```"
        monkeypatch.setattr(
            harness, "_chamar_claude_code", lambda *_: (cercado, None), raising=True
        )
        execucao = self._execucao()
        gerado = harness.gerar_validado("prompt", RelatorioGerado, execucao)
        assert gerado.titulo == "Julho de 2026"
        assert execucao.tentativas == 1

    def test_reenvia_com_o_erro_anexo_e_acerta_na_segunda(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A promessa central da D-12: saída inválida vira correção, não falha."""
        chamadas: list[str] = []
        respostas = iter(['{"titulo": "curto demais"}', self._resposta_valida()])

        def falso(prompt: str, *_: object) -> tuple[str, float | None]:
            chamadas.append(prompt)
            return next(respostas), None

        monkeypatch.setattr(harness, "_chamar_claude_code", falso, raising=True)
        execucao = self._execucao()
        gerado = harness.gerar_validado("prompt original", RelatorioGerado, execucao)

        assert gerado.titulo == "Julho de 2026"
        assert execucao.tentativas == 2
        # A segunda chamada carrega o erro da primeira.
        assert "não validou" in chamadas[1]
        assert len(execucao.erros) == 1

    def test_desiste_depois_do_limite(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            harness, "_chamar_claude_code", lambda *_: ("nada disso é JSON", None), raising=True
        )
        execucao = self._execucao()
        with pytest.raises(harness.FalhaDoModelo):
            harness.gerar_validado("prompt", RelatorioGerado, execucao)
        assert execucao.tentativas == 3
        assert execucao.duracao_ms >= 0

    def test_prompt_versionado_existe_em_arquivo(self) -> None:
        """Regra 9: prompt mora em arquivo, nunca hardcoded."""
        texto = harness.carregar_prompt("relatorio_mensal_v1", {"DOSSIE": "{}", "ALERTAS": "[]"})
        assert "{{DOSSIE}}" not in texto
        assert "Não calcule nada" in texto

    def test_prompt_inexistente_falha_cedo(self) -> None:
        with pytest.raises(FileNotFoundError):
            harness.carregar_prompt("nao_existe_v9", {})


class TestRelatorioService:
    def test_gera_sem_ia_e_grava(self, cenario: dict, session: Session) -> None:
        servico = RelatorioService(session, hoje=HOJE)
        relatorio = servico.gerar_mensal(COMPETENCIA, sem_ia=True)

        assert relatorio.prompt_versao == "deterministico_v1"
        assert relatorio.execucao["backend"] == "nenhum"
        assert "R$ 750,00" in relatorio.conteudo

    def test_o_dossie_fica_gravado_junto(self, cenario: dict, session: Session) -> None:
        """Sem isto, uma afirmação do texto vira palavra contra palavra."""
        servico = RelatorioService(session, hoje=HOJE)
        relatorio = servico.gerar_mensal(COMPETENCIA, sem_ia=True)

        assert relatorio.dados_base["resumo"]["despesas"] == "750.00"
        assert relatorio.dados_base["cobertura"]["transacoes_sem_categoria"] == 1

    def test_regerar_substitui_e_preserva_o_anterior(self, cenario: dict, session: Session) -> None:
        servico = RelatorioService(session, hoje=HOJE)
        primeiro = servico.gerar_mensal(COMPETENCIA, sem_ia=True)
        segundo = servico.gerar_mensal(COMPETENCIA, sem_ia=True)

        assert primeiro.id != segundo.id
        assert primeiro.deleted_em is not None
        assert servico.vigente(COMPETENCIA) is not None
        assert servico.vigente(COMPETENCIA).id == segundo.id  # type: ignore[union-attr]

    def test_recusa_mes_sem_lancamento(self, semeado: None, session: Session) -> None:
        servico = RelatorioService(session, hoje=HOJE)
        with pytest.raises(RegraViolada, match="Nenhum lançamento"):
            servico.gerar_mensal(COMPETENCIA, sem_ia=True)

    def test_recusa_competencia_que_nao_e_dia_primeiro(
        self, cenario: dict, session: Session
    ) -> None:
        servico = RelatorioService(session, hoje=HOJE)
        with pytest.raises(RegraViolada, match="primeiro dia"):
            servico.gerar_mensal(date(2026, 7, 15), sem_ia=True)

    def test_recusa_mes_futuro(self, cenario: dict, session: Session) -> None:
        servico = RelatorioService(session, hoje=HOJE)
        with pytest.raises(RegraViolada, match="ainda não começou"):
            servico.gerar_mensal(date(2026, 12, 1), sem_ia=True)

    def test_nada_e_gravado_quando_o_modelo_falha(
        self, cenario: dict, session: Session, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Relatório pela metade é pior que nenhum: parece completo na lista."""
        monkeypatch.setattr(harness, "_chamar_claude_code", lambda *_: ("lixo", None), raising=True)
        servico = RelatorioService(session, hoje=HOJE)

        with pytest.raises(harness.FalhaDoModelo):
            servico.gerar_mensal(COMPETENCIA, sem_ia=False)

        assert servico.vigente(COMPETENCIA) is None
