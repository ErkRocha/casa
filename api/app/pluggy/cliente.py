"""Cliente HTTP da Pluggy — somente leitura.

Fala com quatro recursos da API: items, contas, transações e faturas. Não
existe aqui `PATCH /items` nem qualquer outra escrita: a Pluggy já atualiza os
dados sozinha a cada 24h (D-16), e o cliente só lê. O único `POST` é o
`/auth`, que troca credencial por `apiKey`.

**Autenticação.** A `apiKey` vale 2h. O cliente a reutiliza e renova de dois
jeitos:

* por relógio: passadas 1h50 desde a emissão, a próxima chamada autentica de
  novo antes de sair;
* por resposta: se um GET voltar 401 mesmo assim (relógio do servidor, chave
  revogada), o cliente descarta a chave, autentica uma vez e repete a mesma
  chamada uma vez. Um segundo 401 é erro de credencial e sobe na hora.

Um 401 no próprio `/auth` é credencial errada e sobe imediatamente, sem
retentativa — repetir não muda a resposta e só gasta rate limit.

**429.** Espera e tenta de novo, até `max_tentativas` no total. A espera vem
do `Retry-After` (a Pluggy manda sempre 60), senão do `RateLimit-Reset`,
senão de backoff exponencial (1s, 2s, 4s...), e nunca passa de
`espera_maxima`. Esgotou, levanta `PluggyLimiteErro`.

Erro 5xx e de rede não são retentados aqui: a sync roda uma vez por dia, e a
execução seguinte é a retentativa natural. Esconder instabilidade atrás de
retry silencioso tornaria a falha mais difícil de ver.

**Isolamento.** Este pacote não importa nada de banco, models, services nem
config. Recebe credencial no construtor e devolve objetos tipados — pode ser
movido para um serviço separado sem reescrita.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, TypeVar
from urllib.parse import parse_qs, quote, urlsplit

import httpx
from pydantic import BaseModel, SecretStr, ValidationError

from app.pluggy.erros import (
    PluggyAutenticacaoErro,
    PluggyErro,
    PluggyFormatoErro,
    PluggyLimiteErro,
    PluggyRedeErro,
    PluggyRespostaErro,
)
from app.pluggy.modelos import Conta, Fatura, Item, Transacao

log = logging.getLogger(__name__)

URL_PADRAO = "https://api.pluggy.ai"

#: Explícito: o padrão do httpx é 5s para tudo, curto para uma página de 500
#: transações e longo demais para descobrir que não há rede.
TIMEOUT_PADRAO = httpx.Timeout(30.0, connect=10.0)

#: A `apiKey` vale 2h (documentação de autenticação da Pluggy). Renova com
#: folga, para não descobrir a expiração no meio de uma paginação.
VALIDADE_API_KEY = 2 * 60 * 60
MARGEM_RENOVACAO = 10 * 60

#: Tamanho de página documentado para faturas (e o máximo das transações).
TAMANHO_PAGINA = 500

_M = TypeVar("_M", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class RespostaBruta:
    """O corpo exato de uma resposta de leitura, antes de qualquer parse.

    Entregue a `ao_responder` — é o que o diagnóstico grava em disco. Nunca é
    emitida para o `/auth`, cuja resposta contém a `apiKey`.
    """

    metodo: str
    caminho: str
    params: dict[str, str]
    status: int
    conteudo: bytes = field(repr=False)


class PluggyCliente:
    def __init__(
        self,
        client_id: str,
        client_secret: SecretStr | str,
        *,
        base_url: str = URL_PADRAO,
        timeout: httpx.Timeout = TIMEOUT_PADRAO,
        max_tentativas: int = 4,
        espera_maxima: float = 120.0,
        transport: httpx.BaseTransport | None = None,
        relogio: Callable[[], float] = time.monotonic,
        dormir: Callable[[float], None] = time.sleep,
        ao_responder: Callable[[RespostaBruta], None] | None = None,
    ) -> None:
        segredo = (
            client_secret if isinstance(client_secret, SecretStr) else SecretStr(client_secret)
        )
        if not client_id or not segredo.get_secret_value():
            raise ValueError("client_id e client_secret da Pluggy são obrigatórios.")
        if max_tentativas < 1:
            raise ValueError("max_tentativas precisa ser ao menos 1.")

        self._client_id = client_id
        self._client_secret = segredo
        self._max_tentativas = max_tentativas
        self._espera_maxima = espera_maxima
        self._relogio = relogio
        self._dormir = dormir
        self._ao_responder = ao_responder

        self._api_key: SecretStr | None = None
        self._api_key_emitida_em = 0.0

        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def __repr__(self) -> str:
        # Escrito à mão: o repr padrão listaria atributos, e um deles é
        # segredo.
        base_url = str(self._http.base_url)
        return f"PluggyCliente(client_id={self._client_id!r}, base_url={base_url!r})"

    @property
    def timeout(self) -> httpx.Timeout:
        return self._http.timeout

    def fechar(self) -> None:
        self._http.close()

    def __enter__(self) -> PluggyCliente:
        return self

    def __exit__(self, *_: object) -> None:
        self.fechar()

    # -- autenticação --------------------------------------------------------

    def autenticar(self) -> None:
        """Troca a credencial por uma `apiKey` nova."""
        resposta = self._enviar(
            "POST",
            "/auth",
            json={
                "clientId": self._client_id,
                "clientSecret": self._client_secret.get_secret_value(),
            },
        )
        if resposta.status_code in (401, 403):
            raise self._erro(resposta, "POST /auth", PluggyAutenticacaoErro)
        if resposta.is_error:
            raise self._erro(resposta, "POST /auth", PluggyRespostaErro)

        # Parse à mão, sem Pydantic: um ValidationError reproduziria a
        # resposta inteira na mensagem — e a resposta é a chave.
        try:
            api_key = json.loads(resposta.content).get("apiKey")
        except (ValueError, AttributeError):
            api_key = None
        if not isinstance(api_key, str) or not api_key:
            raise PluggyFormatoErro("Resposta de POST /auth sem `apiKey`.")

        self._api_key = SecretStr(api_key)
        self._api_key_emitida_em = self._relogio()
        log.info("pluggy: apiKey emitida")

    def _chave_vigente(self) -> str:
        idade = self._relogio() - self._api_key_emitida_em
        if self._api_key is None or idade >= VALIDADE_API_KEY - MARGEM_RENOVACAO:
            self.autenticar()
        assert self._api_key is not None
        return self._api_key.get_secret_value()

    # -- leitura -------------------------------------------------------------

    def listar_items(self) -> list[Item]:
        """`GET /v2/items`, todas as páginas.

        Recurso opt-in da Pluggy: desligado, responde 403 com
        `LIST_ITEMS_FEATURE_NOT_ENABLED` (vira `PluggyRespostaErro` com esse
        `codigo`). Sem ele, o id do item vem de quem criou a conexão.
        """
        return list(self._paginar_cursor("/v2/items", {}, Item))

    def obter_item(self, item_id: str) -> Item:
        """`GET /items/{id}`."""
        dados = self._get(f"/items/{quote(item_id, safe='')}", {})
        return self._validar(Item, dados, "GET /items/{id}")

    def listar_contas(self, item_id: str, tipo: str | None = None) -> list[Conta]:
        """`GET /accounts?itemId=` — `tipo` é `BANK` ou `CREDIT`.

        A documentação não descreve parâmetro de página para contas: um item
        tem poucas, e vêm todas em `results`.
        """
        params = {"itemId": item_id}
        if tipo is not None:
            params["type"] = tipo
        dados = self._get("/accounts", params)
        resultados = self._results(dados, "/accounts")
        return [self._validar(Conta, bruto, "GET /accounts") for bruto in resultados]

    def iterar_transacoes(self, account_id: str, desde: date, ate: date) -> Iterator[Transacao]:
        """`GET /v2/transactions` de uma conta, `desde` e `ate` inclusivos.

        Página a página (500 por vez), sem acumular tudo em memória.
        """
        params = {
            "accountId": account_id,
            "dateFrom": desde.isoformat(),
            "dateTo": ate.isoformat(),
        }
        return self._paginar_cursor("/v2/transactions", params, Transacao)

    def listar_transacoes(self, account_id: str, desde: date, ate: date) -> list[Transacao]:
        return list(self.iterar_transacoes(account_id, desde, ate))

    def listar_faturas(self, account_id: str) -> list[Fatura]:
        """`GET /bills` de uma conta de cartão, todas as páginas."""
        faturas: list[Fatura] = []
        pagina = 1
        while True:
            params = {
                "accountId": account_id,
                "pageSize": str(TAMANHO_PAGINA),
                "page": str(pagina),
            }
            dados = self._get("/bills", params)
            resultados = self._results(dados, "/bills")
            faturas.extend(self._validar(Fatura, bruto, "GET /bills") for bruto in resultados)

            total_paginas = dados.get("totalPages")
            if not resultados or not isinstance(total_paginas, int) or pagina >= total_paginas:
                return faturas
            pagina += 1

    # -- paginação -------------------------------------------------------------

    def _paginar_cursor(
        self, caminho: str, params: dict[str, str], modelo: type[_M]
    ) -> Iterator[_M]:
        """Paginação por cursor dos endpoints `/v2`.

        A resposta traz `next` como query string pronta. Em vez de colá-la na
        URL, o cliente extrai o `after` dela e reenvia junto dos próprios
        filtros — o caminho que a documentação descreve para quem monta a
        requisição. Assim o período pedido vale em toda página, sem depender
        de o cursor carregá-lo.
        """
        vistos: set[str] = set()
        atual = dict(params)
        while True:
            dados = self._get(caminho, atual)
            for bruto in self._results(dados, caminho):
                yield self._validar(modelo, bruto, f"GET {caminho}")

            proximo = dados.get("next")
            if not proximo:
                return
            cursor = self._cursor(proximo, caminho)
            # Cursor repetido é laço infinito, não página nova.
            if cursor in vistos:
                raise PluggyFormatoErro(f"GET {caminho}: cursor repetido na paginação.")
            vistos.add(cursor)
            atual = {**params, "after": cursor}

    @staticmethod
    def _cursor(proximo: object, caminho: str) -> str:
        if not isinstance(proximo, str):
            raise PluggyFormatoErro(f"GET {caminho}: `next` não é texto.")
        query = urlsplit(proximo).query or proximo.lstrip("?")
        # `parse_qs` já devolve o valor decodificado, como a documentação pede.
        valores = parse_qs(query).get("after")
        if not valores or not valores[0]:
            raise PluggyFormatoErro(f"GET {caminho}: `next` sem `after`.")
        return valores[0]

    @staticmethod
    def _results(dados: dict[str, Any], caminho: str) -> list[Any]:
        resultados = dados.get("results")
        if not isinstance(resultados, list):
            raise PluggyFormatoErro(f"GET {caminho}: resposta sem lista `results`.")
        return resultados

    @staticmethod
    def _validar(modelo: type[_M], bruto: Any, endpoint: str) -> _M:
        try:
            return modelo.model_validate(bruto)
        except ValidationError as exc:
            # Encadeado de propósito: aqui o conteúdo é dado da Pluggy, não
            # credencial, e o detalhe do Pydantic é o que permite consertar.
            raise PluggyFormatoErro(f"{endpoint}: resposta fora do formato esperado.") from exc

    # -- HTTP --------------------------------------------------------------------

    def _get(self, caminho: str, params: dict[str, str]) -> dict[str, Any]:
        """GET autenticado, com renovação da chave num 401."""
        endpoint = f"GET {caminho}"
        renovou = False
        while True:
            chave = self._chave_vigente()
            resposta = self._enviar("GET", caminho, params=params, headers={"X-API-KEY": chave})
            if resposta.status_code == 401 and not renovou:
                log.info("pluggy: 401 em %s; renovando a apiKey e repetindo uma vez", endpoint)
                self._api_key = None
                renovou = True
                continue
            break

        if resposta.status_code == 401:
            raise self._erro(resposta, endpoint, PluggyAutenticacaoErro)
        if resposta.is_error:
            raise self._erro(resposta, endpoint, PluggyRespostaErro)

        dados = self._decodificar(resposta.content, endpoint)
        if self._ao_responder is not None:
            self._ao_responder(
                RespostaBruta("GET", caminho, dict(params), resposta.status_code, resposta.content)
            )
        return dados

    def _enviar(self, metodo: str, caminho: str, **kwargs: Any) -> httpx.Response:
        """Uma requisição, com as retentativas de 429 e nada mais."""
        endpoint = f"{metodo} {caminho}"
        for tentativa in range(1, self._max_tentativas + 1):
            try:
                resposta = self._http.request(metodo, caminho, **kwargs)
            except httpx.TimeoutException:
                # `from None`: a exceção do httpx carrega a requisição, e a
                # requisição carrega a credencial (corpo do /auth, cabeçalho
                # X-API-KEY). Encadeada, ela apareceria em todo traceback.
                raise PluggyRedeErro(f"{endpoint}: tempo esgotado.") from None
            except httpx.TransportError as exc:
                raise PluggyRedeErro(f"{endpoint}: falha de rede ({type(exc).__name__}).") from None

            if resposta.status_code != 429:
                return resposta
            if tentativa == self._max_tentativas:
                break

            espera = self._espera(resposta, tentativa)
            log.warning(
                "pluggy: 429 em %s; tentativa %d de %d, esperando %.1fs",
                endpoint,
                tentativa,
                self._max_tentativas,
                espera,
            )
            self._dormir(espera)

        sufixo = f" ({self._max_tentativas} tentativas)"
        raise self._erro(resposta, endpoint, PluggyLimiteErro, sufixo)

    def _espera(self, resposta: httpx.Response, tentativa: int) -> float:
        espera = _segundos_do_cabecalho(resposta.headers.get("Retry-After"))
        if espera is None:
            espera = _segundos_do_cabecalho(resposta.headers.get("RateLimit-Reset"))
        if espera is None:
            espera = float(2 ** (tentativa - 1))
        return min(max(espera, 0.0), self._espera_maxima)

    @staticmethod
    def _decodificar(conteudo: bytes, endpoint: str) -> dict[str, Any]:
        try:
            # `parse_float=Decimal`: número com casa decimal nunca vira float
            # (regra 1). Ver o docstring de `modelos`.
            dados = json.loads(conteudo, parse_float=Decimal)
        except ValueError as exc:
            raise PluggyFormatoErro(f"{endpoint}: resposta não é JSON.") from exc
        if not isinstance(dados, dict):
            raise PluggyFormatoErro(f"{endpoint}: resposta não é um objeto JSON.")
        return dados

    # -- erros -------------------------------------------------------------------

    def _erro(
        self,
        resposta: httpx.Response,
        endpoint: str,
        classe: type[PluggyRespostaErro],
        sufixo: str = "",
    ) -> PluggyRespostaErro:
        codigo: str | None = None
        detalhe = ""
        try:
            corpo = json.loads(resposta.content)
        except ValueError:
            corpo = None
        if isinstance(corpo, dict):
            if isinstance(corpo.get("codeDescription"), str):
                codigo = corpo["codeDescription"]
            if isinstance(corpo.get("message"), str):
                detalhe = f": {corpo['message']}"

        partes = f"{endpoint} respondeu {resposta.status_code}"
        if codigo:
            partes += f" {codigo}"
        mensagem = self._sanitizar(partes + detalhe + sufixo)
        return classe(
            mensagem,
            status=resposta.status_code,
            endpoint=endpoint,
            codigo=self._sanitizar(codigo) if codigo else None,
        )

    def _sanitizar(self, texto: str) -> str:
        """Tira credencial de texto que veio de fora.

        A mensagem de erro é escrita pela Pluggy; o cliente não controla o que
        ela ecoa. Remover aqui garante que nenhum caminho de erro devolva o
        secret ou a chave, seja qual for a resposta.
        """
        for segredo in (self._client_secret, self._api_key):
            if segredo is not None and segredo.get_secret_value():
                texto = texto.replace(segredo.get_secret_value(), "***")
        return texto


def _segundos_do_cabecalho(valor: str | None) -> float | None:
    """`Retry-After` em segundos ou em data HTTP; `None` se não der para ler."""
    if not valor:
        return None
    valor = valor.strip()
    try:
        return float(valor)
    except ValueError:
        pass
    try:
        quando = parsedate_to_datetime(valor)
    except (TypeError, ValueError):
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=UTC)
    return (quando - datetime.now(UTC)).total_seconds()


__all__ = ["URL_PADRAO", "PluggyCliente", "PluggyErro", "RespostaBruta"]
