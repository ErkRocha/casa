"""Leitura do comprovante de uma importação da Pluggy (D-16, D-21).

A sync guarda em `importacoes.arquivo_conteudo` o JSON bruto das respostas da
Pluggy, como o PDF é guardado. É dali que o diagnóstico e o reprocessamento
recuperam o que o staging não guarda: a operação e a categoria da Pluggy de
cada item, a conta de origem e as faturas.

Função pura: recebe bytes e devolve objetos tipados. Dinheiro é lido com
`parse_float=Decimal` (regra 1). Resposta que não valida é contada e
pulada — um comprovante antigo com um campo fora do formato não pode
esconder todo o resto.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from app.pluggy.modelos import Conta, Fatura, Transacao


@dataclass(slots=True)
class Comprovante:
    contas: dict[str, Conta] = field(default_factory=dict)
    transacoes: dict[str, Transacao] = field(default_factory=dict)
    faturas: dict[str, Fatura] = field(default_factory=dict)
    #: `accountId` do pedido -> faturas daquela conta.
    faturas_por_conta: dict[str, list[Fatura]] = field(default_factory=lambda: defaultdict(list))
    #: Respostas ou registros que não validaram.
    invalidos: int = 0

    def conta_da_fatura(self, bill_id: str) -> str | None:
        for conta, faturas in self.faturas_por_conta.items():
            if any(f.id == bill_id for f in faturas):
                return conta
        return None


def ler_comprovante(conteudo: bytes | None) -> Comprovante:
    comprovante = Comprovante()
    if not conteudo:
        return comprovante
    try:
        dados = json.loads(conteudo, parse_float=Decimal)
    except ValueError:
        comprovante.invalidos += 1
        return comprovante
    respostas = dados.get("respostas") if isinstance(dados, dict) else None
    if not isinstance(respostas, list):
        return comprovante

    for resposta in respostas:
        if not isinstance(resposta, dict):
            comprovante.invalidos += 1
            continue
        corpo = resposta.get("corpo")
        resultados = corpo.get("results") if isinstance(corpo, dict) else None
        if not isinstance(resultados, list):
            continue
        caminho = resposta.get("caminho")
        params: dict[str, Any] = resposta.get("params") or {}
        for bruto in resultados:
            try:
                if caminho == "/accounts":
                    conta = Conta.model_validate(bruto)
                    comprovante.contas[conta.id] = conta
                elif caminho == "/v2/transactions":
                    transacao = Transacao.model_validate(bruto)
                    comprovante.transacoes[transacao.id] = transacao
                elif caminho == "/bills":
                    fatura = Fatura.model_validate(bruto)
                    comprovante.faturas[fatura.id] = fatura
                    conta_id = params.get("accountId")
                    if isinstance(conta_id, str):
                        comprovante.faturas_por_conta[conta_id].append(fatura)
            except ValidationError:
                comprovante.invalidos += 1
    return comprovante
