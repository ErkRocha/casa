"""Faixas de orçamento: uma regra só para painel, avisos e relatório.

A partir de 80% da meta a categoria está em "atenção"; a partir de 100%,
"estourado". Início, Análises, os avisos e o relatório mensal leem daqui:
dois limiares diferentes fariam o relatório contradizer o painel. As cores de
cada faixa estão em `docs/design/README.md`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

#: Percentual da meta a partir do qual a categoria acende "atenção".
LIMIAR_ATENCAO = Decimal("80")
#: Percentual da meta a partir do qual a categoria está "estourado".
LIMIAR_ESTOURADO = Decimal("100")

FaixaOrcamento = Literal["ok", "atencao", "estourado"]


def faixa_orcamento(percentual: Decimal) -> FaixaOrcamento:
    """A faixa de um percentual já calculado (0–100+)."""
    if percentual >= LIMIAR_ESTOURADO:
        return "estourado"
    if percentual >= LIMIAR_ATENCAO:
        return "atencao"
    return "ok"


def sql_faixa(percentual: str) -> str:
    """A mesma regra como expressão SQL sobre `percentual` (regra 7).

    `percentual` é uma expressão do SQL de quem chama, nunca texto do
    usuário. Nulo (meta zero ou sem meta) cai em "ok".
    """
    return (
        f"CASE WHEN {percentual} >= {LIMIAR_ESTOURADO} THEN 'estourado' "
        f"WHEN {percentual} >= {LIMIAR_ATENCAO} THEN 'atencao' ELSE 'ok' END"
    )
