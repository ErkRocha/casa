"""Conferência da lista pela nota e "comprado, aguardando nota" (D-33).

SEFAZ falsa e páginas inventadas, como em `test_notas`. O tempo é o do banco:
as notas são emitidas "há 1 hora" (depois da marcação menos 1 dia), e o que
precisa ser mais velho é recuado por SQL.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.nfce.leitor_svrs import FUSO
from tests.apoio import ERIK, LAURA, produto
from tests.apoio_compra import acompanhar, comprar, despensa, na_lista, recuar_compra
from tests.nfce_apoio import CNPJ_A, CNPJ_B, ConsultaFalsa, Item
from tests.test_notas import associar, nota_lida


def _emissao(delta: timedelta = timedelta(hours=-1)) -> str:
    return (datetime.now(FUSO) + delta).strftime("%d/%m/%Y %H:%M:%S")


def _nota(
    client: TestClient,
    consulta: ConsultaFalsa,
    linhas: list[tuple[Item, int | None]],
    *,
    numero: int = 1,
    cnpj: str = CNPJ_A,
    emissao: str | None = None,
) -> dict[str, Any]:
    """Nota lida, com cada linha associada ao produto dado (None: sem associar)."""
    nota = nota_lida(
        client,
        consulta,
        [i for i, _ in linhas],
        numero=numero,
        cnpj=cnpj,
        emissao=emissao or _emissao(),
    )
    for n, (_, pid) in enumerate(linhas, start=1):
        if pid is not None:
            r = associar(client, nota, n, pid)
            assert r.status_code == 200, r.text
    return nota


def _previa(client: TestClient, nota: dict[str, Any]) -> dict[str, Any]:
    r = client.get(f"/notas/{nota['id']}/conferencia")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _confirmar(
    client: TestClient,
    nota: dict[str, Any],
    corpo: dict[str, Any] | None = None,
    quem: dict[str, str] = ERIK,
) -> Any:
    return client.post(f"/notas/{nota['id']}/conferencia", json=corpo, headers=quem)


def _item(client: TestClient, item_id: int) -> dict[str, Any]:
    lista = client.get("/lista", params={"comprados_desde": "2000-01-01T00:00:00Z"}).json()
    for i in lista["itens"] + lista["aguardando_nota"]:
        if i["id"] == item_id:
            return dict(i)
    mud = client.get("/mudancas").json()
    raise AssertionError(f"item {item_id} fora da lista ({mud['recarregar']})")


def _linhas_nota(session: Session, nota_id: int) -> dict[int, int | None]:
    session.expire_all()
    linhas = session.execute(
        text(
            "SELECT linha_num, item_lista_id FROM compras.nota_itens "
            "WHERE nota_fiscal_id = :n ORDER BY linha_num"
        ),
        {"n": nota_id},
    )
    return {int(a): (int(b) if b is not None else None) for a, b in linhas}


# --- a compra simulada da D-33 ----------


def test_compra_simulada_da_d33(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite, arroz, detergente, pao, cafe, chocolate = (
        produto(client, n) for n in ("Leite", "Arroz", "Detergente", "Pão", "Café", "Chocolate")
    )
    # Lista com 5 itens; 3 marcados no mercado (leite, arroz, detergente).
    i_leite, i_arroz, i_det, i_pao, i_cafe = (
        na_lista(client, p) for p in (leite, arroz, detergente, pao, cafe)
    )
    for i in (i_leite, i_arroz, i_det):
        comprar(client, i["id"])
    # A despensa acompanha o leite (tem) e o café (acabou, o que o pôs na lista).
    acompanhar(client, session, leite, "tem")
    acompanhar(client, session, cafe, "acabou")
    sobra = [i for i in client.get("/lista").json()["itens"] if i["produto_id"] == cafe]
    assert sobra[0]["situacao"] == "pendente"

    # Nota com 4 itens da lista (o detergente marcado ficou de fora) e 1 extra.
    nota = _nota(
        client,
        consulta,
        [
            (Item("LEITE FICT 1L", "1", "5", codigo="1"), leite),
            (Item("ARROZ FICT 5KG", "1", "25", codigo="2"), arroz),
            (Item("PAO FICT", "1", "8", codigo="3"), pao),
            (Item("CAFE FICT 500G", "1", "20", codigo="4"), cafe),
            (Item("CHOCOLATE FICT 90G", "1", "7", codigo="5"), chocolate),
        ],
    )

    previa = _previa(client, nota)
    assert previa["conferencia"] == "pendente"
    assert {c["produto"] for c in previa["confirmados"]} == {"Leite", "Arroz"}
    assert all(c["estava"] == "aguardando_nota" for c in previa["confirmados"])
    assert {m["produto"] for m in previa["marcados"]} == {"Pão", "Café"}
    assert all("não estava marcado" in m["aviso"] for m in previa["marcados"])
    assert [e["produto"] for e in previa["extras"]] == ["Chocolate"]
    assert previa["extras"][0]["acompanhado"] is False
    assert previa["extras"][0]["acao"] == "acompanhar_na_despensa"
    assert [a["produto"] for a in previa["aguardando_nota"]] == ["Detergente"]
    assert previa["continuam_pendentes"] == []
    assert [d["produto"] for d in previa["despensa"]] == ["Café"]
    # A prévia não gravou nada.
    assert despensa(client, cafe) == "acabou"
    assert _linhas_nota(session, nota["id"]) == {1: None, 2: None, 3: None, 4: None, 5: None}
    assert client.get(f"/notas/{nota['id']}").json()["conferida_em"] is None

    r = _confirmar(client, nota)
    assert r.status_code == 200, r.text
    feita = r.json()
    assert feita["conferencia"] == "feita"
    for chave in ("confirmados", "marcados", "extras", "aguardando_nota", "despensa"):
        assert feita[chave] == previa[chave], chave

    # Linhas, fechamentos, lista e despensa como a D-33 descreve.
    ligadas = _linhas_nota(session, nota["id"])
    assert ligadas[1] == i_leite["id"] and ligadas[2] == i_arroz["id"]
    assert ligadas[3] is not None and ligadas[4] == i_cafe["id"]
    assert ligadas[5] is None
    for i in (i_leite, i_arroz, i_pao, i_cafe):
        item = _item(client, i["id"])
        assert item["situacao"] == "comprado"
        assert item["fechamento"] == "nota"
        assert item["fechado_por"] == "leitura_nfce"
        assert item["fechado_em"] is not None
    marcado = _item(client, i_cafe["id"])
    assert marcado["comprado_por"] == "Erik"
    assert marcado["comprado_em"] is not None
    detergente_item = _item(client, i_det["id"])
    assert detergente_item["situacao"] == "comprado"
    assert detergente_item["fechamento"] is None
    lista = client.get("/lista").json()
    assert [i["id"] for i in lista["aguardando_nota"]] == [i_det["id"]]
    assert lista["perguntas"] == []
    assert despensa(client, cafe) == "tem"
    assert despensa(client, leite) == "tem"
    assert despensa(client, pao) is None  # não acompanhado: não ganha linha
    assert despensa(client, chocolate) is None
    resumo = client.get(f"/notas/{nota['id']}").json()
    assert resumo["conferida_por"] == "Erik" and resumo["conferida_em"] is not None


def test_confirmar_duas_vezes_nao_muda_nada(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite = produto(client, "Leite")
    pao = produto(client, "Pão")
    i_leite = na_lista(client, leite)
    na_lista(client, pao)
    comprar(client, i_leite["id"])
    nota = _nota(
        client,
        consulta,
        [
            (Item("LEITE FICT 1L", "1", "5", codigo="1"), leite),
            (Item("PAO FICT", "1", "8", codigo="2"), pao),
        ],
    )
    primeira = _confirmar(client, nota)
    assert primeira.status_code == 200
    antes = client.get("/mudancas").json()
    ligadas = _linhas_nota(session, nota["id"])
    conferida_em = client.get(f"/notas/{nota['id']}").json()["conferida_em"]

    segunda = _confirmar(client, nota, quem=LAURA)
    assert segunda.status_code == 200, segunda.text
    corpo = segunda.json()
    assert corpo["conferencia"] == "feita"
    assert {c["produto"] for c in corpo["confirmados"]} == {"Leite"}
    assert {m["produto"] for m in corpo["marcados"]} == {"Pão"}
    assert _linhas_nota(session, nota["id"]) == ligadas
    nota_depois = client.get(f"/notas/{nota['id']}").json()
    assert nota_depois["conferida_em"] == conferida_em
    assert nota_depois["conferida_por"] == "Erik"
    assert client.get("/mudancas").json()["itens"] == antes["itens"]
    assert _previa(client, nota)["conferencia"] == "feita"


# --- os seis casos ----------


def test_pendente_fora_da_nota_continua_e_marcado_fora_da_nota_aguarda(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite, cafe, sal, arroz = (produto(client, n) for n in ("Leite", "Café", "Sal", "Arroz"))
    i_leite = na_lista(client, leite)
    i_cafe = na_lista(client, cafe)
    i_sal = na_lista(client, sal)
    comprar(client, i_sal["id"])
    nota = _nota(
        client,
        consulta,
        [
            (Item("LEITE FICT", "1", "5", codigo="1"), leite),
            (Item("ARROZ FICT", "1", "9", codigo="2"), arroz),
        ],
    )
    previa = _previa(client, nota)
    assert [m["item_lista_id"] for m in previa["marcados"]] == [i_leite["id"]]
    assert [p["item_lista_id"] for p in previa["continuam_pendentes"]] == [i_cafe["id"]]
    assert [a["item_lista_id"] for a in previa["aguardando_nota"]] == [i_sal["id"]]
    assert previa["aguardando_nota"][0]["dias"] == 0
    assert [e["produto"] for e in previa["extras"]] == ["Arroz"]

    _confirmar(client, nota)
    assert _item(client, i_cafe["id"])["situacao"] == "pendente"
    assert _item(client, i_sal["id"])["fechamento"] is None


def test_nota_sem_nada_da_lista_e_sem_lista(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    cafe = produto(client, "Café")
    farmacia = produto(client, "Dipirona")
    na_lista(client, cafe)
    nota = _nota(
        client,
        consulta,
        [
            (Item("DIPIRONA FICT", "1", "12", codigo="1"), farmacia),
            (Item("COISA ESQUISITA", "1", "3", codigo="2"), None),
        ],
        cnpj=CNPJ_B,
    )
    previa = _previa(client, nota)
    assert previa["conferencia"] == "sem_lista"
    assert [e["produto"] for e in previa["extras"]] == ["Dipirona"]
    assert [n["linha"] for n in previa["nao_reconhecidos"]] == [2]
    assert previa["confirmados"] == previa["marcados"] == []
    assert previa["continuam_pendentes"] == previa["aguardando_nota"] == []

    # A confirmação existe: marca a nota como conferida, sem tocar na lista.
    r = _confirmar(client, nota)
    assert r.status_code == 200
    assert client.get(f"/notas/{nota['id']}").json()["conferida_em"] is not None
    assert [i["situacao"] for i in client.get("/lista").json()["itens"]] == ["pendente"]


def test_nao_reconhecido_nao_bloqueia_e_a_associacao_aplica_o_efeito(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite = produto(client, "Leite")
    i_leite = na_lista(client, leite)
    comprar(client, i_leite["id"])
    nota = _nota(client, consulta, [(Item("LEITE FICT 1L", "1", "5", codigo="1"), None)])
    assert _previa(client, nota)["nao_reconhecidos"][0]["linha"] == 1
    assert _confirmar(client, nota).status_code == 200
    assert _item(client, i_leite["id"])["fechamento"] is None  # fora da conferência

    r = associar(client, nota, 1, leite)
    assert r.status_code == 200, r.text
    # A nota já conferida casa a linha com o aguardando nota do mesmo produto.
    assert _item(client, i_leite["id"])["fechamento"] == "nota"
    assert _linhas_nota(session, nota["id"])[1] == i_leite["id"]


def test_associar_depois_leva_o_produto_acompanhado_para_tem(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite = produto(client, "Leite")
    acompanhar(client, session, leite, "acabando")
    nota = _nota(client, consulta, [(Item("LEITE FICT 1L", "1", "5", codigo="1"), None)])
    _confirmar(client, nota)
    assert despensa(client, leite) == "acabando"
    associar(client, nota, 1, leite)
    assert despensa(client, leite) == "tem"


# --- nota e marcação ----------


def test_nota_emitida_antes_da_marcacao_nao_confirma(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = produto(client, "Leite")
    i_leite = na_lista(client, leite)
    comprar(client, i_leite["id"])
    velha = _nota(
        client,
        consulta,
        [(Item("LEITE FICT 1L", "1", "5", codigo="1"), leite)],
        emissao=_emissao(timedelta(days=-3)),
    )
    previa = _previa(client, velha)
    assert previa["confirmados"] == [] and previa["marcados"] == []
    assert [e["produto"] for e in previa["extras"]] == ["Leite"]
    assert previa["conferencia"] == "sem_lista"
    _confirmar(client, velha)
    assert _item(client, i_leite["id"])["fechamento"] is None


def test_aguardando_e_confirmado_por_nota_de_outro_estabelecimento_dias_depois(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite, sabao = produto(client, "Leite"), produto(client, "Sabão")
    i_leite = na_lista(client, leite)
    comprar(client, i_leite["id"])
    recuar_compra(session, i_leite["id"], 3)
    mercado = _nota(client, consulta, [(Item("SABAO FICT", "1", "9", codigo="1"), sabao)], numero=1)
    _confirmar(client, mercado)
    assert _item(client, i_leite["id"])["fechamento"] is None

    padaria = _nota(
        client, consulta, [(Item("LEITE PADARIA", "1", "6", codigo="9"), leite)],
        numero=2, cnpj=CNPJ_B,
    )  # fmt: skip
    previa = _previa(client, padaria)
    assert [c["item_lista_id"] for c in previa["confirmados"]] == [i_leite["id"]]
    _confirmar(client, padaria)
    item = _item(client, i_leite["id"])
    assert item["fechamento"] == "nota" and item["fechado_por"] == "leitura_nfce"


def test_duas_notas_do_mesmo_dia_o_que_a_primeira_fechou_nao_entra_na_segunda(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = produto(client, "Leite")
    i_leite = na_lista(client, leite)
    comprar(client, i_leite["id"])
    a = _nota(client, consulta, [(Item("LEITE A", "1", "5", codigo="1"), leite)], numero=1)
    b = _nota(
        client, consulta, [(Item("LEITE B", "1", "5", codigo="2"), leite)], numero=2, cnpj=CNPJ_B
    )
    _confirmar(client, a)
    segunda = _previa(client, b)
    assert segunda["confirmados"] == []
    assert [e["produto"] for e in segunda["extras"]] == ["Leite"]


# --- despensa ----------


def test_extra_acompanhado_vai_para_tem_e_nao_acompanhado_so_oferece_a_acao(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite, chocolate = produto(client, "Leite"), produto(client, "Chocolate")
    acompanhar(client, session, leite, "acabando")
    nota = _nota(
        client,
        consulta,
        [
            (Item("LEITE FICT", "1", "5", codigo="1"), leite),
            (Item("CHOCOLATE FICT", "1", "7", codigo="2"), chocolate),
        ],
    )
    previa = _previa(client, nota)
    extras = {e["produto"]: e for e in previa["extras"]}
    assert extras["Leite"]["acompanhado"] is True and extras["Leite"]["acao"] is None
    assert extras["Chocolate"]["acompanhado"] is False
    assert extras["Chocolate"]["acao"] == "acompanhar_na_despensa"
    assert extras["Chocolate"]["produto_id"] == chocolate
    assert previa["despensa"] == [
        {"produto_id": leite, "produto": "Leite", "antes": "acabando", "depois": "tem"}
    ]
    _confirmar(client, nota)
    assert despensa(client, leite) == "tem"
    assert despensa(client, chocolate) is None
    # A ação é o PUT de sempre.
    r = client.put(f"/despensa/{chocolate}", json={"estado": "tem"}, headers=LAURA)
    assert r.status_code == 200 and despensa(client, chocolate) == "tem"


def test_nota_lida_com_atraso_nao_desfaz_um_acabou_posterior(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = produto(client, "Leite")
    client.put(f"/despensa/{leite}", json={"estado": "acabou"}, headers=LAURA)  # agora
    nota = _nota(
        client, consulta, [(Item("LEITE FICT", "1", "5", codigo="1"), leite)],
        emissao=_emissao(timedelta(hours=-5)),
    )  # fmt: skip
    previa = _previa(client, nota)
    assert previa["despensa"] == []
    _confirmar(client, nota)
    assert despensa(client, leite) == "acabou"


def test_item_aguardando_nao_mexe_na_despensa(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    leite, sal = produto(client, "Leite"), produto(client, "Sal")
    i_sal = na_lista(client, sal)
    comprar(client, i_sal["id"])
    acompanhar(client, session, sal, "acabou")  # alguém mexeu na despensa depois
    nota = _nota(client, consulta, [(Item("LEITE FICT", "1", "5", codigo="1"), leite)])
    previa = _previa(client, nota)
    assert previa["despensa"] == [] and previa["conferencia"] == "sem_lista"
    _confirmar(client, nota)
    assert despensa(client, sal) == "acabou"


# --- quantidade menor ----------


def _com_diferenca(
    client: TestClient, consulta: ConsultaFalsa, quantidade: str = "6"
) -> tuple[dict[str, Any], dict[str, Any], int]:
    banana = produto(client, "Banana")
    pedido = na_lista(client, banana, quantidade=quantidade, unidade="un")
    comprar(client, pedido["id"])
    nota = _nota(client, consulta, [(Item("BANANA FICT", "4", "8", codigo="1"), banana)])
    return nota, pedido, banana


def test_quantidade_menor_pergunta_e_sem_resposta_da_422(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    nota, pedido, _ = _com_diferenca(client, consulta)
    previa = _previa(client, nota)
    (dif,) = previa["diferencas"]
    assert dif["item_lista_id"] == pedido["id"]
    assert (dif["pedido"], dif["veio"], dif["unidade"]) == ("6", "4", "un")
    assert dif["pergunta"] == "Os 2 un que faltaram voltam para a lista?"
    assert dif["volta"] is None

    r = _confirmar(client, nota)
    assert r.status_code == 422
    assert r.json()["faltam"] == [{"item_lista_id": pedido["id"], "produto": "Banana"}]
    r = _confirmar(client, nota, {"diferencas": []})
    assert r.status_code == 422
    # Nada foi gravado.
    assert client.get(f"/notas/{nota['id']}").json()["conferida_em"] is None
    assert _item(client, pedido["id"])["fechamento"] is None
    assert _linhas_nota(session, nota["id"]) == {1: None}


def test_volta_cria_pendente_com_a_diferenca(client: TestClient, consulta: ConsultaFalsa) -> None:
    nota, pedido, banana = _com_diferenca(client, consulta)
    r = _confirmar(client, nota, {"diferencas": [{"item_lista_id": pedido["id"], "volta": True}]})
    assert r.status_code == 200, r.text
    assert r.json()["diferencas"][0]["volta"] is True
    assert _item(client, pedido["id"])["fechamento"] == "nota"
    pendentes = [i for i in client.get("/lista").json()["itens"] if i["situacao"] == "pendente"]
    assert len(pendentes) == 1
    assert pendentes[0]["produto_id"] == banana
    assert pendentes[0]["quantidade"] == "2.000" and pendentes[0]["unidade"] == "un"
    assert pendentes[0]["origem"] == "nota" and pendentes[0]["adicionado_por"] == "Erik"


def test_sem_volta_nao_cria_nada(client: TestClient, consulta: ConsultaFalsa) -> None:
    nota, pedido, _ = _com_diferenca(client, consulta)
    r = _confirmar(client, nota, {"diferencas": [{"item_lista_id": pedido["id"], "volta": False}]})
    assert r.status_code == 200
    assert _item(client, pedido["id"])["fechamento"] == "nota"
    assert [i for i in client.get("/lista").json()["itens"] if i["situacao"] == "pendente"] == []


def test_volta_soma_ao_pendente_que_ja_existe(client: TestClient, consulta: ConsultaFalsa) -> None:
    nota, pedido, banana = _com_diferenca(client, consulta)
    # Outro pendente do mesmo produto já na lista (o comprado aguarda nota).
    existente = na_lista(client, banana, quantidade="1", unidade="un")
    assert existente["id"] != pedido["id"]
    _confirmar(client, nota, {"diferencas": [{"item_lista_id": pedido["id"], "volta": True}]})
    pendentes = [i for i in client.get("/lista").json()["itens"] if i["situacao"] == "pendente"]
    assert [(p["id"], p["quantidade"]) for p in pendentes] == [(existente["id"], "3.000")]


def test_duas_linhas_do_mesmo_produto_somam_antes_de_comparar(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = produto(client, "Banana")
    comprar(client, na_lista(client, banana, quantidade="6", unidade="un")["id"])
    nota = _nota(
        client,
        consulta,
        [
            (Item("BANANA FICT A", "3", "6", codigo="1"), banana),
            (Item("BANANA FICT B", "3", "6", codigo="2"), banana),
        ],
    )
    previa = _previa(client, nota)
    assert previa["diferencas"] == []
    assert previa["confirmados"][0]["linhas"] == [1, 2]


def test_sem_quantidade_na_lista_nunca_e_menor_e_unidades_diferentes_nao_comparam(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    arroz, leite, queijo = (produto(client, n) for n in ("Arroz", "Leite", "Queijo"))
    comprar(client, na_lista(client, arroz)["id"])  # o de sempre
    comprar(client, na_lista(client, leite, quantidade="6", unidade="l")["id"])
    comprar(client, na_lista(client, queijo, quantidade="1", unidade="un")["id"])
    nota = _nota(
        client,
        consulta,
        [
            (Item("ARROZ FICT", "1", "9", codigo="1"), arroz),
            (Item("LEITE FICT", "2", "10", codigo="2"), leite),
            # pesado em KG: lista em "un" não compara com peso
            (Item("QUEIJO FICT KG", "0.3", "9", unidade="KG", codigo="3"), queijo),
        ],
    )
    assert _previa(client, nota)["diferencas"] == []


def test_lista_em_kg_compara_com_variante_pesada(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    tomate = produto(client, "Tomate")
    pedido = na_lista(client, tomate, quantidade="1", unidade="kg")
    comprar(client, pedido["id"])
    nota = _nota(
        client,
        consulta,
        [(Item("TOMATE KG", "0.512", "4", unidade="KG", codigo="1"), tomate)],
    )
    (dif,) = _previa(client, nota)["diferencas"]
    assert (dif["pedido"], dif["veio"], dif["unidade"]) == ("1", "0.512", "kg")
    assert dif["pergunta"] == "Os 0.488 kg que faltaram voltam para a lista?"


# --- aguardando nota: lista, fechar, pergunta ----------


def test_desfazer_de_item_fechado_por_nota_e_409_e_o_aguardando_se_desfaz(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite, sal = produto(client, "Leite"), produto(client, "Sal")
    i_leite, i_sal = na_lista(client, leite), na_lista(client, sal)
    comprar(client, i_leite["id"])
    comprar(client, i_sal["id"])
    nota = _nota(client, consulta, [(Item("LEITE FICT", "1", "5", codigo="1"), leite)])
    _confirmar(client, nota)

    r = client.post(f"/lista/itens/{i_leite['id']}/desfazer", headers=LAURA)
    assert r.status_code == 409, r.text
    assert r.json()["item"]["fechamento"] == "nota"
    assert _item(client, i_leite["id"])["situacao"] == "comprado"

    ok = client.post(f"/lista/itens/{i_sal['id']}/desfazer", headers=LAURA)
    assert ok.status_code == 200 and ok.json()["situacao"] == "pendente"
    assert ok.json()["fechamento"] is None


# --- notas: proximos e filas ----------


def test_proximos_na_leitura_e_filas_de_notas(client: TestClient, consulta: ConsultaFalsa) -> None:
    cafe = produto(client, "Café")
    na_lista(client, cafe)
    lida = nota_lida(
        client,
        consulta,
        [Item("CAFE FICT", "1", "20", codigo="1"), Item("COISA ESQUISITA", "1", "3", codigo="2")],
        numero=1,
        emissao=_emissao(),
    )
    assert client.get(f"/notas/{lida['id']}").json()["proximos"] is None
    assert lida["proximos"] == {
        "ligar_despesa": True,
        "itens_sem_variante": 2,
        "conferencia": "sem_lista",
    }
    outra = nota_lida(
        client,
        consulta,
        [Item("OUTRA COISA", "1", "3", codigo="9")],
        numero=2,
        cnpj=CNPJ_B,
        emissao=_emissao(),
    )
    assert outra["proximos"]["itens_sem_variante"] == 1
    assert associar(client, lida, 1, cafe).status_code == 200
    assert _previa(client, lida)["conferencia"] == "pendente"
    _confirmar(client, lida)

    todas = client.get("/notas").json()
    assert todas["total"] == 2 and len(todas["items"]) == 2
    sem_conferencia = client.get("/notas", params={"conferida": "false"}).json()
    assert [n["id"] for n in sem_conferencia["items"]] == [outra["id"]]
    assert client.get("/notas", params={"conferida": "true"}).json()["total"] == 1
    assert client.get("/notas", params={"com_transacao": "false"}).json()["total"] == 2
    assert client.get("/notas", params={"com_transacao": "true"}).json()["total"] == 0
    pagina = client.get("/notas", params={"limite": 1, "offset": 1}).json()
    assert pagina["total"] == 2 and len(pagina["items"]) == 1 and pagina["offset"] == 1
    assert client.get(f"/notas/{lida['id']}/conferencia").json()["conferencia"] == "feita"


def test_conferencia_de_nota_inexistente_ou_com_erro(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    assert client.get("/notas/9999/conferencia").status_code == 404
    assert client.post("/notas/9999/conferencia", headers=LAURA).status_code == 404
    from tests.nfce_apoio import chave, url_qr

    c = chave(numero=7)
    r = client.post("/notas", json={"entrada": url_qr(c)}, headers=LAURA)  # a SEFAZ responde 404
    assert r.json()["status"] == "erro"
    assert r.json()["proximos"]["conferencia"] == "sem_lista"
    assert client.get(f"/notas/{r.json()['id']}/conferencia").status_code == 409
    assert client.post(f"/notas/{r.json()['id']}/conferencia", headers=LAURA).status_code == 409
    sem_quem = client.post(f"/notas/{r.json()['id']}/conferencia")
    assert sem_quem.status_code == 400
