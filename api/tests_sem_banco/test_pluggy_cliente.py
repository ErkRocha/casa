"""Cliente HTTP da Pluggy (fase 5b, passo 3) — sem rede.

Tudo passa por `httpx.MockTransport`: o servidor falso abaixo responde como a
documentação da Pluggy descreve e registra cada requisição, para os testes
afirmarem o que o cliente mandou, e não só o que recebeu.
"""

from __future__ import annotations

import ast
import json
import traceback
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import pytest

from app.pluggy import (
    PluggyAutenticacaoErro,
    PluggyCliente,
    PluggyFormatoErro,
    PluggyLimiteErro,
    PluggyRedeErro,
    PluggyRespostaErro,
    RespostaBruta,
)
from app.pluggy.cliente import MARGEM_RENOVACAO, VALIDADE_API_KEY

SEGREDO = "segredo-de-teste-NAO-PODE-VAZAR"
CONTA = "562b795d-1653-429f-be86-74ead9502813"

Manipulador = Callable[[httpx.Request], httpx.Response]


class Servidor:
    """Pluggy falsa: `/auth` emite chaves numeradas; o resto é por rota."""

    def __init__(self) -> None:
        self.requisicoes: list[httpx.Request] = []
        self.chaves_emitidas: list[str] = []
        self.chaves_validas: set[str] = set()
        self.rotas: dict[str, Manipulador] = {}
        self.auth: Manipulador | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        if request.url.path == "/auth":
            if self.auth is not None:
                return self.auth(request)
            chave = f"chave-{len(self.chaves_emitidas) + 1}"
            self.chaves_emitidas.append(chave)
            self.chaves_validas.add(chave)
            return httpx.Response(200, json={"apiKey": chave})
        if request.headers.get("X-API-KEY") not in self.chaves_validas:
            return httpx.Response(401, json={"code": 401, "message": "Unauthorized"})
        return self.rotas[request.url.path](request)

    def de(self, caminho: str) -> list[httpx.Request]:
        return [r for r in self.requisicoes if r.url.path == caminho]


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def servidor() -> Servidor:
    return Servidor()


@pytest.fixture
def relogio() -> Relogio:
    return Relogio()


@pytest.fixture
def esperas() -> list[float]:
    return []


@pytest.fixture
def cliente(servidor: Servidor, relogio: Relogio, esperas: list[float]) -> PluggyCliente:
    return _cliente(servidor, relogio, esperas)


def _cliente(
    servidor: Servidor,
    relogio: Relogio | None = None,
    esperas: list[float] | None = None,
    **kwargs: Any,
) -> PluggyCliente:
    registro = esperas if esperas is not None else []
    return PluggyCliente(
        "id-de-teste",
        SEGREDO,
        transport=httpx.MockTransport(servidor),
        relogio=relogio or Relogio(),
        dormir=registro.append,
        **kwargs,
    )


def _json(corpo: str, status: int = 200, **headers: str) -> httpx.Response:
    """Resposta a partir de JSON *em texto*, para controlar o número exato."""
    return httpx.Response(
        status,
        content=corpo.encode(),
        headers={"Content-Type": "application/json", **headers},
    )


def _transacao(id_: str, **extra: Any) -> dict[str, Any]:
    """Valor inteiro: aqui importa a forma; precisão tem teste próprio, em texto."""
    return {
        "id": id_,
        "accountId": CONTA,
        "date": "2026-09-15T03:00:00.000Z",
        "description": "Compra",
        "amount": 10,
        "status": "POSTED",
        "type": "DEBIT",
        **extra,
    }


# --- autenticação -----------------------------------------------------------


def _rota_contas(servidor: Servidor) -> None:
    servidor.rotas["/accounts"] = lambda r: httpx.Response(
        200, json={"page": 1, "total": 0, "totalPages": 1, "results": []}
    )


