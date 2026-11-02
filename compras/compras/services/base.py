"""Erros de domínio que o `main` traduz em HTTP.

Router valida entrada e chama service; regra de negócio mora no service
(regra 12), como em finanças.
"""

from typing import Any


class ErroDominio(Exception):
    """Base dos erros que viram resposta HTTP."""


class NaoEncontrado(ErroDominio):
    """404."""

    def __init__(self, recurso: str, id_: object) -> None:
        super().__init__(f"{recurso} {id_} não encontrado")


class Conflito(ErroDominio):
    """409, com o estado atual junto quando o celular precisa dele.

    Ex.: comprar um item que o outro celular acabou de tirar da lista. A
    resposta leva o item como está, para a tela se acertar sem outra
    consulta.
    """

    def __init__(self, mensagem: str, corpo: dict[str, Any] | None = None) -> None:
        super().__init__(mensagem)
        self.corpo = corpo or {}


class RegraViolada(ErroDominio):
    """422: o pedido é válido como formato, mas a regra não deixa."""
