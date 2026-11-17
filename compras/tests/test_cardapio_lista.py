"""A lista de compras gerada pelo cardápio (modelo-cardapio.md, "Geração da lista")."""

import threading
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.main import app
from tests.apoio import (
    ERIK,
    LAURA,
    adicionar,
    ingrediente,
    pessoa,
    produto,
    receita,
    refeicao,
    semana,
)

SEG = "2026-11-16"
PASSADA = "2026-11-02"
D = Decimal


def _base(client: TestClient) -> dict[str, Any]:
    """Duas pessoas (2 porções por refeição), cebola, leite e uma receita simples.

    Uma refeição: cebola 2 x 150 g = 300 g (0,300 kg); leite 2 x 500 ml = 1.000 ml (1 un).
    """
    pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1")
    cebola = produto(client, "Cebola", "kg", "g", "150")
    leite = produto(client, "Leite integral 1L", "un", "ml", "1000")
    creme = receita(
        client,
        "Creme",
        [ingrediente(cebola, "1", "un"), ingrediente(leite, "500", "ml")],
    )
    s = semana(client, SEG)
    return {"cebola": cebola, "leite": leite, "receita": creme, "semana": s["id"]}


def _comer(client: TestClient, cenario: dict[str, Any], dia: str = "2026-11-16") -> dict[str, Any]:
    return refeicao(client, cenario["semana"], dia, "almoco", cenario["receita"]["id"])


def _gerar(client: TestClient, semana_id: int, quem: dict[str, str] = LAURA) -> dict[str, Any]:
    r = client.post(f"/semanas/{semana_id}/lista", headers=quem)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _previa(client: TestClient, semana_id: int) -> dict[str, Any]:
    r = client.get(f"/semanas/{semana_id}/lista")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _pendentes(client: TestClient) -> dict[str, dict[str, Any]]:
    itens = client.get("/lista").json()["itens"]
    return {i["produto_nome"]: i for i in itens if i["situacao"] == "pendente"}


