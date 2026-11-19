"""Fatura do Nubank: valor negativo é estorno, que abate o gasto (D-34)."""

from datetime import date
from decimal import Decimal

from app.enums import TipoTransacao
from app.ingestao.base import DocumentoExtraido
from app.ingestao.nubank_fatura import _LINHA, NubankFaturaParser


def _item(linha: str):  # type: ignore[no-untyped-def]
    casou = _LINHA.match(linha)
    assert casou is not None
    return NubankFaturaParser()._item(casou, linha, 1, date(2026, 5, 4), date(2026, 6, 3))


def test_valor_negativo_vira_estorno() -> None:
    item = _item("10 MAI •••• 1234 Loja Teste −R$ 35,50")
    assert item is not None
    assert item.tipo is TipoTransacao.ESTORNO
    assert item.valor == Decimal("35.50")
    assert item.observacao == "estorno"


def test_valor_positivo_segue_despesa() -> None:
    item = _item("10 MAI •••• 1234 Loja Teste R$ 35,50")
    assert item is not None and item.tipo is TipoTransacao.DESPESA


def test_soma_dos_itens_e_liquida_de_estorno() -> None:
    doc = DocumentoExtraido(origem="nubank_fatura", parser="nubank_fatura")
    for linha in ("10 MAI Loja A R$ 100,00", "11 MAI Loja A −R$ 30,00"):
        item = _item(linha)
        assert item is not None
        doc.itens.append(item)
    assert doc.soma_itens == Decimal("70.00")
