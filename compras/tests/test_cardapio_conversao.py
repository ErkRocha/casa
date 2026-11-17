"""Conversão de unidades (modelo-cardapio.md, "Unidades") e as receitas."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.enums import MedidaBase, UnidadeMedida
from compras.services.conversao import converte, para_base_produto, para_compra
from tests.apoio import LAURA, ingrediente, produto, receita

D = Decimal
G, ML, UN = MedidaBase.G, MedidaBase.ML, MedidaBase.UN
U = UnidadeMedida


# --- funções puras -------------------------------------------------------------


def test_mesma_dimensao_usa_a_tabela_fixa() -> None:
    assert para_base_produto(D("0.5"), U.KG, G, None) == D(500)
    assert para_base_produto(D(200), U.G, G, None) == D(200)
    assert para_base_produto(D(2), U.L, ML, None) == D(2000)
    assert para_base_produto(D(1), U.COLHER_SOPA, ML, None) == D(15)
    assert para_base_produto(D(2), U.COLHER_CHA, ML, None) == D(10)
    assert para_base_produto(D(1), U.XICARA, ML, None) == D(240)
    assert para_base_produto(D(3), U.UN, UN, None) == D(3)


def test_caso_2_receita_em_unidade_produto_em_peso() -> None:
    # 2 cebolas, a 150 g cada = 300 g
    assert para_base_produto(D(2), U.UN, G, D(150)) == D(300)


def test_caso_3_receita_em_peso_produto_em_unidade() -> None:
    # 100 g de ovo com o ovo a 50 g = 2 ovos
    assert para_base_produto(D(100), U.G, UN, D(50)) == D(2)


def test_caso_4_nao_converte() -> None:
    # colher (volume) num produto em g: sem densidade
    assert para_base_produto(D(2), U.COLHER_SOPA, G, D(1000)) is None
    # massa com volume do outro lado
    assert para_base_produto(D(100), U.G, ML, D(1000)) is None
    # falta o dado
    assert para_base_produto(D(2), U.UN, G, None) is None
    assert para_base_produto(D(2), U.KG, None, None) is None


def test_a_gosto_nao_tem_quantidade() -> None:
    assert para_base_produto(D(1), U.A_GOSTO, G, None) is None
    assert converte(D(1), U.A_GOSTO, None, None, "un") is True


def test_base_para_unidade_de_compra_direta() -> None:
    assert para_compra(D(300), G, D(150), "kg") == (D("0.300"), "kg")
    assert para_compra(D(300), G, None, "g") == (D("300.000"), "g")
    assert para_compra(D(1500), ML, None, "L") == (D("1.500"), "L")  # caixa não importa
    assert para_compra(D(250), ML, None, "ml") == (D("250.000"), "ml")
    # kg exige base em g
    assert para_compra(D(3), UN, None, "kg") is None


def test_base_para_unidade_de_compra_arredonda_para_cima() -> None:
    assert para_compra(D(1500), ML, D(1000), "un") == (D("2.000"), "un")
    assert para_compra(D(1000), ML, D(1000), "un") == (D("1.000"), "un")
    assert para_compra(D(60), G, D(50), "pct") == (D("2.000"), "pct")
    # ovos: base un sem medida_por_unidade conta de um em um
    assert para_compra(D(3), UN, None, "un") == (D("3.000"), "un")
    # sem unidade_padrao vale "un"
    assert para_compra(D(1), ML, D(500), None) == (D("1.000"), "un")


def test_sem_dado_nao_converte_para_compra() -> None:
    assert para_compra(D(10), None, None, "un") is None
    assert para_compra(D(10), G, None, "un") is None


def test_resto_de_divisao_de_fracao_nao_custa_uma_embalagem() -> None:
    um_terco = D(1) / D(3)
    assert para_compra(um_terco * 3 * 500, ML, D(500), "un") == (D("1.000"), "un")


# --- pela API -----------------------------------------------------------------


def test_patch_produto_com_medidas(client: TestClient) -> None:
    id_ = produto(client, "Cebola", "kg")
    r = client.patch(
        f"/produtos/{id_}", json={"medida_base": "g", "medida_por_unidade": "150"}, headers=LAURA
    )
    assert r.status_code == 200, r.text
    assert r.json()["medida_base"] == "g"
    assert r.json()["medida_por_unidade"] == "150.000"

    limpar = client.patch(
        f"/produtos/{id_}", json={"medida_base": None, "medida_por_unidade": None}, headers=LAURA
    )
    assert limpar.json()["medida_base"] is None and limpar.json()["medida_por_unidade"] is None


def test_medida_por_unidade_sem_medida_base_e_422(client: TestClient) -> None:
    id_ = produto(client, "Leite", "un")
    r = client.patch(f"/produtos/{id_}", json={"medida_por_unidade": "1000"}, headers=LAURA)
    assert r.status_code == 422
    negativa = client.patch(
        f"/produtos/{id_}", json={"medida_base": "ml", "medida_por_unidade": "-1"}, headers=LAURA
    )
    assert negativa.status_code == 422


def test_sem_medida_lista_so_o_que_nao_converte(client: TestClient) -> None:
    cebola = produto(client, "Cebola", "kg", "g", "150")  # ok
    farinha = produto(client, "Farinha", "un", "g", "1000")  # colher não converte
    sal = produto(client, "Sal", "un")  # a gosto: não entra
    azeite = produto(client, "Azeite", "un")  # sem medida_base
    produto(client, "Sem uso", "un")
    receita(
        client,
        "Bolo",
        [
            ingrediente(cebola, "2", "un"),
            ingrediente(farinha, "2", "colher_sopa"),
            ingrediente(sal, None, "a_gosto"),
            ingrediente(azeite, "1", "colher_sopa"),
        ],
    )
    fila = client.get("/produtos/sem-medida", params={"usados_em_receita": "true"}).json()
    por_nome = {p["nome"]: p for p in fila}
    assert set(por_nome) == {"Farinha", "Azeite"}
    assert por_nome["Farinha"]["motivos"] == ["colher_sopa não converte para g"]
    assert por_nome["Azeite"]["motivos"] == ["sem medida_base"]
    assert por_nome["Azeite"]["receitas"] == ["Bolo"]

    todos = {p["nome"] for p in client.get("/produtos/sem-medida?usados_em_receita=false").json()}
    assert {"Azeite", "Sal", "Sem uso"} <= todos and "Cebola" not in todos


# --- receitas ------------------------------------------------------------------


def test_criar_receita_com_produto_novo_e_converte(client: TestClient) -> None:
    cebola = produto(client, "Cebola", "kg", "g", "150")
    criada = receita(
        client,
        "Arroz",
        [
            ingrediente(cebola, "1", "un", "picada"),
            {"produto_nome": "Arroz 5kg", "quantidade": "70", "unidade": "g"},
            {"produto_nome": "Sal", "unidade": "a_gosto"},
        ],
    )
    ings = criada["ingredientes"]
    assert [i["ordem"] for i in ings] == [0, 1, 2]
    assert [i["produto_nome"] for i in ings] == ["Cebola", "Arroz 5kg", "Sal"]
    assert ings[0]["quantidade"] == "1.000" and ings[0]["observacao"] == "picada"
    assert [i["converte"] for i in ings] == [True, False, True]  # arroz sem medida_base
    assert ings[2]["quantidade"] is None
    produtos = client.get("/produtos", params={"busca": "Arroz"}).json()
    assert produtos[0]["secao_nome"] == "Sem seção"


def _corpo(**campos: object) -> dict[str, object]:
    return {
        "id_cliente": str(uuid.uuid4()),
        "nome": "X",
        "tipo": "almoco",
        "rendimento_porcoes": "1",
        "ingredientes": [],
        **campos,
    }


def test_receita_validacoes(client: TestClient) -> None:
    def post(**campos: object) -> int:
        return int(client.post("/receitas", json=_corpo(**campos), headers=LAURA).status_code)

    assert post(pode_antecipar=True) == 422  # sem dura_dias
    assert post(rendimento_porcoes="0") == 422
    assert post(ingredientes=[{"produto_nome": "Sal", "unidade": "g"}]) == 422
    a_gosto_com_quantidade = {"produto_nome": "Sal", "unidade": "a_gosto", "quantidade": "1"}
    assert post(ingredientes=[a_gosto_com_quantidade]) == 422
    assert post(tipo="ceia") == 422
    assert client.post("/receitas", json=_corpo()).status_code == 400  # sem X-Quem


def test_id_cliente_repetido_devolve_a_que_existe(client: TestClient) -> None:
    corpo = _corpo(nome="Ovos mexidos", tipo="cafe_da_manha")
    primeira = client.post("/receitas", json=corpo, headers=LAURA)
    segunda = client.post("/receitas", json=corpo, headers=LAURA)
    assert (primeira.status_code, segunda.status_code) == (201, 200)
    assert primeira.json()["id"] == segunda.json()["id"]


def test_nome_repetido_e_409(client: TestClient) -> None:
    receita(client, "Pão com ovo", [])
    r = client.post("/receitas", json=_corpo(nome="  pao  COM ovo "), headers=LAURA)
    assert r.status_code == 409


def test_listar_receitas_busca_filtros_e_pagina(client: TestClient) -> None:
    receita(client, "Frango grelhado", [], tipo="almoco")
    receita(client, "Sanduíche de frango", [], tipo="lanche")
    receita(client, "Arroz", [], tipo="almoco", pode_antecipar=True, dura_dias=3)
    corpo = client.get("/receitas", params={"busca": "FRANGO"}).json()
    assert corpo["total"] == 2
    # quem começa com o texto vem antes
    assert [r["nome"] for r in corpo["items"]] == ["Frango grelhado", "Sanduíche de frango"]
    assert client.get("/receitas", params={"tipo": "almoco"}).json()["total"] == 2
    antecipaveis = client.get("/receitas", params={"pode_antecipar": "true"}).json()
    assert [r["nome"] for r in antecipaveis["items"]] == ["Arroz"]
    pagina = client.get("/receitas", params={"limite": 1, "offset": 1}).json()
    assert pagina["total"] == 3 and len(pagina["items"]) == 1
    assert pagina["limite"] == 1 and pagina["offset"] == 1


def test_put_apaga_ingredientes_antigos_e_cria_novos(client: TestClient, session: Session) -> None:
    cebola = produto(client, "Cebola", "kg", "g", "150")
    alho = produto(client, "Alho", "un")
    criada = receita(client, "Refogado", [ingrediente(cebola, "1", "un")])
    antigos = [i["id"] for i in criada["ingredientes"]]

    corpo = {
        "nome": "Refogado de alho",
        "tipo": "janta",
        "rendimento_porcoes": "2",
        "ingredientes": [ingrediente(cebola, "2", "un"), ingrediente(alho, "1", "un")],
    }
    r = client.put(f"/receitas/{criada['id']}", json=corpo, headers=LAURA)
    assert r.status_code == 200, r.text
    novo = r.json()
    assert novo["nome"] == "Refogado de alho" and novo["tipo"] == "janta"
    assert len(novo["ingredientes"]) == 2
    assert set(antigos).isdisjoint(i["id"] for i in novo["ingredientes"])

    session.expire_all()
    linha = session.execute(
        text(
            "SELECT deleted_em IS NOT NULL, quantidade "
            "FROM compras.receita_ingredientes WHERE id = :i"
        ),
        {"i": antigos[0]},
    ).one()
    assert linha[0] is True and linha[1] == D("1.000")  # apagado, nunca alterado


def test_duplicar_receita(client: TestClient) -> None:
    cebola = produto(client, "Cebola", "kg", "g", "150")
    original = receita(client, "Sopa", [ingrediente(cebola, "1", "un")], tempo_preparo_min=40)
    copia = client.post(f"/receitas/{original['id']}/duplicar", headers=LAURA)
    assert copia.status_code == 201
    assert copia.json()["nome"] == "Sopa (cópia)"
    assert copia.json()["tempo_preparo_min"] == 40
    assert len(copia.json()["ingredientes"]) == 1
    segunda = client.post(f"/receitas/{original['id']}/duplicar", headers=LAURA)
    assert segunda.json()["nome"] == "Sopa (cópia 2)"


def test_apagar_receita_sem_uso_e_get_404(client: TestClient) -> None:
    criada = receita(client, "Pudim", [])
    r = client.delete(f"/receitas/{criada['id']}", headers=LAURA)
    assert r.status_code == 200 and r.json()["deleted_em"] is not None
    assert client.get(f"/receitas/{criada['id']}").status_code == 404
    assert client.get("/receitas").json()["total"] == 0


@pytest.mark.parametrize("campo", ["nome", "tipo"])
def test_put_exige_corpo_completo(client: TestClient, campo: str) -> None:
    criada = receita(client, "Pudim", [])
    corpo = {"nome": "Pudim", "tipo": "janta", "rendimento_porcoes": "1"}
    del corpo[campo]
    assert client.put(f"/receitas/{criada['id']}", json=corpo, headers=LAURA).status_code == 422
