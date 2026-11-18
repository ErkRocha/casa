"""Faixas de orçamento: a mesma regra em Python e em SQL."""

from decimal import Decimal

import pytest

from app.faixas_orcamento import LIMIAR_ATENCAO, LIMIAR_ESTOURADO, faixa_orcamento, sql_faixa


@pytest.mark.parametrize(
    ("percentual", "faixa"),
    [
        ("0", "ok"),
        ("79.99", "ok"),
        ("80", "atencao"),
        ("99.99", "atencao"),
        ("100", "estourado"),
        ("140", "estourado"),
    ],
)
def test_faixa_orcamento(percentual: str, faixa: str) -> None:
    assert faixa_orcamento(Decimal(percentual)) == faixa


def test_sql_usa_os_mesmos_limiares() -> None:
    sql = sql_faixa("razao")
    assert f"razao >= {LIMIAR_ESTOURADO} THEN 'estourado'" in sql
    assert f"razao >= {LIMIAR_ATENCAO} THEN 'atencao'" in sql
    assert (Decimal("80"), Decimal("100")) == (LIMIAR_ATENCAO, LIMIAR_ESTOURADO)
