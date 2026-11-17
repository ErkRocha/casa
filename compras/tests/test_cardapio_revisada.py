"""Quantidades revisadas da receita ("Conferi, está certa") e a migration 0005 (D-30)."""

import os
import uuid
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from compras.carga_cardapio import run
from compras.config import url_para_alembic
from compras.db import SessionLocal, engine
from tests.apoio import ERIK, LAURA, receita

pytestmark = pytest.mark.usefixtures("semeado")

MARCA = "[REVISAR QUANTIDADES] Quantidades estimadas pela carga inicial."


def _config() -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url_para_alembic(os.environ["COMPRAS_DATABASE_URL"]))
    return config


def _colunas(tabela: str) -> set[str]:
    with engine.connect() as c:
        return set(
            c.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'compras' AND table_name = :t"
                ),
                {"t": tabela},
            ).scalars()
        )


def _inserir(nome: str, modo_preparo: str | None, deleted: bool = False) -> int:
    with SessionLocal() as s:
        id_ = s.execute(
            text(
                "INSERT INTO compras.receitas "
                "(nome, nome_normalizado, tipo, rendimento_porcoes, modo_preparo, deleted_em) "
                "VALUES (:n, :n, 'almoco', 1, :m, CASE WHEN :d THEN now() END) RETURNING id"
            ),
            {"n": nome, "m": modo_preparo, "d": deleted},
        ).scalar_one()
        s.commit()
        return int(id_)


def _estado(id_: int) -> dict[str, Any]:
    with engine.connect() as c:
        linha = c.execute(
            text(
                "SELECT modo_preparo, quantidades_revisadas, revisadas_por, "
                "revisadas_em IS NOT NULL AS tem_em FROM compras.receitas WHERE id = :i"
            ),
            {"i": id_},
        ).one()
    return dict(linha._mapping)


def test_migration_0005_aplica_reverte_e_migra_os_dados() -> None:
    config = _config()
    try:
        command.downgrade(config, "0004")
        assert not {"quantidades_revisadas", "revisadas_por", "revisadas_em"} & _colunas("receitas")
        assert _colunas("passos_feitos") == set()

        com_texto = _inserir("Com marca e texto", f"{MARCA}\nMisture tudo.\nSirva.")
        so_marca = _inserir("So a marca", MARCA)
        sem_marca = _inserir("Sem marca", "Misture tudo.")
        sem_modo = _inserir("Sem modo", None)
        marca_no_meio = _inserir("Marca no meio", f"Misture.\n{MARCA}")
        apagada = _inserir("Apagada", "Misture.", deleted=True)

        command.upgrade(config, "head")
        assert {"quantidades_revisadas", "revisadas_por", "revisadas_em"} <= _colunas("receitas")
        assert {"sessao_id", "receita_id", "feito_por", "feito_em", "id_cliente"} <= _colunas(
            "passos_feitos"
        )

        # Com a linha: vira `false`, sem a linha nem a quebra de linha.
        e = _estado(com_texto)
        assert e["modo_preparo"] == "Misture tudo.\nSirva."
        assert e["quantidades_revisadas"] is False and e["revisadas_por"] is None
        assert e["tem_em"] is False
        # Só a linha: o texto fica nulo.
        e = _estado(so_marca)
        assert e["modo_preparo"] is None and e["quantidades_revisadas"] is False
        # Sem a linha (ou com ela fora da primeira linha): vira `true`, por "migracao".
        for id_, modo in (
            (sem_marca, "Misture tudo."),
            (sem_modo, None),
            (marca_no_meio, f"Misture.\n{MARCA}"),
        ):
            e = _estado(id_)
            assert e["modo_preparo"] == modo
            assert e["quantidades_revisadas"] is True
            assert e["revisadas_por"] == "migracao" and e["tem_em"] is True
        # A apagada não é viva: fica como veio.
        assert _estado(apagada)["quantidades_revisadas"] is False

        # O check recusa o estado incoerente.
        with SessionLocal() as s:
            with pytest.raises(Exception, match="ck_receitas_revisadas_com_autor"):
                s.execute(
                    text(
                        "UPDATE compras.receitas SET quantidades_revisadas = true, "
                        "revisadas_por = NULL WHERE id = :i"
                    ),
                    {"i": com_texto},
                )
            s.rollback()
            with pytest.raises(Exception, match="ck_receitas_revisadas_com_autor"):
                s.execute(
                    text("UPDATE compras.receitas SET revisadas_por = 'x' WHERE id = :i"),
                    {"i": com_texto},
                )
            s.rollback()

        # O downgrade recoloca a linha nas que estão `false` e some com as colunas.
        command.downgrade(config, "0004")
        assert "quantidades_revisadas" not in _colunas("receitas")
        with engine.connect() as c:
            modos = {
                i: m for i, m in c.execute(text("SELECT id, modo_preparo FROM compras.receitas"))
            }
        assert modos[com_texto] == f"{MARCA}\nMisture tudo.\nSirva."
        assert modos[so_marca] == MARCA
        assert modos[sem_marca] == "Misture tudo."
        assert modos[sem_modo] is None
    finally:
        command.upgrade(config, "head")

    assert "quantidades_revisadas" in _colunas("receitas")


def _nova(client: TestClient, nome: str = "Arroz") -> dict[str, Any]:
    return receita(client, nome, [], rendimento="2")


