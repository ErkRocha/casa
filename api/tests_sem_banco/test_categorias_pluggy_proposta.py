"""Proposta inicial do mapeamento de categorias da Pluggy (D-21) — sem banco."""

from __future__ import annotations

import pytest

from app.enums import TipoTransacao
from app.seed import ARVORE_CATEGORIAS
from app.services.categorias_pluggy import (
    AMBIGUAS,
    PROPOSTA_INICIAL,
    e_transferencia_pluggy,
    planejar_criacao,
    proposta_para,
)

#: Alvos que não vêm do seed: dependem de a categoria existir no banco.
#: "Juros e encargos" foi criada como dado em 06/10/2026.
FORA_DO_SEED = {"Juros e encargos"}


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
    assert proposta_para("Services")[0] == "ambigua"
    assert proposta_para("Categoria que a Pluggy inventou") == ("sem_proposta", "")
    assert not e_transferencia_pluggy("11000000", "Groceries")


@pytest.mark.parametrize(
    ("nome", "alvo"),
    [
        ("Shopping", "Compras"),
        ("Online shopping", "Compras › Online"),
        ("Electronics", "Compras › Eletrônicos"),
        ("Office supplies", "Compras"),
        ("Office Supplies", "Compras"),
        ("Pet supplies and vet", "Pets"),
        ("Digital services", "Assinaturas"),
        ("Car rental", "Transporte"),
        ("Gambling", "Lazer"),
    ],
)
def test_decisoes_de_15_10_2026(nome: str, alvo: str) -> None:
    assert proposta_para(nome) == ("mapear", (alvo,))


@pytest.mark.parametrize(
    "nome", ["Services", "Loans", "Loans and financing", "Investments", "Insurance"]
)
def test_sem_mapeamento_de_proposito(nome: str) -> None:
    tipo, motivo = proposta_para(nome)
    assert tipo == "ambigua"
    assert "decisão do usuário" in str(motivo)


def test_compras_e_pets_estao_no_seed_depois_das_antigas() -> None:
    raizes = [raiz for raiz, *_ in ARVORE_CATEGORIAS]
    # Categoria nova entra no fim: inserir no meio repintaria as seguintes.
    assert raizes[-2:] == ["Compras", "Pets"]
    filhas = {raiz: f for raiz, _t, _c, f in ARVORE_CATEGORIAS}
    assert filhas["Compras"] == ["Online", "Eletrônicos"]


# --- planejar_criacao: o que o --aplicar criaria -----------------------------


def test_cria_raiz_e_filha_quando_faltam_as_duas() -> None:
    alvo, nos = planejar_criacao({}, [], ("Compras › Online",)) or ("", [])
    assert alvo == "Compras › Online"
    assert [(n.caminho, n.pai, n.tipo) for n in nos] == [
        ("Compras", None, TipoTransacao.DESPESA),
        ("Compras › Online", "Compras", TipoTransacao.DESPESA),
    ]


def test_cria_so_a_filha_quando_a_raiz_existe() -> None:
    plano = planejar_criacao({"COMPRAS": object()}, ["Compras"], ("Compras › Eletrônicos",))
    assert plano is not None
    assert [n.caminho for n in plano[1]] == ["Compras › Eletrônicos"]


def test_nao_cria_o_que_ja_existe_nem_o_que_nao_e_do_seed() -> None:
    assert planejar_criacao({"PETS": object()}, ["Pets"], ("Pets",)) is None
    assert planejar_criacao({}, [], ("Juros e encargos",)) is None


def test_nao_cria_por_cima_de_inativa() -> None:
    # Viva mas inativa: está em `vivas` e não em `caminhos`.
    assert planejar_criacao({}, ["Pets"], ("Pets",)) is None
    assert planejar_criacao({}, ["Compras"], ("Compras › Online",)) is None
    assert (
        planejar_criacao(
            {"COMPRAS": object()}, ["Compras", "Compras › Online"], ("Compras › Online",)
        )
        is None
    )
