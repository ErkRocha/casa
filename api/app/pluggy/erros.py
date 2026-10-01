"""Erros do cliente da Pluggy.

Nenhuma mensagem daqui carrega credencial. O `client_secret` e a `apiKey`
são removidos de qualquer texto vindo da resposta antes de virar mensagem
(`PluggyCliente._sanitizar`), e erro de rede é relançado sem a exceção do
httpx encadeada, porque ela guarda a requisição — corpo e cabeçalhos
inclusive.
"""

from __future__ import annotations


class PluggyErro(Exception):
    """Base de tudo que o cliente levanta."""


class PluggyRedeErro(PluggyErro):
    """Não houve resposta: timeout, conexão recusada, DNS."""


class PluggyFormatoErro(PluggyErro):
    """A resposta chegou, mas não no formato documentado."""


class PluggyRespostaErro(PluggyErro):
    """A Pluggy respondeu com erro HTTP.

    `codigo` é o `codeDescription` do corpo — o identificador estável que a
    documentação manda usar para decidir o que fazer (ex.
    `LIST_ITEMS_FEATURE_NOT_ENABLED`). `message` não é estável e serve só
    para leitura humana.
    """

    def __init__(self, mensagem: str, *, status: int, endpoint: str, codigo: str | None) -> None:
        super().__init__(mensagem)
        self.status = status
        self.endpoint = endpoint
        self.codigo = codigo


class PluggyAutenticacaoErro(PluggyRespostaErro):
    """Credencial recusada. Nunca é retentada: repetir não muda a resposta."""


class PluggyLimiteErro(PluggyRespostaErro):
    """429 até esgotar as tentativas."""
