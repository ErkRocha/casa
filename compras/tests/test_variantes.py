"""Variantes (D-33): identidade por mercado e código, GTIN, juntar, sugestão de medida.

Páginas inventadas (`nfce_apoio`); nenhum teste sai da máquina.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.enums import MedidaBase
from compras.nfce.medida import sugerir_medida
from tests.apoio import ERIK, LAURA
from tests.nfce_apoio import CNPJ_A, CNPJ_B, ConsultaFalsa, Item
from tests.test_notas import nota_lida, novo_produto

LEITE = Item("LEITE INTEG FICTICIO 1L", "2", "9.98", codigo="7891234567895")
SUCO = Item("SUCO UVA INTEGRAL 1L", "1", "8.00", codigo="0000555")
BANANA = Item("BANANA PRATA KG", "1.5", "10.50", unidade="KG", valor_unitario="7.00", codigo="900")


def associar(client: TestClient, nota: dict[str, Any], linha: int, **corpo: Any) -> dict[str, Any]:
    item = next(i for i in nota["itens"] if i["linha_num"] == linha)
    r = client.put(f"/notas/{nota['id']}/itens/{item['id']}/variante", json=corpo, headers=LAURA)
    assert r.status_code == 200, r.text
    return dict(r.json())


def item_da_nota(client: TestClient, nota: dict[str, Any], linha: int = 1) -> dict[str, Any]:
    corpo = client.get(f"/notas/{nota['id']}").json()
    return dict(next(i for i in corpo["itens"] if i["linha_num"] == linha))


# --- identidade da variante --------------------------------------------------------


def test_mesmo_gtin_em_mercados_diferentes_cai_na_mesma_variante(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    a = nota_lida(client, consulta, [LEITE], numero=1, cnpj=CNPJ_A)
    item = associar(client, a, 1, produto_id=leite, nova={})
    # O GTIN do item vai para a variante nova.
    variante = client.get(f"/variantes/{item['variante_id']}").json()
    assert variante["gtin"] == "7891234567895"
    assert variante["produto_id"] == leite

    b = nota_lida(client, consulta, [LEITE], numero=2, cnpj=CNPJ_B)
    achado = b["itens"][0]
    assert (achado["variante_id"], achado["origem_associacao"]) == (item["variante_id"], "gtin")
    assert achado["produto_id"] == leite


def test_mesmo_codigo_no_mesmo_mercado_cai_na_mesma_variante_e_em_outro_mercado_nao(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    suco = novo_produto(client, "suco de uva")
    a1 = nota_lida(client, consulta, [SUCO], numero=1, cnpj=CNPJ_A)
    item = associar(client, a1, 1, produto_id=suco, nova={})
    variante = client.get(f"/variantes/{item['variante_id']}").json()
    # O código fica sem os zeros à esquerda, preso ao mercado da nota.
    assert [(c["mercado_nome"], c["codigo"]) for c in variante["codigos"]] == [
        ("MERCADO FICTICIO DO BAIRRO LTDA", "555")
    ]

    # Mesmo mercado e mesmo código, mas o mercado abreviou o texto de outro jeito.
    abreviado = Item("SUCO UVA INT 1 L", "1", "8.50", codigo="555")
    a2 = nota_lida(client, consulta, [abreviado], numero=2, cnpj=CNPJ_A)
    assert a2["itens"][0]["variante_id"] == item["variante_id"]
    assert a2["itens"][0]["origem_associacao"] == "apelido"

    # O mesmo código em outro mercado não é a mesma coisa: cada mercado numera do seu jeito.
    b = nota_lida(client, consulta, [abreviado], numero=3, cnpj=CNPJ_B)
    assert b["itens"][0]["variante_id"] is None
    assert b["sem_produto"] == 1


def test_o_codigo_ganha_do_texto(client: TestClient, consulta: ConsultaFalsa) -> None:
    uva = novo_produto(client, "suco de uva")
    laranja = novo_produto(client, "suco de laranja")
    n1 = nota_lida(client, consulta, [SUCO], numero=1)
    v_uva = associar(client, n1, 1, produto_id=uva, nova={})["variante_id"]
    outro = Item("SUCO LARANJA 1L", "1", "7.00", codigo="777")
    n2 = nota_lida(client, consulta, [outro], numero=2)
    v_laranja = associar(client, n2, 1, produto_id=laranja, nova={})["variante_id"]
    assert v_uva != v_laranja

    # O texto é o da uva, mas o código é o da laranja: vale o código.
    confuso = Item("SUCO UVA INTEGRAL 1L", "1", "7.00", codigo="777")
    n3 = nota_lida(client, consulta, [confuso], numero=3)
    assert n3["itens"][0]["variante_id"] == v_laranja


def test_associar_a_variante_que_ja_existe_e_corrigir(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    uva = novo_produto(client, "suco de uva")
    n1 = nota_lida(client, consulta, [SUCO], numero=1)
    v1 = associar(client, n1, 1, produto_id=uva, nova={})["variante_id"]
    criada = client.post(
        "/variantes", json={"produto_id": uva, "nome": "Suco Del Valle Uva 1L"}, headers=LAURA
    )
    assert criada.status_code == 201, criada.text
    v2 = criada.json()["id"]

    # Corrige: o código e o apelido passam para a outra variante.
    item = associar(client, n1, 1, variante_id=v2)
    assert item["variante_id"] == v2
    assert item["origem_associacao"] == "usuario"
    codigo = session.execute(text("SELECT variante_id FROM compras.variante_codigos")).scalar_one()
    apelido = session.execute(
        text("SELECT variante_id, criado_por, acertos FROM compras.apelidos")
    ).one()
    assert codigo == v2
    assert tuple(apelido) == (v2, "correcao", 1)
    assert v1 != v2


def test_associar_pede_variante_ou_produto(client: TestClient, consulta: ConsultaFalsa) -> None:
    nota = nota_lida(client, consulta, [LEITE])
    url = f"/notas/{nota['id']}/itens/{nota['itens'][0]['id']}/variante"
    assert client.put(url, json={}, headers=LAURA).status_code == 422
    assert (
        client.put(url, json={"variante_id": 1, "produto_id": 1}, headers=LAURA).status_code == 422
    )
    assert client.put(url, json={"variante_id": 999_999}, headers=LAURA).status_code == 404
    assert client.put(url, json={"produto_id": 999_999}, headers=LAURA).status_code == 404
    assert client.put(url, json={"variante_id": 1}).status_code == 400  # sem X-Quem


def test_variante_de_produto_apagado_nao_associa(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    uva = novo_produto(client, "suco de uva")
    associar(client, nota_lida(client, consulta, [SUCO], numero=1), 1, produto_id=uva, nova={})
    assert client.delete(f"/produtos/{uva}", headers=LAURA).status_code == 200
    n2 = nota_lida(client, consulta, [SUCO], numero=2)
    assert n2["itens"][0]["variante_id"] is None


# --- pesada e sugestão de medida ------------------------------------------------------


def test_unidade_kg_marca_a_variante_como_pesada_sem_perguntar(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = novo_produto(client, "banana prata")
    nota = nota_lida(client, consulta, [BANANA])
    item = associar(client, nota, 1, produto_id=banana, nova={})
    variante = client.get(f"/variantes/{item['variante_id']}").json()
    assert (variante["pesada"], variante["medida_base"], variante["conteudo"]) == (True, "g", None)


def test_sugestao_de_medida_vem_na_resposta_e_so_grava_confirmada(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    iogurte = novo_produto(client, "iogurte grego")
    grego = Item("IOG GREGO BATAVO TRAD 450G", "2", "23.96", codigo="1234")
    nota = nota_lida(client, consulta, [grego])
    # Antes de associar, a leitura da nota já mostra a sugestão.
    assert nota["itens"][0]["sugestao_medida"] == {"medida_base": "g", "conteudo": "450.000"}

    item = associar(client, nota, 1, produto_id=iogurte, nova={})
    assert item["sugestao_medida"] == {"medida_base": "g", "conteudo": "450.000"}
    variante = client.get(f"/variantes/{item['variante_id']}").json()
    # Só sugestão: a variante nasce sem medida e entra na fila.
    assert (variante["medida_base"], variante["conteudo"], variante["pesada"]) == (
        None,
        None,
        False,
    )
    fila = client.get("/variantes", params={"sem_medida": True}).json()
    assert [v["id"] for v in fila] == [variante["id"]]

    # Confirmar é o PATCH; depois dele a sugestão some e a fila esvazia.
    r = client.patch(
        f"/variantes/{variante['id']}",
        json={"medida_base": "g", "conteudo": "450"},
        headers=LAURA,
    )
    assert r.status_code == 200, r.text
    assert (r.json()["medida_base"], r.json()["conteudo"]) == ("g", "450.000")
    assert item_da_nota(client, nota)["sugestao_medida"] is None
    assert client.get("/variantes", params={"sem_medida": True}).json() == []


def test_confirmar_a_medida_ao_criar_a_variante_pela_nota(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    suco = novo_produto(client, "suco de uva")
    nota = nota_lida(client, consulta, [SUCO])
    item = associar(
        client, nota, 1, produto_id=suco, nova={"medida_base": "ml", "conteudo": "1000"}
    )
    variante = client.get(f"/variantes/{item['variante_id']}").json()
    assert (variante["medida_base"], variante["conteudo"]) == ("ml", "1000.000")
    assert item["sugestao_medida"] is None


@pytest.mark.parametrize(
    ("descricao", "esperado"),
    [
        ("IOG GREGO BATAVO TRAD 450G", (MedidaBase.G, "450")),
        ("SUCO NATURALE LARANJA INT 3L", (MedidaBase.ML, "3000")),
        ("SUCO LARANJA 1,5L", (MedidaBase.ML, "1500")),
        ("REFRIG COLA 250ML", (MedidaBase.ML, "250")),
        ("ARROZ TIPO 1 1KG", (MedidaBase.G, "1000")),
        ("FARINHA TRIGO GF1KG", (MedidaBase.G, "1000")),
        ("OVOS BRANCOS C/12", (MedidaBase.UN, "12")),
        ("CAFE 0,5KG", (MedidaBase.G, "500")),
        ("LEITE 1L C/12", None),  # dois tamanhos: nenhuma sugestão
        ("BISC 120G 3UN 100G", None),
        ("PAO CACETINHO", None),
        ("QUEIJO MUSSARELA", None),
    ],
)
def test_sugestao_de_medida_pela_descricao(
    descricao: str, esperado: tuple[MedidaBase, str] | None
) -> None:
    achada = sugerir_medida(descricao)
    if esperado is None:
        assert achada is None
    else:
        assert achada is not None
        assert (achada.medida_base, achada.conteudo) == (esperado[0], Decimal(esperado[1]))


# --- cadastro ----------------------------------------------------------------------------


def test_criar_buscar_e_gtin_repetido(client: TestClient, consulta: ConsultaFalsa) -> None:
    leite = novo_produto(client, "leite")
    r = client.post(
        "/variantes",
        json={
            "produto_id": leite,
            "nome": "Leite Italac Integral 1L",
            "marca": "Italac",
            "gtin": "7891234567895",
            "medida_base": "ml",
            "conteudo": "1000",
        },
        headers=LAURA,
    )
    assert r.status_code == 201, r.text
    criada = r.json()
    assert (criada["produto_nome"], criada["criado_por"], criada["pesada"]) == (
        "leite",
        "Laura",
        False,
    )

    repetido = client.post(
        "/variantes",
        json={"produto_id": leite, "nome": "Outro", "gtin": "7891234567895"},
        headers=ERIK,
    )
    assert repetido.status_code == 409
    assert repetido.json()["variante"]["id"] == criada["id"]

    # Busca pelo nome da variante, do produto e do GTIN.
    for params in ({"busca": "italac"}, {"busca": "LEITE"}, {"gtin": "7891234567895"}):
        assert [v["id"] for v in client.get("/variantes", params=params).json()] == [criada["id"]]
    assert client.get("/variantes", params={"busca": "queijo"}).json() == []


def test_busca_pelo_mercado_onde_a_variante_tem_codigo(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    uva = novo_produto(client, "suco de uva")
    n1 = nota_lida(client, consulta, [SUCO], numero=1, cnpj=CNPJ_A, razao="ZAFFARI ESTRELA")
    v = associar(client, n1, 1, produto_id=uva, nova={})["variante_id"]
    achadas = client.get("/variantes", params={"busca": "zaffari"}).json()
    assert [x["id"] for x in achadas] == [v]
    assert client.get("/variantes", params={"busca": "outro mercado"}).json() == []


@pytest.mark.parametrize(
    "corpo",
    [
        {"pesada": True, "medida_base": "ml"},
        {"pesada": True, "conteudo": "1"},
        {"medida_base": "ml"},
        {"conteudo": "500"},
    ],
)
def test_medida_incoerente_e_recusada(client: TestClient, corpo: dict[str, Any]) -> None:
    leite = novo_produto(client, "leite")
    r = client.post("/variantes", json={"produto_id": leite, "nome": "X", **corpo}, headers=LAURA)
    assert r.status_code == 422, r.text


def test_gtin_invalido_e_produto_inexistente(client: TestClient) -> None:
    leite = novo_produto(client, "leite")
    assert (
        client.post(
            "/variantes", json={"produto_id": leite, "nome": "X", "gtin": "123"}, headers=LAURA
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/variantes", json={"produto_id": 999_999, "nome": "X"}, headers=LAURA
        ).status_code
        == 404
    )


def test_pesada_e_deixar_de_ser_pesada(client: TestClient) -> None:
    banana = novo_produto(client, "banana")
    v = client.post(
        "/variantes", json={"produto_id": banana, "nome": "Banana", "pesada": True}, headers=LAURA
    ).json()
    assert (v["pesada"], v["medida_base"], v["conteudo"]) == (True, "g", None)
    r = client.patch(f"/variantes/{v['id']}", json={"pesada": False}, headers=LAURA).json()
    assert (r["pesada"], r["medida_base"], r["conteudo"]) == (False, None, None)
    r = client.patch(f"/variantes/{v['id']}", json={"pesada": True}, headers=LAURA).json()
    assert (r["pesada"], r["medida_base"]) == (True, "g")


def test_trocar_o_produto_leva_itens_e_apelidos(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    errado = novo_produto(client, "banana nanica")
    certo = novo_produto(client, "banana prata")
    nota = nota_lida(client, consulta, [BANANA])
    v = associar(client, nota, 1, produto_id=errado, nova={})["variante_id"]

    r = client.patch(f"/variantes/{v}", json={"produto_id": certo}, headers=LAURA)
    assert r.status_code == 200, r.text
    assert r.json()["produto_nome"] == "banana prata"
    assert item_da_nota(client, nota)["produto_id"] == certo
    assert session.execute(text("SELECT produto_id FROM compras.apelidos")).scalar_one() == certo
    # A próxima nota já vem com o produto novo.
    assert nota_lida(client, consulta, [BANANA], numero=2)["itens"][0]["produto_id"] == certo


def test_apagar_variante_com_item_de_nota_e_recusado(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    uva = novo_produto(client, "suco de uva")
    nota = nota_lida(client, consulta, [SUCO])
    v = associar(client, nota, 1, produto_id=uva, nova={})["variante_id"]
    r = client.delete(f"/variantes/{v}", headers=LAURA)
    assert r.status_code == 409
    assert "item" in r.json()["detail"]

    livre = client.post(
        "/variantes", json={"produto_id": uva, "nome": "Sem uso"}, headers=LAURA
    ).json()["id"]
    r = client.delete(f"/variantes/{livre}", headers=LAURA)
    assert r.status_code == 200
    assert r.json()["deleted_em"] is not None
    assert client.get(f"/variantes/{livre}").status_code == 404
    assert [x["id"] for x in client.get("/variantes").json()] == [v]


# --- juntar -----------------------------------------------------------------------------------


def test_juntar_leva_codigos_apelidos_e_itens_e_apaga_a_outra(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    uva = novo_produto(client, "suco de uva")
    a = nota_lida(client, consulta, [SUCO], numero=1, cnpj=CNPJ_A)
    v_a = associar(client, a, 1, produto_id=uva, nova={})["variante_id"]
    # Sem GTIN, o mesmo suco no outro mercado nasce como outra variante.
    suco_b = Item("SUCO UVA INTEGRAL 1L", "1", "8.90", codigo="42")
    b = nota_lida(client, consulta, [suco_b], numero=2, cnpj=CNPJ_B)
    assert b["itens"][0]["variante_id"] == v_a  # o texto igual já casa em outro mercado
    # Para o teste: o usuário diz que, no B, é outra variante (descrição diferente).
    suco_b2 = Item("SUCO UVA DELVALLE 1L", "1", "8.90", codigo="42")
    b2 = nota_lida(client, consulta, [suco_b2], numero=3, cnpj=CNPJ_B)
    v_b = associar(client, b2, 1, produto_id=uva, nova={})["variante_id"]
    assert v_b != v_a

    r = client.post(f"/variantes/{v_a}/juntar", json={"outra_id": v_b}, headers=ERIK)
    assert r.status_code == 200, r.text
    juntada = r.json()
    assert juntada["id"] == v_a
    assert sorted(c["codigo"] for c in juntada["codigos"]) == ["42", "555"]
    assert {c["mercado_nome"] for c in juntada["codigos"]} == {"MERCADO FICTICIO DO BAIRRO LTDA"}

    assert client.get(f"/variantes/{v_b}").status_code == 404
    assert item_da_nota(client, b2)["variante_id"] == v_a
    assert (
        session.execute(
            text("SELECT count(*) FROM compras.apelidos WHERE variante_id = :v"), {"v": v_b}
        ).scalar_one()
        == 0
    )
    assert session.execute(
        text("SELECT deleted_em IS NOT NULL FROM compras.variantes WHERE id = :v"), {"v": v_b}
    ).scalar_one()

    # A nota seguinte, com o código do B, cai na variante que ficou.
    c = nota_lida(
        client, consulta, [Item("QUALQUER COISA", "1", "9.00", codigo="42")], numero=4, cnpj=CNPJ_B
    )
    assert c["itens"][0]["variante_id"] == v_a


def test_juntar_leva_o_gtin_e_a_medida_de_quem_tem(client: TestClient) -> None:
    leite = novo_produto(client, "leite")
    sem = client.post(
        "/variantes", json={"produto_id": leite, "nome": "Leite A"}, headers=LAURA
    ).json()["id"]
    com = client.post(
        "/variantes",
        json={
            "produto_id": leite,
            "nome": "Leite B",
            "gtin": "7891234567895",
            "medida_base": "ml",
            "conteudo": "1000",
        },
        headers=LAURA,
    ).json()["id"]
    r = client.post(f"/variantes/{sem}/juntar", json={"outra_id": com}, headers=LAURA)
    assert r.status_code == 200, r.text
    assert (r.json()["gtin"], r.json()["medida_base"], r.json()["conteudo"]) == (
        "7891234567895",
        "ml",
        "1000.000",
    )


def test_juntar_recusa_a_mesma_produtos_diferentes_e_gtins_diferentes(client: TestClient) -> None:
    leite = novo_produto(client, "leite")
    suco = novo_produto(client, "suco")

    def variante(produto: int, nome: str, **extra: Any) -> int:
        r = client.post(
            "/variantes", json={"produto_id": produto, "nome": nome, **extra}, headers=LAURA
        )
        assert r.status_code == 201, r.text
        return int(r.json()["id"])

    v1 = variante(leite, "Leite 1")
    v2 = variante(suco, "Suco 1")
    v3 = variante(leite, "Leite 3", gtin="7891234567895")
    v4 = variante(leite, "Leite 4", gtin="78912345")

    assert (
        client.post(f"/variantes/{v1}/juntar", json={"outra_id": v1}, headers=LAURA).status_code
        == 422
    )
    r = client.post(f"/variantes/{v1}/juntar", json={"outra_id": v2}, headers=LAURA)
    assert r.status_code == 422
    assert "produtos diferentes" in r.json()["detail"]
    assert (
        client.post(f"/variantes/{v3}/juntar", json={"outra_id": v4}, headers=LAURA).status_code
        == 422
    )
    assert (
        client.post(
            f"/variantes/{v1}/juntar", json={"outra_id": 999_999}, headers=LAURA
        ).status_code
        == 404
    )
    # Nada mudou.
    assert len(client.get("/variantes").json()) == 4


# --- banco -----------------------------------------------------------------------------------


def test_forma_de_pagamento_da_nota_fica_guardada(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    from pathlib import Path

    from tests.nfce_apoio import chave, url_qr

    amostra = Path(__file__).parent / "amostras" / "nfce_rs_anonimizada.html"
    c = chave(cnpj="93015006002914", numero=7)
    consulta.paginas[c] = amostra.read_bytes()
    r = client.post("/notas", json={"entrada": url_qr(c)}, headers=LAURA)
    assert r.status_code == 201, r.text
    assert r.json()["forma_pagamento_nota"] == "Cartão de Crédito"


def test_produto_do_item_e_copia_da_variante_por_trigger(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    uva = novo_produto(client, "suco de uva")
    outro = novo_produto(client, "suco")
    nota = nota_lida(client, consulta, [SUCO])
    associar(client, nota, 1, produto_id=uva, nova={})
    # Mesmo que alguém grave outro produto direto, o trigger refaz a cópia.
    session.execute(text("UPDATE compras.nota_itens SET produto_id = :p"), {"p": outro})
    assert session.execute(text("SELECT produto_id FROM compras.nota_itens")).scalar_one() == uva
    session.rollback()
