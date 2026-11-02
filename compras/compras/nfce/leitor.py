"""O contrato do leitor do conteúdo da nota.

O service guarda o conteúdo bruto e pede a um `LeitorNota` que o interprete.
Se a SEFAZ mudar o formato, entra outro leitor com outra `versao`; as notas
antigas continuam com o conteúdo guardado e a versão que as leu, e dá para
relê-las (modelo-dados.md, `leitor_versao`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol


class FormatoDesconhecido(ValueError):
    """O conteúdo não está no formato que este leitor conhece."""


@dataclass(frozen=True, slots=True)
class ItemLido:
    linha_num: int
    descricao: str
    quantidade: Decimal
    valor_total: Decimal
    unidade: str | None = None
    valor_unitario: Decimal | None = None
    codigo: str | None = None
    gtin: str | None = None
    desconto: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class NotaLida:
    cnpj: str | None
    razao_social: str | None
    endereco: str | None
    cidade: str | None
    emitida_em: datetime | None
    valor_total: Decimal | None
    desconto_total: Decimal
    itens: list[ItemLido] = field(default_factory=list)


class LeitorNota(Protocol):
    #: Gravada em `notas_fiscais.leitor_versao`.
    versao: str

    def ler(self, conteudo: bytes, tipo: str | None) -> NotaLida:
        """Interpreta o conteúdo; `FormatoDesconhecido` se não reconhecer."""
        ...
