"""Chave de acesso da NF-e/NFC-e: 44 dígitos com dígito verificador.

Layout (Manual de Orientação do Contribuinte):

    cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1)

O dígito verificador é o módulo 11 dos 43 primeiros, com pesos de 2 a 9 da
direita para a esquerda; resto 0 ou 1 dá 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Código IBGE de cada UF, como vem na chave.
UFS = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}  # fmt: skip

#: Modelo 65 é a NFC-e (o cupom do mercado); 55 é a NF-e.
MODELO_NFCE = "65"


class ChaveInvalida(ValueError):
    """O texto não é uma chave de acesso válida."""


@dataclass(frozen=True, slots=True)
class Chave:
    numero: str
    uf: str
    ano_mes: str
    cnpj: str
    modelo: str
    serie: str
    numero_nota: str

    @property
    def cnpj_formatado(self) -> str:
        c = self.cnpj
        return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def digito_verificador(base43: str) -> str:
    """O dígito dos 43 primeiros números da chave."""
    soma = 0
    peso = 2
    for digito in reversed(base43):
        soma += int(digito) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def validar(texto: str) -> Chave:
    """A chave, sem espaços nem pontuação, conferida. `ChaveInvalida` se não for."""
    numero = re.sub(r"[\s.\-/]", "", texto)
    if not re.fullmatch(r"\d{44}", numero):
        raise ChaveInvalida("A chave de acesso tem 44 dígitos.")
    if digito_verificador(numero[:43]) != numero[43]:
        raise ChaveInvalida("A chave de acesso não confere: o dígito verificador está errado.")
    uf = UFS.get(numero[:2])
    if uf is None:
        raise ChaveInvalida(f"A chave começa com {numero[:2]}, que não é código de UF.")
    return Chave(
        numero=numero,
        uf=uf,
        ano_mes=numero[2:6],
        cnpj=numero[6:20],
        modelo=numero[20:22],
        serie=numero[22:25],
        numero_nota=numero[25:34],
    )
