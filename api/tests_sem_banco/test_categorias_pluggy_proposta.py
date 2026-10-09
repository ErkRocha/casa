"""Proposta inicial do mapeamento de categorias da Pluggy (D-21) — sem banco."""

from __future__ import annotations

import pytest

from app.enums import TipoTransacao
from app.seed import ARVORE_CATEGORIAS
from app.services.categorias_pluggy import (
    AMBIGUAS,
    PROPOSTA_INICIAL,
    e_transferencia_pluggy,
    proposta_para,
)

#: Alvos que não vêm do seed: dependem de a categoria existir no banco.
#: "Juros e encargos" foi criada como dado em 06/10/2026; "Pets" é da D-04.
FORA_DO_SEED = {"Juros e encargos", "Pets"}


def _caminhos_do_seed() -> dict[str, TipoTransacao]:
    caminhos: dict[str, TipoTransacao] = {}
    for raiz, tipo, _cor, filhas in ARVORE_CATEGORIAS:
        caminhos[raiz] = tipo
        for filha in filhas:
            caminhos[f"{raiz} › {filha}"] = tipo
    return caminhos


def test_todo_alvo_existe_no_seed_ou_e_dado_conhecido() -> None:
    caminhos = _caminhos_do_seed()
    for nome, alvos in PROPOSTA_INICIAL.items():
        for alvo in alvos:
            assert alvo in caminhos or alvo in FORA_DO_SEED, f"{nome} -> {alvo}"


def test_receita_da_pluggy_vai_para_receita_e_o_resto_para_despesa() -> None:
    caminhos = _caminhos_do_seed()
    receitas = {
        "Income",
        "Salary",
        "Entrepreneurial activities",
        "Retirement",
        "Government aid",
        "Non-recurring income",
        "Proceeds interests and dividends",
    }
    for nome, alvos in PROPOSTA_INICIAL.items():
        for alvo in alvos:
            if alvo in FORA_DO_SEED:
                continue
            esperado = TipoTransacao.RECEITA if nome in receitas else TipoTransacao.DESPESA
            assert caminhos[alvo] is esperado, f"{nome} -> {alvo}"


def test_proposta_e_ambiguas_nao_se_cruzam() -> None:
    assert not set(PROPOSTA_INICIAL) & set(AMBIGUAS)


def test_nenhuma_transferencia_e_proposta() -> None:
    for nome in PROPOSTA_INICIAL:
        assert not e_transferencia_pluggy(None, nome), nome


@pytest.mark.parametrize(
    ("pluggy_id", "nome"),
    [
        ("04000000", "Same person transfer"),
        (None, "Same person transfer - PIX"),
        ("05000000", "Transfers"),
        ("05080000", "Transfer - TED"),
        (None, "Transfer - PIX"),
        (None, "Credit card payment"),
        ("06000000", "Third-party transfers"),
        (None, "PIX"),
    ],
)
def test_familias_de_transferencia(pluggy_id: str | None, nome: str) -> None:
    assert e_transferencia_pluggy(pluggy_id, nome)
    assert proposta_para(nome)[0] == "transferencia"


def test_proposta_para() -> None:
    assert proposta_para("Groceries") == ("mapear", ("Alimentação › Mercado",))
    assert proposta_para("Online shopping")[0] == "ambigua"
    assert proposta_para("Categoria que a Pluggy inventou") == ("sem_proposta", "")
    assert not e_transferencia_pluggy("11000000", "Groceries")
