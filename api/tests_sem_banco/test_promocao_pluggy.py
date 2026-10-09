"""Critério da promoção automática da sync (D-21) — sem banco."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest

from app.conversao_pluggy import OBS_PAGAMENTO_NO_CARTAO
from app.enums import TipoTransacao
from app.ingestao.base import ItemExtraido
from app.services.promocao_pluggy import MOTIVOS, motivo_para_revisao

LIMPO = ItemExtraido(
    linha_bruta="MERCADO EXEMPLO",
    linha_num=1,
    data=date(2026, 9, 1),
    valor=Decimal("45.10"),
    descricao="MERCADO EXEMPLO",
    tipo=TipoTransacao.DESPESA,
    confianca=Decimal("1.00"),
    id_externo="tx-1",
)


def test_item_limpo_com_categoria_e_promovido() -> None:
    assert motivo_para_revisao(LIMPO, categoria_id=7, ja_existe=False) is None


@pytest.mark.parametrize(
    ("troca", "categoria_id", "ja_existe", "motivo"),
    [
        ({}, 7, True, "duplicata"),
        (
            {"observacao": "Possível duplicata da Pluggy (no mesmo lote): ..."},
            7,
            False,
            "possivel_duplicata",
        ),
        ({"id_externo": "bill:f1:encargos", "confianca": Decimal("0.70")}, 7, False, "encargos"),
        (
            {"tipo": TipoTransacao.TRANSFERENCIA, "observacao": OBS_PAGAMENTO_NO_CARTAO},
            None,
            False,
            "pagamento_fatura_cartao",
        ),
        (
            {"tipo": TipoTransacao.TRANSFERENCIA, "confianca": Decimal("1.00")},
            None,
            False,
            "transferencia",
        ),
        ({"observacao": "Competência estimada..."}, 7, False, "observacao"),
        ({"confianca": Decimal("0.95")}, 7, False, "confianca"),
        ({}, None, False, "sem_categoria"),
    ],
)
def test_motivos_para_ficar_na_revisao(
    troca: dict[str, object], categoria_id: int | None, ja_existe: bool, motivo: str
) -> None:
    item = replace(LIMPO, **troca)  # type: ignore[arg-type]
    assert motivo_para_revisao(item, categoria_id=categoria_id, ja_existe=ja_existe) == motivo
    assert motivo in MOTIVOS


def test_duplicata_vence_os_outros_motivos() -> None:
    """A ordem é a do relatório: o primeiro motivo que se aplica é o do item."""
    item = replace(LIMPO, confianca=Decimal("0.50"), observacao="qualquer coisa")
    assert motivo_para_revisao(item, categoria_id=None, ja_existe=True) == "duplicata"