def test_receita_criada_por_pessoa_nasce_revisada(client: TestClient) -> None:
    r = _nova(client)
    assert r["quantidades_revisadas"] is True
    assert r["revisadas_por"] == "Laura"
    assert r["revisadas_em"] is not None
    lida = client.get(f"/receitas/{r['id']}").json()
    assert lida["quantidades_revisadas"] is True and lida["revisadas_por"] == "Laura"


def test_carga_nasce_nao_revisada_e_continua_idempotente(client: TestClient) -> None:
    run()
    todas = client.get("/receitas", params={"limite": 50}).json()
    assert todas["total"] == 15
    assert all(i["quantidades_revisadas"] is False for i in todas["items"])
    assert client.get("/receitas", params={"revisadas": "true"}).json()["total"] == 0

    assert not run().mudou()
    nao = client.get("/receitas", params={"revisadas": "false", "limite": 50}).json()
    assert nao["total"] == 15


def test_conferir_marca_guarda_quem_e_repetir_mantem_o_primeiro(client: TestClient) -> None:
    run()
    id_ = client.get("/receitas").json()["items"][0]["id"]
    antes = client.get(f"/receitas/{id_}").json()
    assert antes["quantidades_revisadas"] is False

    primeira = client.post(f"/receitas/{id_}/conferir", headers=LAURA)
    assert primeira.status_code == 200, primeira.text
    corpo = primeira.json()
    assert corpo["quantidades_revisadas"] is True
    assert corpo["revisadas_por"] == "Laura" and corpo["revisadas_em"] is not None
    assert corpo["ingredientes"] == antes["ingredientes"]  # devolve a receita inteira

    segunda = client.post(f"/receitas/{id_}/conferir", headers=ERIK)
    assert segunda.status_code == 200
    assert segunda.json()["revisadas_por"] == "Laura"
    assert segunda.json()["revisadas_em"] == corpo["revisadas_em"]
    assert segunda.json()["atualizado_em"] == corpo["atualizado_em"]


def test_conferir_receita_inexistente_ou_sem_quem(client: TestClient) -> None:
    assert client.post("/receitas/999/conferir", headers=LAURA).status_code == 404
    r = _nova(client)
    assert client.post(f"/receitas/{r['id']}/conferir").status_code == 400


def test_put_nao_mexe_na_revisao(client: TestClient) -> None:
    run()
    id_ = client.get("/receitas").json()["items"][0]["id"]
    corpo = client.get(f"/receitas/{id_}").json()
    edicao = {
        "nome": corpo["nome"],
        "tipo": corpo["tipo"],
        "rendimento_porcoes": "3",
        "modo_preparo": "Novo modo.",
        "ingredientes": [
            {"produto_id": i["produto_id"], "quantidade": i["quantidade"], "unidade": i["unidade"]}
            for i in corpo["ingredientes"]
        ],
    }
    # Não conferida: editar não confere.
    r = client.put(f"/receitas/{id_}", json=edicao, headers=ERIK)
    assert r.status_code == 200, r.text
    assert r.json()["quantidades_revisadas"] is False and r.json()["revisadas_por"] is None

    # Conferida: editar não desmarca, nem troca o autor.
    client.post(f"/receitas/{id_}/conferir", headers=LAURA)
    r = client.put(f"/receitas/{id_}", json={**edicao, "rendimento_porcoes": "4"}, headers=ERIK)
    assert r.status_code == 200
    assert r.json()["quantidades_revisadas"] is True and r.json()["revisadas_por"] == "Laura"
    # E um corpo com os campos tentando mudar a revisão não os muda.
    r = client.put(
        f"/receitas/{id_}", json={**edicao, "quantidades_revisadas": False}, headers=ERIK
    )
    assert r.json()["quantidades_revisadas"] is True


def test_filtro_revisadas(client: TestClient) -> None:
    run()
    id_ = client.get("/receitas").json()["items"][0]["id"]
    client.post(f"/receitas/{id_}/conferir", headers=LAURA)
    feita_a_mao = _nova(client, "Feita a mão")

    sim = client.get("/receitas", params={"revisadas": "true", "limite": 50}).json()
    nao = client.get("/receitas", params={"revisadas": "false", "limite": 50}).json()
    assert {i["id"] for i in sim["items"]} == {id_, feita_a_mao["id"]}
    assert nao["total"] == 14 and id_ not in {i["id"] for i in nao["items"]}
    assert client.get("/receitas", params={"limite": 50}).json()["total"] == 16
    assert all("quantidades_revisadas" in i for i in sim["items"])


def test_duplicar_leva_a_conferencia_da_origem(client: TestClient) -> None:
    r = _nova(client)
    copia = client.post(f"/receitas/{r['id']}/duplicar", headers=ERIK).json()
    assert copia["quantidades_revisadas"] is True and copia["revisadas_por"] == "Laura"

    run()
    ids = [i["id"] for i in client.get("/receitas", params={"revisadas": "false"}).json()["items"]]
    copia = client.post(f"/receitas/{ids[0]}/duplicar", headers=ERIK).json()
    assert copia["quantidades_revisadas"] is False and copia["revisadas_por"] is None


def test_reenvio_do_mesmo_id_cliente_nao_muda_a_revisao(client: TestClient) -> None:
    corpo = {
        "id_cliente": str(uuid.uuid4()),
        "nome": "Sopa",
        "tipo": "janta",
        "rendimento_porcoes": "1",
        "ingredientes": [],
    }
    primeira = client.post("/receitas", json=corpo, headers=LAURA)
    segunda = client.post("/receitas", json=corpo, headers=ERIK)
    assert (primeira.status_code, segunda.status_code) == (201, 200)
    assert segunda.json()["revisadas_por"] == "Laura"
