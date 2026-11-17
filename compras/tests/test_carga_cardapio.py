"""A carga inicial do cardápio (`python -m compras.carga_cardapio`)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.carga_cardapio import AUTOR, PRODUTOS, RECEITAS, run
from compras.services.identidades import IdentidadeService
from tests.apoio import LAURA, pessoa, produto, receita, refeicao, semana

pytestmark = pytest.mark.usefixtures("semeado")


def _contagens(session: Session) -> dict[str, int]:
    session.rollback()
    return {
        t: int(
            session.execute(
                text(f"SELECT count(*) FROM compras.{t} WHERE deleted_em IS NULL")
            ).scalar_one()
        )
        for t in ("pessoas", "produtos", "receitas", "receita_ingredientes", "despensa")
    }


def test_primeira_vez_cria_e_a_segunda_nao_muda_nada(session: Session) -> None:
    primeira = run()
    assert primeira.pessoas_criadas == 2
    assert primeira.receitas_criadas == len(RECEITAS) == 15
    assert primeira.produtos_com_medida > 0
    depois_da_primeira = _contagens(session)
    assert depois_da_primeira["pessoas"] == 2 and depois_da_primeira["receitas"] == 15

    session.rollback()
    atualizado_em = session.execute(
        text("SELECT max(atualizado_em) FROM compras.produtos")
    ).scalar_one()

    segunda = run()
    assert not segunda.mudou(), segunda
    assert _contagens(session) == depois_da_primeira
    session.rollback()
    assert (
        session.execute(text("SELECT max(atualizado_em) FROM compras.produtos")).scalar_one()
        == atualizado_em
    )


def test_pessoas_com_a_porcao_padrao(client: TestClient) -> None:
    run()
    pessoas = {p["nome"]: p for p in client.get("/pessoas").json()}
    assert pessoas["Erik"]["porcao_padrao"] == "1.50"
    assert pessoas["Laura"]["porcao_padrao"] == "1.00"
    assert pessoas["Erik"]["identidade_id"] is None  # sem identidade, fica nulo


def test_liga_a_identidade_quando_existe(client: TestClient, session: Session) -> None:
    ident = IdentidadeService(session).criar("erik@exemplo.com", "Erik")
    IdentidadeService(session).criar("outra@exemplo.com", "Maria")
    session.commit()

    resumo = run()
    assert resumo.identidades_ligadas == 1
    pessoas = {p["nome"]: p for p in client.get("/pessoas").json()}
    assert pessoas["Erik"]["identidade_id"] == ident.id
    assert pessoas["Erik"]["login"] == "erik@exemplo.com"
    assert pessoas["Laura"]["identidade_id"] is None


def test_identidade_com_acento_e_caixa_diferentes_tambem_liga(
    client: TestClient, session: Session
) -> None:
    ident = IdentidadeService(session).criar("laura@exemplo.com", "LAURA")
    session.commit()
    run()
    laura = next(p for p in client.get("/pessoas").json() if p["nome"] == "Laura")
    assert laura["identidade_id"] == ident.id


def test_nao_sobrescreve_o_que_o_casal_ja_tem(client: TestClient) -> None:
    pessoa(client, "Erik", "3")
    cebola = produto(client, "Cebola", "kg", "ml", "99")  # o casal escolheu assim
    antiga = receita(client, "Arroz", [], rendimento="4", modo_preparo="do jeito da casa")

    run()
    assert (
        next(p for p in client.get("/pessoas").json() if p["nome"] == "Erik")["porcao_padrao"]
        == "3.00"
    )
    medidas = next(p for p in client.get("/produtos", params={"busca": "Cebola"}).json())
    assert medidas["id"] == cebola
    assert (medidas["medida_base"], medidas["medida_por_unidade"]) == ("ml", "99.000")
    arroz = client.get(f"/receitas/{antiga['id']}").json()
    assert arroz["rendimento_porcoes"] == "4.00"
    assert arroz["modo_preparo"] == "do jeito da casa"
    assert arroz["ingredientes"] == []
    assert client.get("/receitas", params={"busca": "Arroz"}).json()["total"] == 1


def test_produto_existente_ganha_medida_so_se_estiver_nulo(client: TestClient) -> None:
    run()
    leite = client.get("/produtos", params={"busca": "Leite integral"}).json()[0]
    assert leite["secao_nome"] == "Frios e laticínios"  # o do seed, que já existia
    assert (leite["medida_base"], leite["medida_por_unidade"]) == ("ml", "1000.000")
    ovos = client.get("/produtos", params={"busca": "Ovos 12"}).json()[0]
    assert (ovos["medida_base"], ovos["medida_por_unidade"]) == ("un", "12.000")
    sal = client.get("/produtos", params={"busca": "Sal"}).json()
    assert next(p for p in sal if p["nome"] == "Sal")["medida_base"] is None
    # o produto novo vai para a seção que existe pelo nome
    aveia = client.get("/produtos", params={"busca": "Aveia"}).json()[0]
    assert aveia["secao_nome"] == "Mercearia"


def test_produto_em_outra_unidade_nao_recebe_medida(client: TestClient) -> None:
    """A medida da carga pressupõe a unidade dela; com outra, o casal decide."""
    produto(client, "Arroz 5kg", "kg")
    run()
    arroz = client.get("/produtos", params={"busca": "Arroz 5kg"}).json()[0]
    assert arroz["medida_base"] is None


def test_receitas_nascem_nao_revisadas_e_com_tudo_convertendo(client: TestClient) -> None:
    run()
    todas = client.get("/receitas", params={"limite": 50}).json()
    assert todas["total"] == 15
    for resumo in todas["items"]:
        detalhe = client.get(f"/receitas/{resumo['id']}").json()
        assert detalhe["quantidades_revisadas"] is False, resumo["nome"]
        assert detalhe["revisadas_por"] is None and detalhe["revisadas_em"] is None
        assert "REVISAR" not in detalhe["modo_preparo"], resumo["nome"]
        assert detalhe["rendimento_porcoes"] == "1.00"
        assert detalhe["tempo_preparo_min"] is not None and detalhe["ingredientes"]
        assert all(i["converte"] for i in detalhe["ingredientes"]), resumo["nome"]
        if detalhe["pode_antecipar"]:
            assert detalhe["dura_dias"] >= 1
    # nada que a carga usa fica na fila de "cadastre a medida"
    assert client.get("/produtos/sem-medida").json() == []
    assert {p.nome for p in PRODUTOS} >= {"Cebola", "Sal", "Ovos 12 un"}


def test_as_receitas_antecipaveis_do_enunciado(client: TestClient) -> None:
    run()
    por_nome = {
        r["nome"]: r for r in client.get("/receitas", params={"limite": 50}).json()["items"]
    }
    for nome in (
        "Arroz",
        "Feijão",
        "Frango desfiado (base)",
        "Carne moída com legumes",
        "Sopa de legumes com frango",
        "Sobrecoxa assada com batata-doce",
    ):
        r = por_nome[nome]
        assert r["pode_antecipar"] and r["pode_congelar"] and r["dura_dias"] in (3, 4), nome
    for nome in ("Ovos mexidos com pão integral", "Omelete com legumes e queijo"):
        assert not por_nome[nome]["pode_antecipar"], nome
    assert not por_nome["Brócolis e cenoura no vapor"]["pode_antecipar"]
    aveia = por_nome["Aveia de geladeira com iogurte e fruta"]
    assert aveia["pode_antecipar"] and aveia["dura_dias"] == 3 and not aveia["pode_congelar"]


def test_autor_da_carga_na_auditoria(session: Session) -> None:
    run()
    session.rollback()
    autores = set(
        session.execute(
            text(
                "SELECT DISTINCT autor FROM compras.auditoria "
                "WHERE tabela IN ('pessoas', 'receitas', 'receita_ingredientes')"
            )
        ).scalars()
    )
    assert autores == {AUTOR}


def test_a_lista_sai_das_receitas_da_carga(client: TestClient) -> None:
    run()
    s = semana(client, "2026-11-16")
    frango = client.get("/receitas", params={"busca": "Frango desfiado"}).json()["items"][0]
    refeicao(client, s["id"], "2026-11-16", "almoco", frango["id"])
    resposta = client.post(f"/semanas/{s['id']}/lista", headers=LAURA).json()
    produtos = {c["produto"]: c for c in resposta["criados"]} | {
        c["produto"]: c for c in resposta["confira"]
    }
    # 2 porções (Erik 1,5 + Laura 1): 200 g x 2,5 = 500 g de frango
    assert produtos["Peito de frango"]["quantidade"] == "0.500"
    assert resposta["avisos"] == []