def _por_produto(lista: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {x["produto"]: x for x in lista}


def _contribuicoes(session: Session, semana_id: int) -> list[tuple[Any, ...]]:
    linhas = session.execute(
        text(
            "SELECT item_lista_id, quantidade, unidade, deleted_em IS NOT NULL, gerado_por "
            "FROM compras.itens_lista_cardapio WHERE semana_id = :s ORDER BY id"
        ),
        {"s": semana_id},
    ).all()
    return [tuple(x) for x in linhas]


# --- soma, conversão e o que não converte -----------------------------------------


def test_gera_a_lista_convertendo_para_a_unidade_de_compra(client: TestClient) -> None:
    pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1")
    cebola = produto(client, "Cebola", "kg", "g", "150")
    leite = produto(client, "Leite integral 1L", "un", "ml", "1000")
    arroz = produto(client, "Arroz 5kg", "un", "g", "5000")
    farinha = produto(client, "Farinha de trigo 1kg", "un", "g", "1000")
    sal = produto(client, "Sal", "un")
    r = receita(
        client,
        "Arroz de forno",
        [
            ingrediente(cebola, "2", "un"),
            ingrediente(leite, "250", "ml"),
            ingrediente(arroz, "70", "g"),
            ingrediente(farinha, "2", "colher_sopa"),
            ingrediente(sal, None, "a_gosto"),
        ],
    )
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-17", "almoco", r["id"])

    previa = _previa(client, s["id"])
    assert client.get("/lista").json()["itens"] == []  # a prévia não grava
    resposta = _gerar(client, s["id"])
    assert [c["produto"] for c in previa["criados"]] == [c["produto"] for c in resposta["criados"]]
    assert all(c["item_id"] is None for c in previa["criados"])

    criados = _por_produto(resposta["criados"])
    assert set(criados) == {
        "Cebola",
        "Leite integral 1L",
        "Arroz 5kg",
        "Farinha de trigo 1kg",
        "Sal",
    }
    assert (criados["Cebola"]["quantidade"], criados["Cebola"]["unidade"]) == ("0.600", "kg")
    assert (
        criados["Leite integral 1L"]["quantidade"],
        criados["Leite integral 1L"]["unidade"],
    ) == (
        "1.000",
        "un",
    )
    assert criados["Arroz 5kg"]["quantidade"] == "1.000"  # 140 g de 5 kg: a embalagem inteira
    assert criados["Cebola"]["de"] == ["Arroz de forno"]
    assert criados["Farinha de trigo 1kg"]["quantidade"] is None
    assert criados["Sal"]["quantidade"] is None

    assert [(a["produto"], a["texto"]) for a in resposta["avisos"]] == [
        ("Farinha de trigo 1kg", "cadastre a medida: 4 colher_sopa não converte para g")
    ]

    itens = _pendentes(client)
    assert all(i["origem"] == "cardapio" and i["adicionado_por"] == "Laura" for i in itens.values())
    assert itens["Cebola"]["quantidade"] == "0.600"
    assert itens["Farinha de trigo 1kg"]["quantidade"] is None
    assert itens["Farinha de trigo 1kg"]["observacao"] == "cardápio: 4 colher_sopa"
    assert itens["Sal"]["observacao"] == "cardápio: a gosto"


def test_soma_por_produto_na_base_antes_de_converter(client: TestClient) -> None:
    """Duas receitas com cebola: a soma é em gramas, e só então vira kg."""
    pessoa(client, "Laura", "1")
    cebola = produto(client, "Cebola", "kg", "g", "150")
    a = receita(client, "Sopa", [ingrediente(cebola, "1", "un")])
    b = receita(client, "Refogado", [ingrediente(cebola, "200", "g")])
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-16", "almoco", a["id"])
    refeicao(client, s["id"], "2026-11-17", "almoco", b["id"])
    criado = _gerar(client, s["id"])["criados"][0]
    assert criado["quantidade"] == "0.350"  # 150 g + 200 g
    assert criado["de"] == ["Sopa", "Refogado"]


def test_fator_usa_porcoes_e_rendimento(client: TestClient) -> None:
    pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1.5")
    arroz = produto(client, "Arroz", "kg", "g", None)
    r = receita(client, "Arroz", [ingrediente(arroz, "400", "g")], rendimento="4")
    s = semana(client, SEG)
    refeicao(client, s["id"], "2026-11-16", "almoco", r["id"])
    # fator 2,5 / 4 = 0,625: 400 g x 0,625 = 250 g
    assert _gerar(client, s["id"])["criados"][0]["quantidade"] == "0.250"


def test_refeicao_sem_receita_nao_entra(client: TestClient) -> None:
    c = _base(client)
    refeicao(client, c["semana"], "2026-11-16", "almoco", observacao="jantar fora")
    resposta = _gerar(client, c["semana"])
    assert resposta == {
        "criados": [],
        "ajustados": [],
        "sem_mudanca": [],
        "confira": [],
        "avisos": [],
    }


# --- repetir -------------------------------------------------------------------


def test_gerar_duas_vezes_nao_duplica(client: TestClient, session: Session) -> None:
    c = _base(client)
    _comer(client, c)
    primeira = _gerar(client, c["semana"])
    assert len(primeira["criados"]) == 2

    segunda = _gerar(client, c["semana"])
    assert segunda["criados"] == [] and segunda["ajustados"] == []
    assert {x["produto"] for x in segunda["sem_mudanca"]} == {"Cebola", "Leite integral 1L"}
    assert len(client.get("/lista").json()["itens"]) == 2
    assert len(_contribuicoes(session, c["semana"])) == 2
    # e a prévia, depois de gerada, também não vê mudança
    previa = _previa(client, c["semana"])
    assert previa["criados"] == [] and previa["ajustados"] == []


def test_aumentar_uma_refeicao_aplica_so_a_diferenca(client: TestClient, session: Session) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    _gerar(client, c["semana"])
    _comer(client, c, "2026-11-17")

    previa = _previa(client, c["semana"])
    assert {a["produto"] for a in previa["ajustados"]} == {"Cebola", "Leite integral 1L"}
    resposta = _gerar(client, c["semana"])
    ajustados = _por_produto(resposta["ajustados"])
    assert (ajustados["Cebola"]["antes"], ajustados["Cebola"]["depois"]) == ("0.300", "0.600")
    assert (ajustados["Leite integral 1L"]["antes"], ajustados["Leite integral 1L"]["depois"]) == (
        "1.000",
        "2.000",
    )
    assert ajustados["Cebola"]["origem_item"] == "cardapio"
    itens = _pendentes(client)
    assert len(itens) == 2 and itens["Cebola"]["quantidade"] == "0.600"
    contribs = _contribuicoes(session, c["semana"])
    assert sorted(x[1] for x in contribs) == [D("0.600"), D("2.000")]
    assert all(x[4] == "Laura" for x in contribs)

    de_novo = _gerar(client, c["semana"])
    assert de_novo["ajustados"] == [] and len(de_novo["sem_mudanca"]) == 2


def test_tirar_uma_refeicao_subtrai(client: TestClient) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    segunda = _comer(client, c, "2026-11-17")
    _gerar(client, c["semana"])
    assert _pendentes(client)["Cebola"]["quantidade"] == "0.600"

    client.delete(f"/refeicoes/{segunda['id']}", headers=LAURA)
    resposta = _gerar(client, c["semana"])
    cebola = _por_produto(resposta["ajustados"])["Cebola"]
    assert (cebola["antes"], cebola["depois"], cebola["removido"]) == ("0.600", "0.300", False)
    assert _pendentes(client)["Cebola"]["quantidade"] == "0.300"
    assert _pendentes(client)["Leite integral 1L"]["quantidade"] == "1.000"


def test_item_so_do_cardapio_que_zera_sai_da_lista(client: TestClient, session: Session) -> None:
    c = _base(client)
    unica = _comer(client, c)
    _gerar(client, c["semana"])
    client.delete(f"/refeicoes/{unica['id']}", headers=LAURA)

    resposta = _gerar(client, c["semana"])
    assert {a["produto"] for a in resposta["ajustados"] if a["removido"]} == {
        "Cebola",
        "Leite integral 1L",
    }
    assert _pendentes(client) == {}
    assert all(x[3] for x in _contribuicoes(session, c["semana"]))  # linhas da semana apagadas

    # a refeição volta: o item volta, como item novo do cardápio
    _comer(client, c)
    de_volta = _gerar(client, c["semana"])
    assert {x["produto"] for x in de_volta["criados"]} == {"Cebola", "Leite integral 1L"}


def test_subtrair_nao_passa_do_que_a_semana_pos(client: TestClient) -> None:
    """O item tinha 1 un à mão; o cardápio somou 1; tirar a refeição devolve só o 1 dele."""
    c = _base(client)
    adicionar(client, quantidade="1", unidade="un", produto_id=c["leite"])
    refeicao_ = _comer(client, c)
    _gerar(client, c["semana"])
    assert _pendentes(client)["Leite integral 1L"]["quantidade"] == "2.000"

    client.delete(f"/refeicoes/{refeicao_['id']}", headers=LAURA)
    resposta = _gerar(client, c["semana"])
    leite = _por_produto(resposta["ajustados"])["Leite integral 1L"]
    assert (leite["antes"], leite["depois"], leite["removido"]) == ("2.000", "1.000", False)
    item = _pendentes(client)["Leite integral 1L"]
    assert item["quantidade"] == "1.000" and item["origem"] == "manual"  # o item à mão fica


def test_item_comprado_nao_volta_a_pendente(client: TestClient) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    resposta = _gerar(client, c["semana"])
    cebola = _por_produto(resposta["criados"])["Cebola"]
    assert client.post(f"/lista/itens/{cebola['item_id']}/comprar", headers=ERIK).status_code == 200

    de_novo = _gerar(client, c["semana"])
    assert "Cebola" in _por_produto(de_novo["sem_mudanca"])
    assert "Cebola" not in _pendentes(client)

    # tirar a refeição não desfaz o que foi comprado
    # (sem mudança no pedido: só o aumento recria, e só pela diferença)
    _comer(client, c, "2026-11-17")
    aumento = _gerar(client, c["semana"])
    nova = _por_produto(aumento["criados"])["Cebola"]
    assert nova["quantidade"] == "0.300" and nova["item_id"] != cebola["item_id"]
    comprados = [i for i in client.get("/lista").json()["itens"] if i["situacao"] == "comprado"]
    assert [i["quantidade"] for i in comprados if i["produto_nome"] == "Cebola"] == ["0.300"]
    assert _pendentes(client)["Cebola"]["quantidade"] == "0.300"


def test_tirar_refeicao_com_item_ja_comprado_nao_mexe(client: TestClient) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    segunda = _comer(client, c, "2026-11-17")
    resposta = _gerar(client, c["semana"])
    cebola = _por_produto(resposta["criados"])["Cebola"]
    client.post(f"/lista/itens/{cebola['item_id']}/comprar", headers=ERIK)
    client.delete(f"/refeicoes/{segunda['id']}", headers=LAURA)

    depois = _gerar(client, c["semana"])
    assert "Cebola" in _por_produto(depois["sem_mudanca"])
    assert "Cebola" not in _por_produto(depois["ajustados"])
    comprado = next(
        i for i in client.get("/lista").json()["itens"] if i["produto_nome"] == "Cebola"
    )
    assert comprado["situacao"] == "comprado" and comprado["quantidade"] == "0.600"


def test_item_removido_a_mao_nao_volta(client: TestClient) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    resposta = _gerar(client, c["semana"])
    cebola = _por_produto(resposta["criados"])["Cebola"]
    assert client.delete(f"/lista/itens/{cebola['item_id']}", headers=LAURA).status_code == 200

    de_novo = _gerar(client, c["semana"])
    assert "Cebola" in _por_produto(de_novo["sem_mudanca"])
    assert "Cebola" not in _pendentes(client)

    # só volta se o pedido aumentar, e só pela diferença
    _comer(client, c, "2026-11-17")
    aumento = _gerar(client, c["semana"])
    assert _por_produto(aumento["criados"])["Cebola"]["quantidade"] == "0.300"


# --- despensa -------------------------------------------------------------------


def test_despensa_tem_vai_para_confira_e_nao_cria_item(client: TestClient) -> None:
    c = _base(client)
    client.put(f"/despensa/{c['cebola']}", json={"estado": "tem"}, headers=LAURA)
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    assert [x["produto"] for x in resposta["criados"]] == ["Leite integral 1L"]
    assert resposta["confira"] == [
        {
            "produto": "Cebola",
            "estado_despensa": "tem",
            "pedido": "0.300",
            "unidade": "kg",
            "texto": "provavelmente já tem, confira",
            "de": ["Creme"],
        }
    ]
    assert "Cebola" not in _pendentes(client)
    # a prévia diz o mesmo
    assert _previa(client, c["semana"])["confira"][0]["produto"] == "Cebola"


def test_despensa_acabando_entra_na_lista(client: TestClient) -> None:
    c = _base(client)
    client.put(f"/despensa/{c['cebola']}", json={"estado": "acabando"}, headers=LAURA)
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    assert "Cebola" in _por_produto(resposta["criados"])
    assert resposta["confira"] == []


def test_despensa_acabou_ja_tem_item_e_a_geracao_o_ajusta(client: TestClient) -> None:
    c = _base(client)
    pos = client.put(f"/despensa/{c['cebola']}", json={"estado": "acabou"}, headers=LAURA)
    assert pos.json()["item_criado"]["origem"] == "despensa"
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    assert "Cebola" not in _por_produto(resposta["criados"])
    cebola = _por_produto(resposta["ajustados"])["Cebola"]
    assert cebola["origem_item"] == "despensa"  # quem pôs primeiro continua valendo
    assert len(_pendentes(client)) == 2


def test_despensa_tem_com_pendente_existente_ajusta(client: TestClient) -> None:
    c = _base(client)
    client.put(f"/despensa/{c['leite']}", json={"estado": "tem"}, headers=LAURA)
    adicionar(client, quantidade="1", unidade="un", produto_id=c["leite"])  # já está na lista
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    assert resposta["confira"] == []
    leite = _por_produto(resposta["ajustados"])["Leite integral 1L"]
    assert (leite["antes"], leite["depois"]) == ("1.000", "2.000")


# --- pendente único ---------------------------------------------------------------


def test_produto_ja_na_lista_a_mao_recebe_a_quantidade(
    client: TestClient, session: Session
) -> None:
    c = _base(client)
    manual = adicionar(
        client, quantidade="1", unidade="un", produto_id=c["leite"], quem=ERIK
    ).json()
    _comer(client, c)
    resposta = _gerar(client, c["semana"])

    assert "Leite integral 1L" not in _por_produto(resposta["criados"])
    leite = _por_produto(resposta["ajustados"])["Leite integral 1L"]
    assert leite["item_id"] == manual["id"] and leite["origem_item"] == "manual"
    assert (leite["antes"], leite["depois"]) == ("1.000", "2.000")

    itens = client.get("/lista").json()["itens"]
    leites = [i for i in itens if i["produto_nome"] == "Leite integral 1L"]
    assert len(leites) == 1
    assert leites[0]["origem"] == "manual" and leites[0]["adicionado_por"] == "Erik"
    # o cardápio fica registrado na tabela nova
    linhas = _contribuicoes(session, c["semana"])
    assert (manual["id"], D("1.000"), "un", False, "Laura") in linhas


def test_item_existente_sem_quantidade_continua_sem(client: TestClient, session: Session) -> None:
    c = _base(client)
    manual = adicionar(client, produto_id=c["leite"]).json()  # "o de sempre"
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    leite = _por_produto(resposta["ajustados"])["Leite integral 1L"]
    assert leite["antes"] is None and leite["depois"] is None
    assert _pendentes(client)["Leite integral 1L"]["quantidade"] is None
    assert (manual["id"], D("1.000"), "un", False, "Laura") in _contribuicoes(session, c["semana"])
    # repetir não muda nada
    assert _gerar(client, c["semana"])["ajustados"] == []


def test_item_existente_em_unidade_que_nao_converte_nao_soma(
    client: TestClient, session: Session
) -> None:
    c = _base(client)
    manual = adicionar(client, quantidade="3", unidade="un", produto_id=c["cebola"]).json()
    _comer(client, c)
    resposta = _gerar(client, c["semana"])
    cebola = _por_produto(resposta["ajustados"])["Cebola"]
    assert (cebola["antes"], cebola["depois"]) == ("3.000", "3.000")  # não soma
    assert _pendentes(client)["Cebola"]["quantidade"] == "3.000"
    # a linha guarda o pedido, na unidade do pedido
    assert (manual["id"], D("0.300"), "kg", False, "Laura") in _contribuicoes(session, c["semana"])
    assert _gerar(client, c["semana"])["ajustados"] == []


# --- semana passada ---------------------------------------------------------------


def test_semana_passada_recusa_previa_e_geracao(client: TestClient) -> None:
    pessoa(client, "Laura")
    cebola = produto(client, "Cebola", "kg", "g", "150")
    r = receita(client, "Sopa", [ingrediente(cebola, "1", "un")])
    s = semana(client, PASSADA)
    refeicao(client, s["id"], "2026-11-03", "almoco", r["id"])
    for resposta in (
        client.get(f"/semanas/{s['id']}/lista"),
        client.post(f"/semanas/{s['id']}/lista", headers=LAURA),
    ):
        assert resposta.status_code == 409, resposta.text
        assert "passou" in resposta.json()["detail"]
    assert client.get("/lista").json()["itens"] == []


def test_a_semana_gera_ate_o_domingo_e_passa_na_segunda(
    client: TestClient, hoje: Callable[[date], None]
) -> None:
    c = _base(client)
    _comer(client, c)
    hoje(date(2026, 11, 22))  # domingo da semana: ainda gera
    assert client.get(f"/semanas/{c['semana']}/lista").status_code == 200
    hoje(date(2026, 11, 23))  # segunda: passou
    assert client.get(f"/semanas/{c['semana']}/lista").status_code == 409
    assert client.post(f"/semanas/{c['semana']}/lista", headers=LAURA).status_code == 409
    assert client.post("/semanas/9999/lista", headers=LAURA).status_code == 404
    assert client.get("/semanas/9999/lista").status_code == 404
    assert client.post(f"/semanas/{c['semana']}/lista").status_code == 400  # sem X-Quem


# --- concorrência ---------------------------------------------------------------------


def _corrida(semanas: list[int]) -> list[tuple[int, dict[str, Any]]]:
    """Um POST da lista por semana, no mesmo instante, cada um com a sua conexão."""
    largada = threading.Barrier(len(semanas))
    respostas: list[tuple[int, dict[str, Any]]] = []

    def celular(semana_id: int, quem: dict[str, str]) -> None:
        with TestClient(app) as c:
            largada.wait()
            r = c.post(f"/semanas/{semana_id}/lista", headers=quem)
            respostas.append((r.status_code, r.json()))

    fios = [
        threading.Thread(target=celular, args=(s, q))
        for s, q in zip(semanas, (LAURA, ERIK), strict=False)
    ]
    for f in fios:
        f.start()
    for f in fios:
        f.join(timeout=60)
    return respostas


def test_duas_geracoes_da_mesma_semana_dao_o_resultado_de_uma(
    client: TestClient, session: Session
) -> None:
    c = _base(client)
    _comer(client, c, "2026-11-16")
    _comer(client, c, "2026-11-17")

    respostas = _corrida([c["semana"], c["semana"]])
    assert [s for s, _ in respostas] == [200, 200]
    com_criados = [r for _, r in respostas if r["criados"]]
    sem_nada = [r for _, r in respostas if not r["criados"]]
    assert len(com_criados) == 1 and len(sem_nada) == 1
    assert len(sem_nada[0]["sem_mudanca"]) == 2 and sem_nada[0]["ajustados"] == []

    itens = _pendentes(client)
    assert set(itens) == {"Cebola", "Leite integral 1L"}
    assert itens["Cebola"]["quantidade"] == "0.600"
    assert len(client.get("/lista").json()["itens"]) == 2
    assert len(_contribuicoes(session, c["semana"])) == 2


def test_duas_semanas_gerando_o_mesmo_produto_viram_um_item(
    client: TestClient, session: Session
) -> None:
    """O pendente único vale entre semanas: o item é um, com a soma das duas."""
    c = _base(client)
    outra = semana(client, "2026-11-23")["id"]
    _comer(client, c, "2026-11-16")
    refeicao(client, outra, "2026-11-23", "almoco", c["receita"]["id"])

    respostas = _corrida([c["semana"], outra])
    assert [s for s, _ in respostas] == [200, 200]

    itens = client.get("/lista").json()["itens"]
    assert sorted(i["produto_nome"] for i in itens) == ["Cebola", "Leite integral 1L"]
    assert _pendentes(client)["Cebola"]["quantidade"] == "0.600"
    assert _pendentes(client)["Leite integral 1L"]["quantidade"] == "2.000"
    assert len(_contribuicoes(session, c["semana"])) == 2
    assert len(_contribuicoes(session, outra)) == 2
