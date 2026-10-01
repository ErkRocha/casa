"""Diagnóstico da Pluggy: amostras brutas, relatório e comparação entre execuções."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.pluggy import PluggyCliente
from scripts import pluggy_diagnostico as diag

SEGREDO = "segredo-de-teste-NAO-PODE-VAZAR"
SENSIVEIS = ("Fulano de Tal", "123.456.789-00", "MERCADO DO BAIRRO", "0001-2")


def _conta(id_: str, tipo: str, subtipo: str) -> dict[str, Any]:
    return {
        "id": id_,
        "itemId": "item-1",
        "type": tipo,
        "subtype": subtipo,
        "name": "Conta do Fulano",
        "number": "0001-2",
        "owner": "Fulano de Tal",
        "taxNumber": "123.456.789-00",
        "balance": 1000.50,
    }


def _t(id_: str, conta: str, status: str, valor: str, dia: str, bill: str | None = None) -> str:
    """Transação em JSON *texto*, para o valor chegar como número cru."""
    meta = f', "creditCardMetadata": {{"billId": "{bill}"}}' if bill else ""
    return (
        f'{{"id": "{id_}", "accountId": "{conta}", "status": "{status}", "amount": {valor},'
        f' "date": "{dia}T12:00:00.000Z", "description": "MERCADO DO BAIRRO"{meta}}}'
    )


def _servidor(transacoes_por_conta: dict[str, list[str]]) -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        caminho = request.url.path
        if caminho == "/auth":
            return httpx.Response(200, json={"apiKey": "chave-secreta-da-sessao"})
        if caminho == "/items/item-1":
            return httpx.Response(
                200,
                json={
                    "id": "item-1",
                    "status": "UPDATED",
                    "connector": {"id": 200, "name": "MeuPluggy", "isOpenFinance": False},
                },
            )
        if caminho == "/accounts":
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total": 2,
                    "totalPages": 1,
                    "results": [
                        _conta("conta-banco", "BANK", "CHECKING_ACCOUNT"),
                        _conta("conta-cartao", "CREDIT", "CREDIT_CARD"),
                    ],
                },
            )
        if caminho == "/v2/transactions":
            itens = transacoes_por_conta.get(request.url.params["accountId"], [])
            corpo = '{"results": [' + ", ".join(itens) + '], "next": null}'
            return httpx.Response(200, content=corpo.encode())
        if caminho == "/bills":
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "total": 1,
                    "totalPages": 1,
                    "results": [{"id": "fatura-1", "dueDate": "2026-09-20", "totalAmount": 80}],
                },
            )
        raise AssertionError(f"rota inesperada: {caminho}")

    return httpx.MockTransport(responder)


def _rodar(pasta: Path, hoje: date, transacoes: dict[str, list[str]]) -> diag.Relatorio:
    gravador = diag.Gravador(pasta)
    with PluggyCliente(
        "id-de-teste", SEGREDO, transport=_servidor(transacoes), ao_responder=gravador
    ) as cliente:
        return diag.executar(cliente, ["item-1"], pasta, hoje)


PRIMEIRA = {
    "conta-banco": [_t("b1", "conta-banco", "POSTED", "12.34", "2026-09-10")],
    "conta-cartao": [
        _t("c1", "conta-cartao", "POSTED", "80.00", "2026-09-05", bill="fatura-1"),
        _t("c2", "conta-cartao", "POSTED", "10.00", "2026-09-06"),
        _t("p1", "conta-cartao", "PENDING", "50.00", "2026-09-25"),
        _t("p2", "conta-cartao", "PENDING", "30.00", "2026-08-03"),
        _t("p3", "conta-cartao", "PENDING", "70.00", "2026-09-26"),
        _t("p4", "conta-cartao", "PENDING", "15.00", "2026-09-27"),
    ],
}

SEGUNDA = {
    "conta-banco": [_t("b1", "conta-banco", "POSTED", "12.34", "2026-09-10")],
    "conta-cartao": [
        _t("c1", "conta-cartao", "POSTED", "80.00", "2026-09-05", bill="fatura-1"),
        _t("c2", "conta-cartao", "POSTED", "10.00", "2026-09-06"),
        # p1 consolidou com o mesmo id.
        _t("p1", "conta-cartao", "POSTED", "50.00", "2026-09-25", bill="fatura-2"),
        # p2 é de agosto: saiu da janela de 60 dias da segunda execução.
        # p3 sumiu, e apareceu uma POSTED nova com mesma conta e valor.
        _t("novo", "conta-cartao", "POSTED", "70.00", "2026-09-26", bill="fatura-2"),
        _t("p4", "conta-cartao", "PENDING", "15.00", "2026-09-27"),
    ],
}


def test_primeira_execucao_grava_bruto_e_responde_a_b_c(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pasta = tmp_path / "20261001_100000"
    relatorio = _rodar(pasta, date(2026, 10, 1), PRIMEIRA)

    # Bruto: cada resposta como veio, e o índice dizendo o que é cada uma.
    indice = json.loads((pasta / "indice.json").read_text("utf-8"))
    assert [e["caminho"] for e in indice] == [
        "/items/item-1",
        "/accounts",
        "/v2/transactions",
        "/v2/transactions",
        "/bills",
    ]
    arquivo_cartao = pasta / indice[3]["arquivo"]
    assert b'"amount": 80.00' in arquivo_cartao.read_bytes()

    # O /auth nunca é gravado: a resposta dele é a chave.
    for arquivo in pasta.iterdir():
        conteudo = arquivo.read_text("utf-8")
        assert "chave-secreta-da-sessao" not in conteudo
        assert SEGREDO not in conteudo

    assert relatorio.contas == [
        ("conta-banco", "BANK", "CHECKING_ACCOUNT"),
        ("conta-cartao", "CREDIT", "CREDIT_CARD"),
    ]
    assert (relatorio.cartao_postadas, relatorio.cartao_postadas_com_bill) == (2, 1)
    assert relatorio.bills_citados == {"fatura-1"}
    assert relatorio.bills_listados == {"fatura-1"}
    assert relatorio.anterior is None

    diag.imprimir(relatorio)
    saida = capsys.readouterr().out
    assert "BANK/CHECKING_ACCOUNT: 1" in saida
    assert "1 de 2 trazem billId" in saida
    assert "transações PENDING: 4" in saida
    assert "p1  conta conta-cartao" in saida
    assert "primeira execução" in saida


def test_segunda_execucao_compara_pendentes_com_a_anterior(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _rodar(tmp_path / "20261001_100000", date(2026, 10, 1), PRIMEIRA)
    relatorio = _rodar(tmp_path / "20261010_100000", date(2026, 10, 10), SEGUNDA)

    assert relatorio.anterior == tmp_path / "20261001_100000"
    comp = relatorio.comparacao
    assert comp is not None
    assert comp.pendentes_antes == 4
    assert comp.mesmo_id_postada == ["p1"]
    assert comp.ainda_pendente == ["p4"]
    assert comp.fora_da_janela == ["p2"]
    assert comp.sumiram == ["p3"]
    assert comp.possiveis_trocas == [("p3", "novo")]

    diag.imprimir(relatorio)
    saida = capsys.readouterr().out
    assert "viraram POSTED com o mesmo id: 1" in saida
    assert "possível troca de id: p3 -> novo" in saida
    assert "id preservado em 1 de 2" in saida


def test_terminal_so_mostra_contagens_tipos_e_ids(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _rodar(tmp_path / "20261001_100000", date(2026, 10, 1), PRIMEIRA)
    diag.imprimir(_rodar(tmp_path / "20261010_100000", date(2026, 10, 10), SEGUNDA))
    saida = capsys.readouterr().out
    for sensivel in (*SENSIVEIS, "1000.50", "12.34", "chave-secreta-da-sessao", SEGREDO):
        assert sensivel not in saida, sensivel


def test_execucao_anterior_ignora_pasta_sem_transacoes(tmp_path: Path) -> None:
    _rodar(tmp_path / "20261001_100000", date(2026, 10, 1), PRIMEIRA)
    (tmp_path / "20261005_100000").mkdir()  # execução que caiu antes de ler
    atual = tmp_path / "20261010_100000"
    assert diag.execucao_anterior(tmp_path, atual) == tmp_path / "20261001_100000"


def test_sem_credenciais_sai_com_2_sem_falar_com_a_pluggy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for nome in ("PLUGGY_CLIENT_ID", "PLUGGY_CLIENT_SECRET"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(diag, "ARQUIVO_ENV", tmp_path / "nao-existe.env")
    monkeypatch.setattr(diag, "PASTA_AMOSTRAS", tmp_path / "amostras")

    assert diag.main([]) == 2
    assert "PLUGGY_CLIENT_ID" in capsys.readouterr().err
    assert not (tmp_path / "amostras").exists()