def test_autentica_com_credencial_e_usa_a_chave_no_cabecalho(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    _rota_contas(servidor)
    cliente.listar_contas("item-1")

    (auth,) = servidor.de("/auth")
    assert auth.method == "POST"
    assert json.loads(auth.content) == {"clientId": "id-de-teste", "clientSecret": SEGREDO}
    (contas,) = servidor.de("/accounts")
    assert contas.headers["X-API-KEY"] == "chave-1"
    assert contas.url.params["itemId"] == "item-1"


def test_reutiliza_a_chave_enquanto_valida(
    cliente: PluggyCliente, servidor: Servidor, relogio: Relogio
) -> None:
    _rota_contas(servidor)
    cliente.listar_contas("item-1")
    relogio.agora += VALIDADE_API_KEY - MARGEM_RENOVACAO - 1
    cliente.listar_contas("item-1")
    assert len(servidor.de("/auth")) == 1


def test_renova_a_chave_quando_o_relogio_diz_que_expirou(
    cliente: PluggyCliente, servidor: Servidor, relogio: Relogio
) -> None:
    _rota_contas(servidor)
    cliente.listar_contas("item-1")
    relogio.agora += VALIDADE_API_KEY - MARGEM_RENOVACAO
    cliente.listar_contas("item-1")

    assert len(servidor.de("/auth")) == 2
    assert [r.headers["X-API-KEY"] for r in servidor.de("/accounts")] == ["chave-1", "chave-2"]


def test_renova_a_chave_quando_a_pluggy_responde_401(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    """Chave expirada antes do previsto: renova uma vez e repete a chamada."""
    _rota_contas(servidor)
    cliente.listar_contas("item-1")
    servidor.chaves_validas.clear()  # a Pluggy invalidou a chave-1

    cliente.listar_contas("item-1")

    assert len(servidor.de("/auth")) == 2
    assert [r.headers["X-API-KEY"] for r in servidor.de("/accounts")] == [
        "chave-1",
        "chave-1",
        "chave-2",
    ]


def test_401_depois_de_renovar_falha_sem_laco(servidor: Servidor, esperas: list[float]) -> None:
    servidor.rotas["/accounts"] = lambda r: httpx.Response(
        401, json={"code": 401, "codeDescription": "UNAUTHORIZED", "message": "nope"}
    )
    cliente = _cliente(servidor, esperas=esperas)

    with pytest.raises(PluggyAutenticacaoErro) as erro:
        cliente.listar_contas("item-1")

    assert erro.value.status == 401
    assert len(servidor.de("/auth")) == 2
    assert len(servidor.de("/accounts")) == 2
    assert esperas == []


def test_401_no_auth_falha_na_hora_sem_retry(servidor: Servidor, esperas: list[float]) -> None:
    servidor.auth = lambda r: httpx.Response(
        401,
        json={"code": 401, "codeDescription": "CLIENT_KEYS_UNAUTHORIZED", "message": "x"},
    )
    cliente = _cliente(servidor, esperas=esperas)

    with pytest.raises(PluggyAutenticacaoErro) as erro:
        cliente.listar_contas("item-1")

    assert erro.value.codigo == "CLIENT_KEYS_UNAUTHORIZED"
    assert len(servidor.requisicoes) == 1
    assert esperas == []


# --- paginação ----------------------------------------------------------------


def test_transacoes_percorrem_todas_as_paginas(cliente: PluggyCliente, servidor: Servidor) -> None:
    paginas = {
        None: ([_transacao("t1"), _transacao("t2")], "cursor/A=="),
        "cursor/A==": ([_transacao("t3")], "cursor/B=="),
        "cursor/B==": ([_transacao("t4")], None),
    }

    def rota(request: httpx.Request) -> httpx.Response:
        resultados, proximo = paginas[request.url.params.get("after")]
        # `next` como a Pluggy manda: query string pronta, cursor codificado.
        nxt = f"?accountId={CONTA}&after={quote(proximo, safe='')}" if proximo else None
        return httpx.Response(200, json={"results": resultados, "next": nxt})

    servidor.rotas["/v2/transactions"] = rota

    transacoes = cliente.listar_transacoes(CONTA, date(2026, 8, 1), date(2026, 9, 30))

    assert [t.id for t in transacoes] == ["t1", "t2", "t3", "t4"]
    pedidos = servidor.de("/v2/transactions")
    assert [p.url.params.get("after") for p in pedidos] == [None, "cursor/A==", "cursor/B=="]
    # O período vale em toda página, não só na primeira.
    for pedido in pedidos:
        assert pedido.url.params["accountId"] == CONTA
        assert pedido.url.params["dateFrom"] == "2026-08-01"
        assert pedido.url.params["dateTo"] == "2026-09-30"


def test_cursor_repetido_aborta_em_vez_de_girar_para_sempre(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    servidor.rotas["/v2/transactions"] = lambda r: httpx.Response(
        200, json={"results": [_transacao("t1")], "next": f"?accountId={CONTA}&after=SEMPRE"}
    )
    with pytest.raises(PluggyFormatoErro, match="cursor repetido"):
        cliente.listar_transacoes(CONTA, date(2026, 9, 1), date(2026, 9, 30))
    assert len(servidor.de("/v2/transactions")) == 2


def test_items_paginam_por_cursor(cliente: PluggyCliente, servidor: Servidor) -> None:
    def rota(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("after") is None:
            return httpx.Response(200, json={"results": [{"id": "item-1"}], "next": "?after=pag2"})
        return httpx.Response(200, json={"results": [{"id": "item-2"}], "next": None})

    servidor.rotas["/v2/items"] = rota
    assert [i.id for i in cliente.listar_items()] == ["item-1", "item-2"]


def test_listar_items_desligado_vira_erro_com_codigo(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    servidor.rotas["/v2/items"] = lambda r: httpx.Response(
        403,
        json={
            "code": 403,
            "codeDescription": "LIST_ITEMS_FEATURE_NOT_ENABLED",
            "message": "List items is not enabled",
        },
    )
    with pytest.raises(PluggyRespostaErro) as erro:
        cliente.listar_items()
    assert erro.value.codigo == "LIST_ITEMS_FEATURE_NOT_ENABLED"
    assert erro.value.status == 403


def test_faturas_percorrem_todas_as_paginas(cliente: PluggyCliente, servidor: Servidor) -> None:
    def rota(request: httpx.Request) -> httpx.Response:
        pagina = int(request.url.params["page"])
        fatura = {
            "id": f"fatura-{pagina}",
            "dueDate": "2026-09-20T00:00:00",
            "billClosingDate": "2026-09-13T00:00:00",
            "totalAmount": 100,
        }
        return httpx.Response(
            200, json={"page": pagina, "total": 2, "totalPages": 2, "results": [fatura]}
        )

    servidor.rotas["/bills"] = rota

    faturas = cliente.listar_faturas(CONTA)

    assert [f.id for f in faturas] == ["fatura-1", "fatura-2"]
    assert [p.url.params["pageSize"] for p in servidor.de("/bills")] == ["500", "500"]


# --- 429 ------------------------------------------------------------------------


def _depois_de(falhas: list[httpx.Response], sucesso: httpx.Response) -> Manipulador:
    fila = list(falhas)

    def rota(request: httpx.Request) -> httpx.Response:
        return fila.pop(0) if fila else sucesso

    return rota


_429 = {"code": 429, "message": "Too many requests"}
_OK_CONTAS = httpx.Response(200, json={"page": 1, "total": 0, "totalPages": 1, "results": []})


def test_429_espera_o_retry_after_e_tenta_de_novo(
    cliente: PluggyCliente, servidor: Servidor, esperas: list[float]
) -> None:
    servidor.rotas["/accounts"] = _depois_de(
        [httpx.Response(429, json=_429, headers={"Retry-After": "7"})], _OK_CONTAS
    )
    assert cliente.listar_contas("item-1") == []
    assert esperas == [7.0]
    assert len(servidor.de("/accounts")) == 2


def test_429_sem_retry_after_usa_ratelimit_reset(
    cliente: PluggyCliente, servidor: Servidor, esperas: list[float]
) -> None:
    servidor.rotas["/accounts"] = _depois_de(
        [httpx.Response(429, json=_429, headers={"RateLimit-Reset": "3"})], _OK_CONTAS
    )
    cliente.listar_contas("item-1")
    assert esperas == [3.0]


def test_429_sem_cabecalho_faz_backoff_exponencial(
    cliente: PluggyCliente, servidor: Servidor, esperas: list[float]
) -> None:
    servidor.rotas["/accounts"] = _depois_de([httpx.Response(429, json=_429)] * 3, _OK_CONTAS)
    cliente.listar_contas("item-1")
    assert esperas == [1.0, 2.0, 4.0]


def test_espera_nunca_passa_do_teto(servidor: Servidor, esperas: list[float]) -> None:
    servidor.rotas["/accounts"] = _depois_de(
        [httpx.Response(429, json=_429, headers={"Retry-After": "3600"})], _OK_CONTAS
    )
    _cliente(servidor, esperas=esperas, espera_maxima=60.0).listar_contas("item-1")
    assert esperas == [60.0]


def test_429_esgotando_tentativas_levanta_limite(servidor: Servidor, esperas: list[float]) -> None:
    servidor.rotas["/accounts"] = lambda r: httpx.Response(
        429, json=_429, headers={"Retry-After": "60"}
    )
    cliente = _cliente(servidor, esperas=esperas, max_tentativas=3)

    with pytest.raises(PluggyLimiteErro) as erro:
        cliente.listar_contas("item-1")

    assert erro.value.status == 429
    assert "3 tentativas" in str(erro.value)
    assert len(servidor.de("/accounts")) == 3
    assert esperas == [60.0, 60.0]  # espera entre tentativas, não depois da última


def test_429_no_auth_tambem_e_retentado(servidor: Servidor, esperas: list[float]) -> None:
    """Rate limit não é erro de credencial: no `/auth` ele também espera."""
    tentativas = {"n": 0}

    def auth(request: httpx.Request) -> httpx.Response:
        tentativas["n"] += 1
        if tentativas["n"] == 1:
            return httpx.Response(429, json=_429, headers={"Retry-After": "5"})
        servidor.chaves_validas.add("chave-x")
        return httpx.Response(200, json={"apiKey": "chave-x"})

    servidor.auth = auth
    _rota_contas(servidor)
    _cliente(servidor, esperas=esperas).listar_contas("item-1")
    assert esperas == [5.0]


def test_erro_5xx_nao_e_retentado(cliente: PluggyCliente, servidor: Servidor) -> None:
    servidor.rotas["/accounts"] = lambda r: httpx.Response(
        503, json={"code": 503, "message": "maintenance"}
    )
    with pytest.raises(PluggyRespostaErro) as erro:
        cliente.listar_contas("item-1")
    assert erro.value.status == 503
    assert len(servidor.de("/accounts")) == 1


# --- dinheiro -------------------------------------------------------------------


def test_valores_monetarios_chegam_como_decimal_exato(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    """Número JSON vira Decimal sem passar por float — nem dentro de campo livre.

    `0.1 + 0.2` em float dá `0.30000000000000004`; o último valor tem mais
    dígitos do que um float consegue guardar. Qualquer passagem por float no
    caminho quebraria uma das duas afirmações.
    """
    corpo = """{
      "results": [
        {"id": "a", "accountId": "c", "date": "2026-09-01T00:00:00Z", "amount": 0.1},
        {"id": "b", "accountId": "c", "date": "2026-09-01T00:00:00Z", "amount": 0.2,
         "balance": -1234567.89,
         "creditCardMetadata": {"totalAmount": 1499.90, "billId": "f1"},
         "paymentData": {"valorDentroDeCampoLivre": 19.99}},
        {"id": "c", "accountId": "c", "date": "2026-09-01T00:00:00Z",
         "amount": 0.12345678901234567890123}
      ],
      "next": null
    }"""
    servidor.rotas["/v2/transactions"] = lambda r: _json(corpo)

    a, b, c = cliente.listar_transacoes("c", date(2026, 9, 1), date(2026, 9, 30))

    assert isinstance(a.amount, Decimal)
    assert a.amount + b.amount == Decimal("0.3")
    assert b.balance == Decimal("-1234567.89")
    assert b.credit_card_metadata is not None
    assert b.credit_card_metadata.total_amount == Decimal("1499.90")
    assert b.payment_data == {"valorDentroDeCampoLivre": Decimal("19.99")}
    assert c.amount == Decimal("0.12345678901234567890123")


def test_contas_e_faturas_tambem_em_decimal(cliente: PluggyCliente, servidor: Servidor) -> None:
    servidor.rotas["/accounts"] = lambda r: _json(
        """{"page": 1, "total": 1, "totalPages": 1, "results": [
          {"id": "c1", "itemId": "i1", "type": "CREDIT", "subtype": "CREDIT_CARD",
           "balance": 2500.75,
           "creditData": {"creditLimit": 10000.00, "availableCreditLimit": 7499.25}}
        ]}"""
    )
    servidor.rotas["/bills"] = lambda r: _json(
        """{"page": 1, "total": 1, "totalPages": 1, "results": [
          {"id": "f1", "dueDate": "2026-09-20T00:00:00", "totalAmount": 2500.75,
           "minimumPaymentAmount": 375.11,
           "financeCharges": [{"type": "IOF", "amount": 1.03}]}
        ]}"""
    )

    (conta,) = cliente.listar_contas("i1")
    (fatura,) = cliente.listar_faturas("c1")

    assert conta.e_cartao
    assert conta.balance == Decimal("2500.75")
    assert conta.credit_data is not None
    assert conta.credit_data.available_credit_limit == Decimal("7499.25")
    assert fatura.total_amount == Decimal("2500.75")
    assert fatura.minimum_payment_amount == Decimal("375.11")
    assert fatura.finance_charges[0]["amount"] == Decimal("1.03")


def test_campo_desconhecido_nao_derruba_a_leitura(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    servidor.rotas["/v2/transactions"] = lambda r: httpx.Response(
        200,
        json={
            "results": [
                _transacao(
                    "t1",
                    campoQueAPluggyInventouOntem={"x": 1},
                    creditCardMetadata={"billId": "f1", "outroCampoNovo": True},
                )
            ],
            "next": None,
        },
    )
    (t,) = cliente.listar_transacoes(CONTA, date(2026, 9, 1), date(2026, 9, 30))
    assert t.model_extra == {"campoQueAPluggyInventouOntem": {"x": 1}}
    assert t.credit_card_metadata is not None
    assert t.credit_card_metadata.bill_id == "f1"


def test_resposta_fora_do_formato_vira_erro_de_formato(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    servidor.rotas["/v2/transactions"] = lambda r: httpx.Response(
        200, json={"results": [{"id": "sem-amount"}], "next": None}
    )
    with pytest.raises(PluggyFormatoErro):
        cliente.listar_transacoes(CONTA, date(2026, 9, 1), date(2026, 9, 30))


# --- segredo --------------------------------------------------------------------


def _tudo_sobre(erro: BaseException) -> str:
    """Tudo o que um log ou um traceback mostraria desta exceção."""
    return "\n".join([str(erro), repr(erro), "".join(traceback.format_exception(erro))])


def test_secret_e_chave_nao_aparecem_no_repr_do_cliente(
    cliente: PluggyCliente, servidor: Servidor
) -> None:
    _rota_contas(servidor)
    cliente.listar_contas("item-1")
    texto = repr(cliente)
    assert SEGREDO not in texto
    assert "chave-1" not in texto
    assert "id-de-teste" in texto


def test_secret_nao_vaza_quando_a_pluggy_ecoa_a_credencial(servidor: Servidor) -> None:
    """Mesmo que o servidor devolva o secret na mensagem de erro."""
    servidor.auth = lambda r: httpx.Response(
        401,
        json={
            "code": 401,
            "codeDescription": "CLIENT_KEYS_UNAUTHORIZED",
            "message": f"credencial recebida: {json.loads(r.content)}",
        },
    )
    with pytest.raises(PluggyAutenticacaoErro) as erro:
        _cliente(servidor).listar_contas("item-1")

    assert SEGREDO not in _tudo_sobre(erro.value)
    assert "***" in str(erro.value)


def test_chave_nao_vaza_quando_a_pluggy_a_ecoa(servidor: Servidor) -> None:
    servidor.rotas["/accounts"] = lambda r: httpx.Response(
        400, json={"code": 400, "message": f"chave {r.headers['X-API-KEY']} sem acesso"}
    )
    with pytest.raises(PluggyRespostaErro) as erro:
        _cliente(servidor).listar_contas("item-1")
    assert "chave-1" not in _tudo_sobre(erro.value)


def test_erro_de_rede_nao_carrega_a_requisicao(servidor: Servidor) -> None:
    """A exceção do httpx guarda a requisição — e o corpo do /auth tem o secret."""

    def cai(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"sem rede; corpo era {request.content!r}", request=request)

    cliente = PluggyCliente(
        "id-de-teste", SEGREDO, transport=httpx.MockTransport(cai), dormir=lambda s: None
    )
    with pytest.raises(PluggyRedeErro) as erro:
        cliente.autenticar()

    assert erro.value.__cause__ is None
    assert erro.value.__suppress_context__
    assert SEGREDO not in _tudo_sobre(erro.value)


def test_construtor_sem_credencial_falha_sem_ecoar_nada() -> None:
    with pytest.raises(ValueError) as erro:
        PluggyCliente("id-de-teste", "")
    assert "obrigatórios" in str(erro.value)


# --- forma do cliente -----------------------------------------------------------


def test_timeout_e_explicito() -> None:
    cliente = PluggyCliente("id", SEGREDO, transport=httpx.MockTransport(Servidor()))
    assert cliente.timeout.read == 30.0
    assert cliente.timeout.connect == 10.0


def test_ao_responder_recebe_o_corpo_bruto_e_nunca_o_auth(
    servidor: Servidor, relogio: Relogio
) -> None:
    corpo = '{"page": 1, "total": 0, "totalPages": 1, "results": []}'
    servidor.rotas["/accounts"] = lambda r: _json(corpo)
    recebidas: list[RespostaBruta] = []
    cliente = _cliente(servidor, relogio, ao_responder=recebidas.append)

    cliente.listar_contas("item-1")

    assert [(r.metodo, r.caminho) for r in recebidas] == [("GET", "/accounts")]
    assert recebidas[0].conteudo == corpo.encode()
    assert recebidas[0].params == {"itemId": "item-1"}


def test_so_le_nenhuma_escrita_alem_do_auth(cliente: PluggyCliente, servidor: Servidor) -> None:
    """D-16: a sync só lê. O único POST permitido é o `/auth`."""
    _rota_contas(servidor)
    servidor.rotas["/items/item-1"] = lambda r: httpx.Response(200, json={"id": "item-1"})
    servidor.rotas["/v2/transactions"] = lambda r: httpx.Response(
        200, json={"results": [], "next": None}
    )
    servidor.rotas["/bills"] = lambda r: httpx.Response(
        200, json={"page": 1, "total": 0, "totalPages": 1, "results": []}
    )

    cliente.obter_item("item-1")
    cliente.listar_contas("item-1")
    cliente.listar_transacoes(CONTA, date(2026, 9, 1), date(2026, 9, 30))
    cliente.listar_faturas(CONTA)

    for pedido in servidor.requisicoes:
        assert pedido.method == ("POST" if pedido.url.path == "/auth" else "GET")

    fonte = (Path(__file__).parents[1] / "app" / "pluggy" / "cliente.py").read_text("utf-8")
    for verbo in ('"PATCH"', '"PUT"', '"DELETE"', ".patch(", ".put(", ".delete("):
        assert verbo not in fonte


def test_pacote_nao_importa_banco_models_services_nem_config() -> None:
    """Decisão de arquitetura: o cliente pode sair para outro serviço sem reescrita."""
    pacote = Path(__file__).parents[1] / "app" / "pluggy"
    proibidos_externos = ("sqlalchemy", "psycopg", "alembic", "fastapi")
    for arquivo in pacote.glob("*.py"):
        arvore = ast.parse(arquivo.read_text("utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                modulos = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom):
                modulos = [no.module or ""]
            else:
                continue
            for modulo in modulos:
                if modulo == "app" or modulo.startswith("app."):
                    assert modulo.startswith("app.pluggy"), f"{arquivo.name} importa {modulo}"
                assert not modulo.startswith(proibidos_externos), f"{arquivo.name} importa {modulo}"
