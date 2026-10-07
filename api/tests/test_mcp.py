"""Servidor MCP do chat sob demanda (D-20).

Cada tool é chamada por um cliente MCP de verdade — em processo, e pelo
stdio de `python -m app.mcp` —, contra o banco de teste e pela role
read-only da D-11. O que se protege, em ordem:

1. não existe tool de escrita, e a sessão é a read-only (o Postgres recusa);
2. os números conferem com o cenário, transferência fora do gasto, apagado
   fora de tudo, dinheiro como texto;
3. a busca respeita o limite e diz quando há mais;
4. a stdout do processo só tem protocolo.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient
from mcp import Client, StdioServerParameters
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.insights.db import sessao_leitura
from app.mcp import servidor as modulo_servidor
from app.mcp.consultas import LIMITE_MAXIMO
from app.mcp.servidor import criar_servidor
from app.models import Relatorio

API = Path(__file__).resolve().parents[1]

TOOLS = {
    "resumo_do_mes",
    "cobertura_de_categorias",
    "gasto_por_categoria",
    "gasto_por_pessoa",
    "comparar_com_meses_anteriores",
    "status_do_orcamento",
    "gastos_fora_do_padrao",
    "assinaturas_reajustadas",
    "listar_cadastros",
    "buscar_transacoes",
    "totalizar_transacoes",
    "ler_relatorio_do_mes",
}


def _rodar[T](acao: Callable[[Client], Awaitable[T]]) -> T:
    async def principal() -> T:
        async with Client(criar_servidor()) as cliente:
            return await acao(cliente)

    return anyio.run(principal)


def _chamar(nome: str, argumentos: dict[str, Any] | None = None) -> dict[str, Any]:
    async def acao(c: Client) -> dict[str, Any]:
        r = await c.call_tool(nome, argumentos or {})
        assert not r.is_error, r.content
        assert r.structured_content is not None
        return r.structured_content

    return _rodar(acao)


def _erro(nome: str, argumentos: dict[str, Any]) -> str:
    async def acao(c: Client) -> str:
        r = await c.call_tool(nome, argumentos)
        assert r.is_error
        return " ".join(getattr(b, "text", "") for b in r.content)

    return _rodar(acao)


# --- cenário ------------------------------------------------------------------


@pytest.fixture
def ids(client: TestClient, semeado: None) -> dict[str, int]:
    pessoas = client.get("/pessoas").json()["items"]
    arvore = client.get("/categorias/arvore/completa").json()
    contas = {c["nome"]: c["id"] for c in client.get("/contas").json()["items"]}

    def raiz(nome: str) -> dict[str, Any]:
        return next(c for c in arvore if c["nome"] == nome)

    def filha(pai: str, nome: str) -> int:
        return next(s["id"] for s in raiz(pai)["subcategorias"] if s["nome"] == nome)

    return {
        "pessoa_a": pessoas[0]["id"],
        "pessoa_b": pessoas[1]["id"],
        "alimentacao": raiz("Alimentação")["id"],
        "mercado": filha("Alimentação", "Mercado"),
        "transporte": raiz("Transporte")["id"],
        "combustivel": filha("Transporte", "Combustível"),
        "salario": filha("Receita", "Salário"),
        "corrente": contas["Conta Corrente"],
        "poupanca": contas["Poupança"],
    }


def _criar(client: TestClient, **campos: object) -> dict[str, Any]:
    r = client.post("/transacoes", json={"tipo": "despesa", **campos})
    assert r.status_code == 201, r.text
    resultado: dict[str, Any] = r.json()
    return resultado


@pytest.fixture
def cenario(client: TestClient, ids: dict[str, int]) -> dict[str, int]:
    """Julho/2026: 500,50 de despesa (300 + 120,50 + 80), 5.000 de receita,
    1.000 de transferência e um lançamento apagado. Junho: 200 de mercado."""
    _criar(client, data="2026-06-10", valor="200.00", descricao="Mercado de junho",
           categoria_id=ids["mercado"], pessoa_id=ids["pessoa_a"])  # fmt: skip
    _criar(client, data="2026-07-05", valor="300.00", descricao="Mercado Bom Preço",
           categoria_id=ids["mercado"], pessoa_id=ids["pessoa_a"])  # fmt: skip
    _criar(client, data="2026-07-12", valor="120.50", descricao="Posto Shell",
           categoria_id=ids["combustivel"], pessoa_id=ids["pessoa_b"])  # fmt: skip
    _criar(client, data="2026-07-20", valor="80.00", descricao="Padaria do bairro",
           categoria_id=ids["alimentacao"])  # fmt: skip
    _criar(client, data="2026-07-01", valor="5000.00", tipo="receita", descricao="Salário",
           categoria_id=ids["salario"], pessoa_id=ids["pessoa_a"])  # fmt: skip
    _criar(client, data="2026-07-02", valor="1000.00", tipo="transferencia",
           descricao="Aplicação na poupança", conta_origem_id=ids["corrente"],
           conta_destino_id=ids["poupanca"])  # fmt: skip
    apagada = _criar(client, data="2026-07-15", valor="999.00", descricao="Lançamento apagado",
                     categoria_id=ids["mercado"])  # fmt: skip
    assert client.delete(f"/transacoes/{apagada['id']}").status_code == 200
    return ids


# --- 1. só leitura, por construção ------------------------------------------------


def test_tools_expostas_sao_exatamente_as_de_leitura() -> None:
    async def acao(c: Client) -> list[Any]:
        return list((await c.list_tools()).tools)

    tools = _rodar(acao)
    assert {t.name for t in tools} == TOOLS
    for t in tools:
        assert t.annotations is not None and t.annotations.read_only_hint is True, t.name
        assert t.annotations.destructive_hint is False, t.name
        assert t.description, f"{t.name} sem descrição"
    verbos_de_escrita = (
        "criar", "apagar", "remover", "editar", "atualizar", "inserir",
        "lancar", "aprovar", "rejeitar", "gravar", "salvar", "executar",
    )  # fmt: skip
    for t in tools:
        assert not any(v in t.name for v in verbos_de_escrita), t.name


def test_servidor_usa_a_sessao_read_only() -> None:
    """A fábrica padrão é a da D-11, e o pacote não importa a sessão do app."""
    assert criar_servidor.__defaults__ == (sessao_leitura,)
    for arquivo in (API / "app" / "mcp").glob("*.py"):
        arvore = ast.parse(arquivo.read_text("utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom):
                assert no.module != "app.db", f"{arquivo.name} importa a sessão de escrita"
                nomes = {a.name for a in no.names}
                assert "SessionLocal" not in nomes, arquivo.name
    assert "SessionLocal" not in vars(modulo_servidor)


def test_a_role_da_sessao_nao_escreve() -> None:
    with sessao_leitura() as s:
        assert s.execute(text("SELECT current_user")).scalar_one() == get_settings().insights_role
        with pytest.raises(DBAPIError) as erro:
            s.execute(text("INSERT INTO pessoas (nome, tipo) VALUES ('invasor', 'individual')"))
        # 42501: permissão negada pela role; 25006: transação read-only. As
        # duas travas existem; qualquer uma basta.
        assert getattr(erro.value.orig, "sqlstate", None) in {"42501", "25006"}


# --- 2. números -------------------------------------------------------------------


def test_resumo_do_mes(cenario: dict[str, int]) -> None:
    r = _chamar("resumo_do_mes", {"competencia": "2026-07"})
    assert (r["despesas"], r["receitas"], r["saldo"]) == ("500.50", "5000.00", "4499.50")
    assert r["transacoes"] == 4, "transferência e apagado fora"


def test_gasto_por_categoria_e_por_pessoa(cenario: dict[str, int]) -> None:
    categorias = _chamar("gasto_por_categoria", {"competencia": "2026-07"})
    totais = {linha["categoria"]: linha["total"] for linha in categorias["linhas"]}
    assert totais == {"Alimentação": "380.00", "Transporte": "120.50"}

    pessoas = _chamar("gasto_por_pessoa", {"competencia": "2026-07"})
    assert pessoas["total"] == "500.50"
    assert "Conjunto" in {linha["pessoa"] for linha in pessoas["linhas"]}


def test_cobertura_comparacao_orcamento_atipicos_reajustes(cenario: dict[str, int]) -> None:
    cobertura = _chamar("cobertura_de_categorias", {"competencia": "2026-07"})
    assert cobertura["percentual"] == "100.0"

    comparacao = _chamar("comparar_com_meses_anteriores", {"competencia": "2026-07", "meses": 3})
    assert (comparacao["total_atual"], comparacao["total_anterior"]) == ("500.50", "200.00")
    assert comparacao["diferenca"] == "300.50"

    assert _chamar("status_do_orcamento", {"competencia": "2026-07"})["tem_orcamento"] is False
    assert "linhas" in _chamar("gastos_fora_do_padrao", {"competencia": "2026-07"})
    assert "linhas" in _chamar("assinaturas_reajustadas", {"competencia": "2026-07"})


def test_listar_cadastros(cenario: dict[str, int]) -> None:
    r = _chamar("listar_cadastros")
    assert {p["id"] for p in r["pessoas"]} >= {cenario["pessoa_a"], cenario["pessoa_b"]}
    assert {"Conta Corrente", "Poupança"} <= {c["nome"] for c in r["contas"]}
    caminhos = {c["caminho"] for c in r["categorias"]}
    assert "Alimentação › Mercado" in caminhos and "Alimentação" in caminhos
    assert r["formas_pagamento"], "o seed cria formas de pagamento"


def test_totalizar_separa_transferencia(cenario: dict[str, int]) -> None:
    r = _chamar("totalizar_transacoes", {"competencia": "2026-07"})
    assert (r["despesas"], r["receitas"], r["saldo"]) == ("500.50", "5000.00", "4499.50")
    assert (r["transferencias"], r["quantidade_transferencias"]) == ("1000.00", 1)
    assert r["quantidade_despesas"] == 3


@pytest.mark.parametrize(
    ("filtro", "despesas"),
    [
        ({"categoria_id": "alimentacao", "competencia": "2026-07"}, "380.00"),  # raiz + filhas
        ({"categoria_id": "mercado"}, "500.00"),  # junho e julho
        ({"pessoa_id": "pessoa_b"}, "120.50"),
        ({"so_conjunto": True, "competencia": "2026-07"}, "80.00"),
        ({"texto": "MERCADO"}, "500.00"),
        ({"valor_min": "100", "valor_max": "300"}, "620.50"),
        ({"data_inicio": "2026-07-10", "data_fim": "2026-07-31"}, "200.50"),
    ],
)
def test_totalizar_com_filtros(
    cenario: dict[str, int], filtro: dict[str, Any], despesas: str
) -> None:
    argumentos = {k: (cenario[v] if k.endswith("_id") else v) for k, v in filtro.items()}
    assert _chamar("totalizar_transacoes", argumentos)["despesas"] == despesas


def test_buscar_transacoes(cenario: dict[str, int]) -> None:
    r = _chamar("buscar_transacoes", {"competencia": "2026-07"})
    descricoes = [t["descricao"] for t in r["transacoes"]]
    assert "Lançamento apagado" not in descricoes
    assert descricoes[0] == "Padaria do bairro", "mais recente primeiro"
    assert r["total_encontrado"] == 5 and r["ha_mais"] is False
    padaria = r["transacoes"][0]
    assert padaria["pessoa"] == "Conjunto"
    assert padaria["categoria"] == "Alimentação"
    # Dinheiro como texto decimal, nunca número (regra 1).
    assert all(isinstance(t["valor"], str) for t in r["transacoes"])
    assert Decimal(padaria["valor"]) == Decimal("80.00")

    so_transferencia = _chamar("buscar_transacoes", {"tipo": "transferencia"})
    assert [t["descricao"] for t in so_transferencia["transacoes"]] == ["Aplicação na poupança"]

    na_conta = _chamar("buscar_transacoes", {"conta_id": cenario["poupanca"]})
    assert [t["descricao"] for t in na_conta["transacoes"]] == ["Aplicação na poupança"]


# --- 3. limite ----------------------------------------------------------------------


def test_limite_e_paginacao(cenario: dict[str, int]) -> None:
    primeira = _chamar("buscar_transacoes", {"limite": 2})
    assert primeira["retornadas"] == 2 and primeira["total_encontrado"] == 6
    assert primeira["ha_mais"] is True and primeira["proximo_offset"] == 2

    ultima = _chamar("buscar_transacoes", {"limite": 2, "offset": 4})
    assert ultima["retornadas"] == 2 and ultima["ha_mais"] is False
    assert ultima["proximo_offset"] is None


def test_limite_acima_do_maximo_e_recusado(cenario: dict[str, int]) -> None:
    mensagem = _erro("buscar_transacoes", {"limite": LIMITE_MAXIMO + 1})
    assert "limite" in mensagem.lower()


def test_mes_invalido_volta_mensagem_para_o_modelo() -> None:
    assert "AAAA-MM" in _erro("resumo_do_mes", {"competencia": "07/2026"})


# --- relatório ------------------------------------------------------------------------


def test_ler_relatorio_do_mes(session: Session) -> None:
    vazio = _chamar("ler_relatorio_do_mes", {"competencia": "2026-07"})
    assert vazio["encontrado"] is False
    assert "make relatorio m=2026-07" in vazio["aviso"]

    from datetime import date

    session.add(
        Relatorio(
            competencia=date(2026, 7, 1),
            conteudo="# Julho\n\nTexto.",
            dados_base={},
            prompt_versao="deterministico_v1",
        )
    )
    session.commit()
    lido = _chamar("ler_relatorio_do_mes", {"competencia": "2026-07"})
    assert lido["encontrado"] is True
    assert lido["relatorio"]["conteudo"] == "# Julho\n\nTexto."
    assert lido["relatorio"]["com_ia"] is False


# --- 4. stdio: só protocolo na stdout ------------------------------------------------------


def _mensagem(**campos: Any) -> bytes:
    return (json.dumps({"jsonrpc": "2.0", **campos}) + "\n").encode()


def test_stdout_so_tem_protocolo(cenario: dict[str, int]) -> None:
    """Roda `python -m app.mcp` e confere cada linha da stdout.

    Inclui uma chamada que falha (mês inválido) e uma que funciona: erro de
    tool gera log, e log na stdout corromperia a conversa.
    """
    entrada = b"".join(
        [
            _mensagem(
                id=1,
                method="initialize",
                params={
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "teste", "version": "0"},
                },
            ),
            _mensagem(method="notifications/initialized"),
            _mensagem(id=2, method="tools/list"),
            _mensagem(
                id=3,
                method="tools/call",
                params={"name": "resumo_do_mes", "arguments": {"competencia": "07/2026"}},
            ),
            _mensagem(
                id=4,
                method="tools/call",
                params={"name": "totalizar_transacoes", "arguments": {"competencia": "2026-07"}},
            ),
        ]
    )
    processo = subprocess.Popen(
        [sys.executable, "-m", "app.mcp"],
        cwd=API,
        env=dict(os.environ),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    respostas: dict[int, dict[str, Any]] = {}
    try:
        assert processo.stdin is not None and processo.stdout is not None
        processo.stdin.write(entrada)
        processo.stdin.flush()
        while len(respostas) < 4:
            linha = processo.stdout.readline()
            assert linha, "o servidor fechou a stdout antes de responder"
            mensagem = json.loads(linha)  # quebra se houver qualquer coisa que não JSON
            assert mensagem.get("jsonrpc") == "2.0", linha
            if "id" in mensagem:
                respostas[mensagem["id"]] = mensagem
        processo.stdin.close()
        resto = processo.stdout.read()
        processo.wait(timeout=30)
    finally:
        if processo.poll() is None:
            processo.kill()

    for linha in resto.splitlines():
        if linha.strip():
            assert json.loads(linha).get("jsonrpc") == "2.0", linha

    assert {t["name"] for t in respostas[2]["result"]["tools"]} == TOOLS
    assert respostas[3]["result"]["isError"] is True
    assert respostas[4]["result"]["structuredContent"]["despesas"] == "500.50"


def test_cliente_stdio_de_ponta_a_ponta(cenario: dict[str, int]) -> None:
    """O mesmo caminho do Claude Desktop: um processo, falando por stdio."""
    parametros = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp"], cwd=str(API), env=dict(os.environ)
    )

    async def principal() -> dict[str, Any]:
        async with Client(parametros) as c:
            r = await c.call_tool("resumo_do_mes", {"competencia": "2026-07"})
            assert not r.is_error and r.structured_content is not None
            return r.structured_content

    assert anyio.run(principal)["despesas"] == "500.50"
