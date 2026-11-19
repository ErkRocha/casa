"""Sugestão de medida da variante, lida na descrição do item da nota (D-33).

Procura o tamanho no fim de uma palavra ou sozinho: `450G`, `1KG`, `1,5L`,
`250ML`, `GF1KG`, `C/12`. Achou um só: sugere `medida_base` e `conteudo`
(450G -> g 450; 1,5L -> ml 1500; C/12 -> un 12). Nenhum, ou mais de um
(ex.: "LEITE 1L C/12"): nenhuma sugestão. É só sugestão: quem grava é a
associação, com confirmação (`modelo-notas.md`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from compras.enums import MedidaBase
from compras.normalizar import normalizar

_TAMANHO = re.compile(r"^[A-Z]*?(\d+(?:[.,]\d+)?)(KG|GR|G|ML|LT|L)$")
_CAIXA = re.compile(r"^C/(\d+)$")

#: Quanto de `medida_base` vale 1 de cada unidade.
_FATOR: dict[str, tuple[MedidaBase, Decimal]] = {
    "G": (MedidaBase.G, Decimal(1)),
    "GR": (MedidaBase.G, Decimal(1)),
    "KG": (MedidaBase.G, Decimal(1000)),
    "ML": (MedidaBase.ML, Decimal(1)),
    "L": (MedidaBase.ML, Decimal(1000)),
    "LT": (MedidaBase.ML, Decimal(1000)),
}


@dataclass(frozen=True, slots=True)
class MedidaSugerida:
    medida_base: MedidaBase
    conteudo: Decimal


def sugerir_medida(descricao: str) -> MedidaSugerida | None:
    achadas: list[MedidaSugerida] = []
    for palavra in normalizar(descricao).split():
        palavra = palavra.rstrip(".,;:")
        caixa = _CAIXA.match(palavra)
        if caixa:
            conteudo = Decimal(caixa.group(1))
            if conteudo > 0:
                achadas.append(MedidaSugerida(MedidaBase.UN, conteudo))
            continue
        tamanho = _TAMANHO.match(palavra)
        if tamanho:
            base, fator = _FATOR[tamanho.group(2)]
            conteudo = Decimal(tamanho.group(1).replace(",", ".")) * fator
            if conteudo > 0:
                achadas.append(MedidaSugerida(base, conteudo.quantize(Decimal("0.001"))))
    return achadas[0] if len(achadas) == 1 else None
