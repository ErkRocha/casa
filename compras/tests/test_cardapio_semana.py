"""Pessoas, semanas e refeições do cardápio (D-30)."""

from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.services.identidades import IdentidadeService
from tests.apoio import LAURA, ingrediente, pessoa, produto, receita, refeicao, semana

SEG = "2026-11-16"  # a semana de "hoje" (17/11/2026)
PASSADA = "2026-11-02"


def _dias(corpo: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {d["dia"]: d["refeicoes"] for d in corpo["dias"]}


# --- pessoas ------------------------------------------------------------------


def test_pessoas_crud_e_nome_repetido(client: TestClient) -> None:
    erik = pessoa(client, "Erik", "1.5")
    assert erik["porcao_padrao"] == "1.50" and erik["login"] is None
    assert client.post("/pessoas", json={"nome": "erik"}, headers=LAURA).status_code == 409

    r = client.patch(f"/pessoas/{erik['id']}", json={"porcao_padrao": "2"}, headers=LAURA)
    assert r.json()["porcao_padrao"] == "2.00"
    assert (
        client.patch(
            f"/pessoas/{erik['id']}", json={"porcao_padrao": "0"}, headers=LAURA
        ).status_code
        == 422
    )

    pessoa(client, "Laura")
    assert [p["nome"] for p in client.get("/pessoas").json()] == ["Erik", "Laura"]
    apagada = client.delete(f"/pessoas/{erik['id']}", headers=LAURA)
    assert apagada.json()["deleted_em"] is not None
    assert [p["nome"] for p in client.get("/pessoas").json()] == ["Laura"]


def test_pessoa_ligada_a_identidade(client: TestClient, session: Session) -> None:
    ident = IdentidadeService(session).criar("erik@exemplo.com", "Erik")
    session.commit()
    r = client.post("/pessoas", json={"nome": "Erik", "identidade_id": ident.id}, headers=LAURA)
    assert r.status_code == 201, r.text
    assert r.json()["login"] == "erik@exemplo.com"
    # a mesma identidade em outra pessoa: 409
    repetida = client.post(
        "/pessoas", json={"nome": "Outro", "identidade_id": ident.id}, headers=LAURA
    )
    assert repetida.status_code == 409
    assert (
        client.post(
            "/pessoas", json={"nome": "Sem", "identidade_id": 9999}, headers=LAURA
        ).status_code
        == 404
    )
    # desligar
    solta = client.patch(f"/pessoas/{r.json()['id']}", json={"identidade_id": None}, headers=LAURA)
    assert solta.json()["identidade_id"] is None and solta.json()["login"] is None


def test_apagar_pessoa_some_das_refeicoes_de_hoje_em_diante(client: TestClient) -> None:
    laura = pessoa(client, "Laura")
    pessoa(client, "Erik")
    arroz = receita(client, "Arroz", [])
    futura = semana(client, SEG)
    passada = semana(client, PASSADA)
    r_futura = refeicao(client, futura["id"], "2026-11-18", "almoco", arroz["id"])
    r_passada = refeicao(client, passada["id"], "2026-11-03", "almoco", arroz["id"])
    assert len(r_futura["pessoas"]) == 2

    client.delete(f"/pessoas/{laura['id']}", headers=LAURA)
    depois = client.get(f"/semanas/{SEG}").json()
    assert [p["nome"] for p in _dias(depois)["2026-11-18"][0]["pessoas"]] == ["Erik"]
    antes = client.get(f"/semanas/{PASSADA}").json()
    assert [p["nome"] for p in _dias(antes)["2026-11-03"][0]["pessoas"]] == ["Erik", "Laura"]
    assert r_passada["porcoes"] == "2.00"


# --- porções ------------------------------------------------------------------


def test_porcao_padrao_e_fator_da_receita(client: TestClient) -> None:
    pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1.5")
    r = receita(client, "Frango", [], rendimento="4")
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-18", "almoco", r["id"])
    assert ref["porcoes"] == "2.50"
    assert ref["fator"] == "0.625"
    assert [(p["nome"], p["porcoes"], p["ajustada"]) for p in ref["pessoas"]] == [
        ("Erik", "1.50", False),
        ("Laura", "1.00", False),
    ]


def test_ajuste_numa_refeicao_muda_so_ela(client: TestClient) -> None:
    laura = pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1.5")
    r = receita(client, "Frango", [], rendimento="1")
    s = semana(client, SEG)
    a = refeicao(client, s["id"], "2026-11-18", "almoco", r["id"])
    b = refeicao(client, s["id"], "2026-11-19", "almoco", r["id"])

    ajuste = client.put(
        f"/refeicoes/{a['id']}/pessoas",
        json=[{"pessoa_id": laura["id"], "porcoes": "2"}]
        + [{"pessoa_id": p["pessoa_id"]} for p in a["pessoas"] if p["nome"] == "Erik"],
        headers=LAURA,
    )
    assert ajuste.status_code == 200, ajuste.text
    corpo = ajuste.json()
    assert corpo["porcoes"] == "3.50"
    assert {p["nome"]: p["ajustada"] for p in corpo["pessoas"]} == {"Laura": True, "Erik": False}

    semana_lida = client.get(f"/semanas/{SEG}").json()
    assert _dias(semana_lida)["2026-11-19"][0]["porcoes"] == b["porcoes"] == "2.50"


def test_refeicao_de_uma_pessoa_so(client: TestClient) -> None:
    laura = pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1.5")
    r = receita(client, "Salada", [], rendimento="2")
    s = semana(client, SEG)
    ref = refeicao(
        client,
        s["id"],
        "2026-11-18",
        "janta",
        r["id"],
        pessoas=[{"pessoa_id": laura["id"]}],
    )
    assert [p["nome"] for p in ref["pessoas"]] == ["Laura"]
    assert ref["porcoes"] == "1.00" and ref["fator"] == "0.500"


def test_mudar_o_perfil_muda_as_refeicoes_nao_ajustadas(client: TestClient) -> None:
    laura = pessoa(client, "Laura", "1")
    erik = pessoa(client, "Erik", "1.5")
    r = receita(client, "Frango", [])
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-18", "almoco", r["id"])
    client.put(
        f"/refeicoes/{ref['id']}/pessoas",
        json=[{"pessoa_id": laura["id"], "porcoes": "2"}, {"pessoa_id": erik["id"]}],
        headers=LAURA,
    )
    outra = refeicao(client, s["id"], "2026-11-19", "almoco", r["id"])

    client.patch(f"/pessoas/{erik['id']}", json={"porcao_padrao": "2"}, headers=LAURA)
    client.patch(f"/pessoas/{laura['id']}", json={"porcao_padrao": "3"}, headers=LAURA)
    lida = client.get(f"/semanas/{SEG}").json()
    dias = _dias(lida)
    assert dias["2026-11-18"][0]["porcoes"] == "4.00"  # Laura ajustada em 2 + Erik 2
    assert dias["2026-11-19"][0]["porcoes"] == "5.00"  # as duas pelo padrão novo
    assert outra["porcoes"] == "2.50"


def test_porcoes_nulas_voltam_ao_padrao(client: TestClient) -> None:
    laura = pessoa(client, "Laura", "1")
    r = receita(client, "Frango", [])
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-18", "almoco", r["id"])
    client.put(
        f"/refeicoes/{ref['id']}/pessoas",
        json=[{"pessoa_id": laura["id"], "porcoes": "2"}],
        headers=LAURA,
    )
    volta = client.put(
        f"/refeicoes/{ref['id']}/pessoas",
        json=[{"pessoa_id": laura["id"], "porcoes": None}],
        headers=LAURA,
    )
    assert volta.json()["pessoas"][0]["ajustada"] is False
    assert volta.json()["porcoes"] == "1.00"


# --- semanas ------------------------------------------------------------------


def test_criar_semana_com_sessao_do_domingo_anterior(client: TestClient) -> None:
    r = client.post("/semanas", json={"inicio": SEG}, headers=LAURA)
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert [s["data"] for s in corpo["sessoes"]] == ["2026-11-15"]
    assert corpo["sessoes"][0]["rotulo"] == "domingo"
    assert corpo["dias"][0]["dia"] == SEG and len(corpo["dias"]) == 7
    assert corpo["passada"] is False

    de_novo = client.post("/semanas", json={"inicio": SEG}, headers=LAURA)
    assert de_novo.status_code == 200 and de_novo.json()["id"] == corpo["id"]
    assert len(de_novo.json()["sessoes"]) == 1


def test_semana_que_nao_comeca_na_segunda_e_422(client: TestClient) -> None:
    assert client.post("/semanas", json={"inicio": "2026-11-17"}, headers=LAURA).status_code == 422
    assert client.get("/semanas/2026-11-17").status_code == 422
    assert client.post("/semanas", json={"inicio": SEG}).status_code == 400


def test_semana_inexistente_diz_que_nao_existe(client: TestClient) -> None:
    r = client.get("/semanas/2026-11-23")
    assert r.status_code == 404
    assert r.json()["existe"] is False


def test_listar_semanas_paginado_com_contagem(client: TestClient) -> None:
    receita_ = receita(client, "Arroz", [])
    a = semana(client, "2026-11-09")
    b = semana(client, SEG)
    semana(client, "2026-11-23")
    refeicao(client, b["id"], "2026-11-16", "almoco", receita_["id"])
    refeicao(client, b["id"], "2026-11-17", "almoco", receita_["id"])
    refeicao(client, a["id"], "2026-11-10", "almoco", observacao="jantar fora")

    pagina = client.get("/semanas", params={"limite": 2}).json()
    assert pagina["total"] == 3
    assert [(s["inicio"], s["refeicoes"], s["passada"]) for s in pagina["items"]] == [
        ("2026-11-23", 0, False),
        (SEG, 2, False),
    ]
    resto = client.get("/semanas", params={"limite": 2, "offset": 2}).json()
    assert [(s["inicio"], s["refeicoes"], s["passada"]) for s in resto["items"]] == [
        ("2026-11-09", 1, True)
    ]


def test_apagar_semana_apaga_as_refeicoes(client: TestClient) -> None:
    r = receita(client, "Arroz", [])
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-16", "almoco", r["id"])
    assert client.delete(f"/semanas/{s['id']}", headers=LAURA).status_code == 200
    assert client.get(f"/semanas/{SEG}").status_code == 404
    assert client.get("/semanas").json()["total"] == 0
    # a mesma segunda pode ser criada de novo
    assert client.post("/semanas", json={"inicio": SEG}, headers=LAURA).status_code == 201


# --- refeições ----------------------------------------------------------------


def test_refeicao_varios_pratos_no_mesmo_almoco(client: TestClient) -> None:
    pessoa(client, "Laura")
    arroz = receita(client, "Arroz", [])
    feijao = receita(client, "Feijão", [])
    s = semana(client, SEG)
    a = refeicao(client, s["id"], "2026-11-18", "almoco", arroz["id"])
    b = refeicao(client, s["id"], "2026-11-18", "almoco", feijao["id"])
    assert (a["ordem"], b["ordem"]) == (0, 1)
    refeicao(client, s["id"], "2026-11-18", "cafe_da_manha", observacao="pão com ovo")
    do_dia = _dias(client.get(f"/semanas/{SEG}").json())["2026-11-18"]
    assert [r["tipo"] for r in do_dia] == ["cafe_da_manha", "almoco", "almoco"]
    assert [r["receita"]["nome"] if r["receita"] else None for r in do_dia] == [
        None,
        "Arroz",
        "Feijão",
    ]


def test_refeicao_validacoes(client: TestClient) -> None:
    receita(client, "Arroz", [])
    s = semana(client, SEG)

    def post(corpo: dict[str, object]) -> int:
        return int(
            client.post(f"/semanas/{s['id']}/refeicoes", json=corpo, headers=LAURA).status_code
        )

    assert (
        post({"dia": "2026-11-23", "tipo": "almoco", "observacao": "fora"}) == 422
    )  # fora da semana
    assert post({"dia": "2026-11-15", "tipo": "almoco", "observacao": "fora"}) == 422
    assert post({"dia": "2026-11-18", "tipo": "almoco"}) == 422  # nada a comer
    assert post({"dia": "2026-11-18", "tipo": "almoco", "receita_id": 9999}) == 404
    assert post({"dia": "2026-11-18", "tipo": "ceia", "observacao": "x"}) == 422
    assert (
        post(
            {
                "dia": "2026-11-18",
                "tipo": "almoco",
                "observacao": "x",
                "pessoas": [{"pessoa_id": 9999}],
            }
        )
        == 404
    )


def test_patch_refeicao(client: TestClient) -> None:
    arroz = receita(client, "Arroz", [])
    feijao = receita(client, "Feijão", [])
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-18", "almoco", arroz["id"])

    r = client.patch(
        f"/refeicoes/{ref['id']}",
        json={"dia": "2026-11-20", "tipo": "janta", "receita_id": feijao["id"], "ordem": 3},
        headers=LAURA,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["dia"], corpo["tipo"], corpo["receita"]["nome"], corpo["ordem"]) == (
        "2026-11-20",
        "janta",
        "Feijão",
        3,
    )
    assert (
        client.patch(
            f"/refeicoes/{ref['id']}", json={"dia": "2026-11-23"}, headers=LAURA
        ).status_code
        == 422
    )
    # sem receita precisa de observação
    assert (
        client.patch(
            f"/refeicoes/{ref['id']}", json={"receita_id": None}, headers=LAURA
        ).status_code
        == 422
    )
    ok = client.patch(
        f"/refeicoes/{ref['id']}", json={"receita_id": None, "observacao": "sobras"}, headers=LAURA
    )
    assert ok.status_code == 200 and ok.json()["receita"] is None


def test_apagar_refeicao(client: TestClient) -> None:
    arroz = receita(client, "Arroz", [])
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-18", "almoco", arroz["id"])
    r = client.delete(f"/refeicoes/{ref['id']}", headers=LAURA)
    assert r.status_code == 200 and r.json()["deleted_em"] is not None
    assert _dias(client.get(f"/semanas/{SEG}").json())["2026-11-18"] == []
    assert client.delete(f"/refeicoes/{ref['id']}", headers=LAURA).status_code == 404


def test_editar_refeicao_de_semana_passada_e_permitido(client: TestClient) -> None:
    arroz = receita(client, "Arroz", [])
    s = semana(client, PASSADA)
    assert s["passada"] is True
    ref = refeicao(client, s["id"], "2026-11-03", "almoco", arroz["id"])
    r = client.patch(f"/refeicoes/{ref['id']}", json={"tipo": "janta"}, headers=LAURA)
    assert r.status_code == 200 and r.json()["tipo"] == "janta"


def test_trigger_recusa_dia_fora_da_semana(session: Session, client: TestClient) -> None:
    from sqlalchemy.exc import DBAPIError

    s = semana(client, SEG)
    try:
        session.execute(
            text(
                "INSERT INTO compras.refeicoes (semana_id, dia, tipo, observacao) "
                "VALUES (:s, '2026-11-30', 'almoco', 'x')"
            ),
            {"s": s["id"]},
        )
    except DBAPIError as erro:
        assert getattr(erro.orig, "sqlstate", None) == "23514"
    else:
        raise AssertionError("o trigger deveria recusar")
    session.rollback()


# --- sessões ------------------------------------------------------------------


def test_sessoes_de_preparo(client: TestClient) -> None:
    s = semana(client, SEG)
    nova = client.post(
        f"/semanas/{s['id']}/sessoes",
        json={"data": "2026-11-18", "rotulo": "quarta à noite"},
        headers=LAURA,
    )
    assert nova.status_code == 201, nova.text
    assert (
        client.post(
            f"/semanas/{s['id']}/sessoes", json={"data": "2026-11-18"}, headers=LAURA
        ).status_code
        == 409
    )
    for fora in ("2026-11-13", "2026-11-23"):
        assert (
            client.post(
                f"/semanas/{s['id']}/sessoes", json={"data": fora}, headers=LAURA
            ).status_code
            == 422
        )
    sabado = client.post(f"/semanas/{s['id']}/sessoes", json={"data": "2026-11-14"}, headers=LAURA)
    assert sabado.status_code == 201

    mudada = client.patch(
        f"/sessoes/{nova.json()['id']}",
        json={"data": "2026-11-19", "rotulo": "quinta"},
        headers=LAURA,
    )
    assert (mudada.json()["data"], mudada.json()["rotulo"]) == ("2026-11-19", "quinta")
    assert (
        client.patch(
            f"/sessoes/{nova.json()['id']}", json={"data": "2026-11-14"}, headers=LAURA
        ).status_code
        == 409
    )

    assert client.delete(f"/sessoes/{nova.json()['id']}", headers=LAURA).json()["deleted_em"]
    datas = [x["data"] for x in client.get(f"/semanas/{SEG}").json()["sessoes"]]
    assert datas == ["2026-11-14", "2026-11-15"]


# --- receita e semana passada ----------------------------------------------------


def _por_sql(session: Session, sql: str, **params: object) -> None:
    session.execute(text(sql), params)
    session.commit()


def test_editar_receita_nao_muda_os_ingredientes_da_semana_passada(
    client: TestClient, session: Session, hoje: Callable[[date], None]
) -> None:
    pessoa(client, "Laura")
    cebola = produto(client, "Cebola", "kg", "g", "150")
    r = receita(client, "Refogado", [ingrediente(cebola, "1", "un")])
    passada = semana(client, PASSADA)
    atual = semana(client, SEG)
    refeicao(client, passada["id"], "2026-11-03", "almoco", r["id"])
    refeicao(client, atual["id"], "2026-11-17", "almoco", r["id"])

    # a receita nasceu antes da semana passada acabar
    _por_sql(session, "UPDATE compras.receita_ingredientes SET criado_em = '2026-10-01'")

    corpo = {
        "nome": "Refogado",
        "tipo": "almoco",
        "rendimento_porcoes": "1",
        "ingredientes": [ingrediente(cebola, "3", "un")],
    }
    assert client.put(f"/receitas/{r['id']}", json=corpo, headers=LAURA).status_code == 200
    # a edição aconteceu depois do domingo da semana passada (08/11)
    _por_sql(
        session,
        "UPDATE compras.receita_ingredientes SET deleted_em = '2026-11-12' "
        "WHERE deleted_em IS NOT NULL",
    )
    _por_sql(
        session,
        "UPDATE compras.receita_ingredientes SET criado_em = '2026-11-12' WHERE deleted_em IS NULL",
    )

    def quantidade(inicio: str, dia: str) -> list[str]:
        lida = client.get(f"/semanas/{inicio}", params={"ingredientes": "true"}).json()
        receita_lida = _dias(lida)[dia][0]["receita"]
        return [i["quantidade"] for i in receita_lida["ingredientes"]]

    assert quantidade(PASSADA, "2026-11-03") == ["1.000"]
    assert quantidade(SEG, "2026-11-17") == ["3.000"]
    # sem o parâmetro, a receita vem sem ingredientes
    sem = client.get(f"/semanas/{SEG}").json()
    assert _dias(sem)["2026-11-17"][0]["receita"]["ingredientes"] is None


def test_apagar_receita_em_semana_que_nao_acabou_e_409(
    client: TestClient, hoje: Callable[[date], None]
) -> None:
    arroz = receita(client, "Arroz", [])
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-18", "almoco", arroz["id"])
    r = client.delete(f"/receitas/{arroz['id']}", headers=LAURA)
    assert r.status_code == 409
    assert r.json()["semanas"] == [{"id": s["id"], "inicio": SEG}]

    # a semana passa: agora pode
    hoje(date(2026, 11, 23))
    assert client.delete(f"/receitas/{arroz['id']}", headers=LAURA).status_code == 200


# --- copiar -------------------------------------------------------------------


def test_copiar_semana(client: TestClient) -> None:
    laura = pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1.5")
    arroz = receita(client, "Arroz", [])
    feijao = receita(client, "Feijão", [])
    origem = semana(client, SEG)
    a = refeicao(client, origem["id"], "2026-11-16", "almoco", arroz["id"])
    refeicao(client, origem["id"], "2026-11-18", "janta", feijao["id"])
    refeicao(client, origem["id"], "2026-11-22", "almoco", observacao="jantar fora")
    client.put(
        f"/refeicoes/{a['id']}/pessoas",
        json=[
            {"pessoa_id": laura["id"], "porcoes": "2"},
            {"pessoa_id": next(p["pessoa_id"] for p in a["pessoas"] if p["nome"] == "Erik")},
        ],
        headers=LAURA,
    )

    r = client.post(
        f"/semanas/{origem['id']}/copiar", json={"destino": "2026-11-23"}, headers=LAURA
    )
    assert r.status_code == 201, r.text
    copia = r.json()
    assert copia["inicio"] == "2026-11-23" and copia["avisos"] == []
    dias = _dias(copia)
    assert [x["receita"]["nome"] for x in dias["2026-11-23"]] == ["Arroz"]
    assert [x["receita"]["nome"] for x in dias["2026-11-25"]] == ["Feijão"]
    assert dias["2026-11-29"][0]["observacao"] == "jantar fora"
    ajustes = {p["nome"]: (p["porcoes"], p["ajustada"]) for p in dias["2026-11-23"][0]["pessoas"]}
    assert ajustes == {"Laura": ("2.00", True), "Erik": ("1.50", False)}
    # a sessão da origem (domingo 15) vai para o domingo 22; a origem fica como estava
    assert [s["data"] for s in copia["sessoes"]] == ["2026-11-22"]
    assert len(_dias(client.get(f"/semanas/{SEG}").json())["2026-11-16"]) == 1


def test_copiar_para_destino_ocupado_e_409(client: TestClient) -> None:
    arroz = receita(client, "Arroz", [])
    origem = semana(client, SEG)
    refeicao(client, origem["id"], "2026-11-16", "almoco", arroz["id"])
    destino = semana(client, "2026-11-23")
    refeicao(client, destino["id"], "2026-11-24", "almoco", arroz["id"])
    r = client.post(
        f"/semanas/{origem['id']}/copiar", json={"destino": "2026-11-23"}, headers=LAURA
    )
    assert r.status_code == 409
    assert r.json()["semana"]["id"] == destino["id"]
    assert len(_dias(client.get("/semanas/2026-11-23").json())["2026-11-24"]) == 1


def test_copiar_para_destino_vazio_que_ja_existe(client: TestClient) -> None:
    arroz = receita(client, "Arroz", [])
    origem = semana(client, SEG)
    refeicao(client, origem["id"], "2026-11-16", "almoco", arroz["id"])
    destino = semana(client, "2026-11-23")  # já tem a sessão do domingo 22
    r = client.post(
        f"/semanas/{origem['id']}/copiar", json={"destino": "2026-11-23"}, headers=LAURA
    )
    assert r.status_code == 201
    assert r.json()["id"] == destino["id"]
    assert [s["data"] for s in r.json()["sessoes"]] == ["2026-11-22"]  # sem duplicar


def test_copiar_validacoes(client: TestClient) -> None:
    origem = semana(client, SEG)
    assert (
        client.post(
            f"/semanas/{origem['id']}/copiar", json={"destino": "2026-11-24"}, headers=LAURA
        ).status_code
        == 422
    )
    assert (
        client.post(
            f"/semanas/{origem['id']}/copiar", json={"destino": SEG}, headers=LAURA
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/semanas/9999/copiar", json={"destino": "2026-11-23"}, headers=LAURA
        ).status_code
        == 404
    )


def test_copiar_receita_apagada_vira_aviso(client: TestClient) -> None:
    pessoa(client, "Laura")
    velha = receita(client, "Sopa antiga", [])
    passada = semana(client, PASSADA)
    refeicao(client, passada["id"], "2026-11-03", "janta", velha["id"])
    # a semana já passou: apagar a receita é permitido
    assert client.delete(f"/receitas/{velha['id']}", headers=LAURA).status_code == 200

    r = client.post(
        f"/semanas/{passada['id']}/copiar", json={"destino": "2026-11-23"}, headers=LAURA
    )
    assert r.status_code == 201, r.text
    copiada = _dias(r.json())["2026-11-24"][0]
    assert copiada["receita"] is None
    assert copiada["observacao"] == "receita apagada: Sopa antiga"
    assert [a["texto"] for a in r.json()["avisos"]] == ["receita apagada: Sopa antiga"]
    assert r.json()["avisos"][0]["refeicao_id"] == copiada["id"]
