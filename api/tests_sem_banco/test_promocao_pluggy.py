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


# --- rejeição automática (D-22) ---------------------------------------------

from app.config import Settings  # noqa: E402
from app.conversao_pluggy import OBS_MESMA_PESSOA, OBS_PAGAMENTO_NA_CONTA  # noqa: E402
from app.services.promocao_pluggy import REJEICOES, motivo_para_rejeitar  # noqa: E402

CASA = frozenset({"11122233344"})
TRANSF = replace(LIMPO, tipo=TipoTransacao.TRANSFERENCIA, confianca=Decimal("0.70"))


@pytest.mark.parametrize(
    ("item", "motivo"),
    [
        (replace(TRANSF, observacao=OBS_PAGAMENTO_NO_CARTAO), "pagamento_fatura"),
        (replace(TRANSF, observacao=OBS_PAGAMENTO_NA_CONTA), "pagamento_fatura"),
        (replace(TRANSF, observacao=OBS_MESMA_PESSOA), "movimento_casa"),
        (replace(LIMPO, documento_contraparte="11122233344"), "movimento_casa"),
        (
            replace(LIMPO, tipo=TipoTransacao.RECEITA, documento_contraparte="11122233344"),
            "movimento_casa",
        ),
    ],
)
def test_rejeita_o_que_nao_e_gasto_da_casa(item: ItemExtraido, motivo: str) -> None:
    assert motivo_para_rejeitar(item, documentos_casa=CASA) == motivo
    assert motivo in REJEICOES


@pytest.mark.parametrize(
    "item",
    [
        LIMPO,
        replace(LIMPO, documento_contraparte="99988877766"),
        replace(TRANSF, observacao="Transferência que a Pluggy não explica."),
        # Possível duplicata pede o olho do usuário, mesmo sendo da casa.
        replace(
            LIMPO,
            documento_contraparte="11122233344",
            observacao="Possível duplicata da Pluggy (no mesmo lote): ...",
        ),
        replace(LIMPO, id_externo="bill:f1:encargos", observacao=OBS_PAGAMENTO_NO_CARTAO),
    ],
)
def test_nao_rejeita_o_resto(item: ItemExtraido) -> None:
    assert motivo_para_rejeitar(item, documentos_casa=CASA) is None


def test_documentos_da_casa_do_env() -> None:
    s = Settings(casa_documentos=" 111.222.333-44, ,55566677788 ")
    assert s.documentos_da_casa == frozenset({"11122233344", "55566677788"})
    assert Settings(casa_documentos=None).documentos_da_casa == frozenset()


# --- compra em aberto (D-23) ------------------------------------------------

from app.conversao_pluggy import OBS_ABERTA  # noqa: E402


def test_compra_em_aberto_limpa_e_promovida() -> None:
    aberta = replace(LIMPO, observacao=OBS_ABERTA)
    assert motivo_para_revisao(aberta, categoria_id=7, ja_existe=False) is None
    assert motivo_para_revisao(aberta, categoria_id=None, ja_existe=False) == "sem_categoria"


def test_compra_em_aberto_com_outra_nota_fica_na_revisao() -> None:
    aberta = replace(LIMPO, observacao=f"{OBS_ABERTA} Valor arredondado.")
    assert motivo_para_revisao(aberta, categoria_id=7, ja_existe=False) == "observacao"
