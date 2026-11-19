"""Preços (D-33): preço cheio, desconto rateado, preço pago e comparável (R$/kg, R$/L, R$/un).

O "hoje" dos testes é 17/11/2026 (`conftest`). Páginas inventadas; nenhum teste
sai da máquina.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.apoio import LAURA
from tests.nfce_apoio import CNPJ_A, CNPJ_B, ConsultaFalsa, Item
from tests.test_notas import nota_lida, novo_produto

CNPJ_C = "77888999000155"

_numero = iter(range(1, 10_000))
MEDIDA_1L = {"medida_base": "ml", "conteudo": "1000"}


def comprar(
    client: TestClient,
    consulta: ConsultaFalsa,
    produto: int,
    descricao: str,
    *,
    quantidade: str,
    total: str,
    emissao: str,
    cnpj: str = CNPJ_A,
    unidade: str = "UN",
    codigo: str = "1",
    nova: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lê uma nota de um item e o associa ao produto (se ainda não vier associado)."""
    item = Item(descricao, quantidade, total, unidade=unidade, codigo=codigo)
    nota = nota_lida(
        client, consulta, [item], numero=next(_numero), cnpj=cnpj, emissao=emissao,
        razao=f"MERCADO {cnpj[:2]}",
    )  # fmt: skip
    if nota["itens"][0]["variante_id"] is None:
        r = client.put(
            f"/notas/{nota['id']}/itens/{nota['itens'][0]['id']}/variante",
            json={"produto_id": produto, "nova": nova or {}},
            headers=LAURA,
        )
        assert r.status_code == 200, r.text
    return dict(client.get(f"/notas/{nota['id']}").json())


def historico(client: TestClient, variante_id: int, **params: Any) -> dict[str, Any]:
    r = client.get(f"/precos/variantes/{variante_id}", params=params)
    assert r.status_code == 200, r.text
    return dict(r.json())


# --- comparável -------------------------------------------------------------------------


def test_item_pesado_em_kg_da_preco_por_quilo(client: TestClient, consulta: ConsultaFalsa) -> None:
    banana = novo_produto(client, "banana prata")
    nota = comprar(
        client, consulta, banana, "BANANA PRATA KG", quantidade="1.5", total="10.50",
        unidade="KG", emissao="10/11/2026 09:00:00",
    )  # fmt: skip
    item = nota["itens"][0]
    # Quantidade 1,5 kg a R$ 10,50: R$ 7,00 o quilo, em numeric.
    assert item["comparavel"] == {"valor": "7.0000", "por": "kg"}
    assert (item["preco_cheio"], item["preco_pago"], item["preco_pago_estimado"]) == (
        "10.50", "10.50", False,
    )  # fmt: skip
    h = historico(client, item["variante_id"])
    assert h["total"] == 1
    assert h["itens"][0]["comparavel"] == {"valor": "7.0000", "por": "kg"}
    assert h["itens"][0]["quantidade"] == "1.500"


def test_um_litro_e_duzentos_ml_se_comparam_por_litro(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    # 1 L por R$ 6,00 e 3 caixinhas de 200 ml por R$ 6,00 (600 ml): R$ 6,00/L e R$ 10,00/L.
    grande = comprar(
        client, consulta, leite, "LEITE GRANDE", quantidade="1", total="6.00",
        emissao="10/11/2026 09:00:00", codigo="10",
        nova={"medida_base": "ml", "conteudo": "1000"},
    )  # fmt: skip
    pequeno = comprar(
        client, consulta, leite, "LEITE CAIXINHA", quantidade="3", total="6.00",
        emissao="11/11/2026 09:00:00", codigo="20",
        nova={"medida_base": "ml", "conteudo": "200"},
    )  # fmt: skip
    assert grande["itens"][0]["comparavel"] == {"valor": "6.0000", "por": "l"}
    assert pequeno["itens"][0]["comparavel"] == {"valor": "10.0000", "por": "l"}

    agregado = client.get(f"/precos/produtos/{leite}").json()
    assert [
        (v["variante_nome"], v["por"], v["ultimo_comparavel"]) for v in agregado["por_variante"]
    ] == [
        ("LEITE GRANDE", "l", "6.0000"),
        ("LEITE CAIXINHA", "l", "10.0000"),
    ]
    # A mais barata pelo comparável, uma por unidade.
    assert [
        (m["variante_nome"], m["por"], m["ultimo_comparavel"]) for m in agregado["mais_barata"]
    ] == [("LEITE GRANDE", "l", "6.0000")]
    assert agregado["sem_comparavel"] == 0


def test_conteudo_vezes_quantidade_em_unidades(client: TestClient, consulta: ConsultaFalsa) -> None:
    ovos = novo_produto(client, "ovos")
    # Duas cartelas de 12 por R$ 24,00: R$ 1,00 o ovo.
    nota = comprar(
        client, consulta, ovos, "OVOS BRANCOS C/12", quantidade="2", total="24.00",
        emissao="10/11/2026 09:00:00",
        nova={"medida_base": "un", "conteudo": "12"},
    )  # fmt: skip
    assert nota["itens"][0]["comparavel"] == {"valor": "1.0000", "por": "un"}


def test_variante_sem_medida_fica_fora_do_comparavel_e_entra_na_contagem(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    suco = novo_produto(client, "suco")
    com = comprar(
        client, consulta, suco, "SUCO COM MEDIDA", quantidade="1", total="8.00", codigo="1",
        emissao="10/11/2026 09:00:00", nova={"medida_base": "ml", "conteudo": "1000"},
    )  # fmt: skip
    sem = comprar(
        client, consulta, suco, "SUCO SEM MEDIDA", quantidade="1", total="5.00", codigo="2",
        emissao="11/11/2026 09:00:00",
    )  # fmt: skip
    assert sem["itens"][0]["comparavel"] is None
    assert sem["itens"][0]["preco_pago"] == "5.00"

    h = historico(client, sem["itens"][0]["variante_id"])
    assert (h["total"], h["sem_comparavel"]) == (1, 1)
    assert h["itens"][0]["comparavel"] is None

    agregado = client.get(f"/precos/produtos/{suco}").json()
    por_variante = {v["variante_nome"]: v for v in agregado["por_variante"]}
    assert por_variante["SUCO SEM MEDIDA"]["por"] is None
    assert (
        por_variante["SUCO SEM MEDIDA"]["compras"],
        por_variante["SUCO SEM MEDIDA"]["sem_comparavel"],
    ) == (0, 1)
    assert por_variante["SUCO COM MEDIDA"]["ultimo_comparavel"] == "8.0000"
    assert agregado["sem_comparavel"] == 1
    # Fora da média e do mínimo; nunca misturada.
    assert [m["variante_nome"] for m in agregado["mais_barata"]] == ["SUCO COM MEDIDA"]

    # `/precos` mostra a mesma contagem, em linha à parte (sem medida).
    linhas = client.get("/precos", params={"produto_id": suco}).json()
    assert sorted((r["por"], r["compras"], r["sem_comparavel"]) for r in linhas if r["por"]) == [
        ("l", 1, 0)
    ]
    sem_medida = [r for r in linhas if r["por"] is None]
    assert [(r["compras"], r["sem_comparavel"], r["ultimo_comparavel"]) for r in sem_medida] == [
        (0, 1, None)
    ]
    assert com["itens"][0]["comparavel"]["por"] == "l"


# --- desconto -------------------------------------------------------------------------------


def _soma_pago(nota: dict[str, Any]) -> Decimal:
    return sum((Decimal(i["preco_pago"]) for i in nota["itens"]), Decimal(0))


def _tres_itens_de_dez(codigo_base: int = 1) -> list[Item]:
    return [Item(f"PRODUTO {n}", "1", "10.00", codigo=str(codigo_base + n)) for n in (1, 2, 3)]


def _associar_todos(client: TestClient, nota: dict[str, Any], produto: int) -> dict[str, Any]:
    for item in nota["itens"]:
        r = client.put(
            f"/notas/{nota['id']}/itens/{item['id']}/variante",
            json={"produto_id": produto, "nova": {}},
            headers=LAURA,
        )
        assert r.status_code == 200, r.text
    return dict(client.get(f"/notas/{nota['id']}").json())


def test_desconto_da_nota_e_rateado_e_a_soma_dos_pagos_bate_com_o_total(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    produto = novo_produto(client, "diversos")
    nota = nota_lida(client, consulta, _tres_itens_de_dez(), numero=1, desconto="1.00")
    assert nota["valor_total"] == "29.00"
    nota = _associar_todos(client, nota, produto)

    # R$ 1,00 em três linhas iguais: 0,33 cada, e o centavo que sobra vai para a
    # linha de maior valor (a primeira, no empate).
    assert [i["desconto_rateado"] for i in nota["itens"]] == ["0.34", "0.33", "0.33"]
    assert [i["preco_pago"] for i in nota["itens"]] == ["9.66", "9.67", "9.67"]
    assert _soma_pago(nota) == Decimal(nota["valor_total"])
    # É estimativa: a página só mostra o desconto da nota inteira.
    assert all(i["preco_pago_estimado"] for i in nota["itens"])
    # O preço cheio continua o da nota.
    assert all(i["preco_cheio"] == "10.00" for i in nota["itens"])


def test_o_resto_do_arredondamento_vai_para_a_linha_de_maior_valor(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    produto = novo_produto(client, "diversos")
    itens = [
        Item("PEQUENO", "1", "3.33", codigo="1"),
        Item("GRANDE", "1", "13.34", codigo="2"),
        Item("MEDIO", "1", "7.77", codigo="3"),
    ]
    nota = nota_lida(client, consulta, itens, numero=1, desconto="2.01")
    nota = _associar_todos(client, nota, produto)
    assert _soma_pago(nota) == Decimal(nota["valor_total"]) == Decimal("22.43")
    rateios = {i["descricao_original"]: Decimal(i["desconto_rateado"]) for i in nota["itens"]}
    assert sum(rateios.values()) == Decimal("2.01")
    # Proporcional: o maior leva mais.
    assert rateios["GRANDE"] > rateios["MEDIO"] > rateios["PEQUENO"]


def test_o_rateio_conta_os_itens_ainda_nao_associados(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    produto = novo_produto(client, "diversos")
    nota = nota_lida(client, consulta, _tres_itens_de_dez(), numero=1, desconto="1.00")
    primeiro = nota["itens"][0]
    r = client.put(
        f"/notas/{nota['id']}/itens/{primeiro['id']}/variante",
        json={"produto_id": produto, "nova": {}},
        headers=LAURA,
    )
    assert r.status_code == 200
    # Só um item associado, mas a parte dele é a mesma de quando os três estão.
    assert (r.json()["desconto_rateado"], r.json()["preco_pago"]) == ("0.34", "9.66")
    sem_variante = client.get(f"/notas/{nota['id']}").json()["itens"][1]
    assert sem_variante["preco_pago"] is None


def test_desconto_de_linha_e_da_nota_inteira(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    produto = novo_produto(client, "diversos")
    nota = nota_lida(client, consulta, _tres_itens_de_dez(), numero=1, desconto="3.00")
    # A página do RS não traz desconto por linha; aqui a linha 1 ganha R$ 1,00
    # (o desconto da nota inteira, 3,00, já o inclui: sobram 2,00 para ratear).
    session.execute(
        text(
            "UPDATE compras.nota_itens SET desconto = 1.00 "
            "WHERE nota_fiscal_id = :n AND linha_num = 1"
        ),
        {"n": nota["id"]},
    )
    session.commit()
    nota = _associar_todos(client, nota, produto)

    assert [i["desconto"] for i in nota["itens"]] == ["1.00", "0.00", "0.00"]
    assert [i["desconto_rateado"] for i in nota["itens"]] == ["0.66", "0.67", "0.67"]
    assert [i["preco_pago"] for i in nota["itens"]] == ["8.34", "9.33", "9.33"]
    assert _soma_pago(nota) == Decimal(nota["valor_total"]) == Decimal("27.00")

    h = historico(client, nota["itens"][0]["variante_id"])
    primeiro = h["itens"][0]
    assert (primeiro["desconto_linha"], primeiro["desconto_rateado"], primeiro["desconto"]) == (
        "1.00", "0.66", "1.66",
    )  # fmt: skip


def test_nota_sem_desconto_nao_e_estimativa(client: TestClient, consulta: ConsultaFalsa) -> None:
    produto = novo_produto(client, "diversos")
    nota = nota_lida(client, consulta, _tres_itens_de_dez(), numero=1)
    nota = _associar_todos(client, nota, produto)
    assert not any(i["preco_pago_estimado"] for i in nota["itens"])
    assert _soma_pago(nota) == Decimal("30.00")


# --- consultas ----------------------------------------------------------------------------------


def test_historico_da_variante_e_paginado_do_mais_recente_para_o_mais_antigo(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    for dia, total in (("01", "5.00"), ("08", "5.50"), ("15", "6.00")):
        nota = comprar(
            client, consulta, leite, "LEITE 1L", quantidade="1", total=total,
            emissao=f"{dia}/11/2026 09:00:00", nova={"medida_base": "ml", "conteudo": "1000"},
        )  # fmt: skip
    variante = nota["itens"][0]["variante_id"]
    h = historico(client, variante, limite=2)
    assert (h["total"], h["limite"], h["offset"]) == (3, 2, 0)
    assert [i["preco_pago"] for i in h["itens"]] == ["6.00", "5.50"]
    assert h["variante"]["nome"] == "LEITE 1L"
    h2 = historico(client, variante, limite=2, offset=2)
    assert [i["preco_pago"] for i in h2["itens"]] == ["5.00"]
    assert client.get("/precos/variantes/999999").status_code == 404


def test_agregado_do_produto_por_variante_e_por_mercado(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    medida = {"medida_base": "ml", "conteudo": "1000"}
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="5.00", nova=medida,
            emissao="01/11/2026 09:00:00")  # fmt: skip
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="7.00", nova=medida,
            emissao="10/11/2026 09:00:00")  # fmt: skip
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="6.00", nova=medida,
            emissao="05/11/2026 09:00:00", cnpj=CNPJ_B)  # fmt: skip

    r = client.get(f"/precos/produtos/{leite}")
    assert r.status_code == 200, r.text
    agregado = r.json()
    (variante,) = agregado["por_variante"]
    estatistica = (variante["ultimo_comparavel"], variante["minimo"], variante["maximo"])
    assert (*estatistica, variante["media"]) == (
        "7.0000", "5.0000", "7.0000", "6.0000",
    )  # fmt: skip
    assert variante["compras"] == 3
    por_mercado = {m["mercado_nome"]: m for m in agregado["por_mercado"]}
    assert por_mercado["MERCADO 11"]["ultimo_comparavel"] == "7.0000"
    assert por_mercado["MERCADO 11"]["media"] == "6.0000"
    assert por_mercado["MERCADO 44"]["ultimo_comparavel"] == "6.0000"

    # `desde` corta o que veio antes.
    recente = client.get(f"/precos/produtos/{leite}", params={"desde": "2026-11-06"}).json()
    assert recente["por_variante"][0]["compras"] == 1
    assert recente["por_variante"][0]["minimo"] == "7.0000"
    assert client.get("/precos/produtos/999999").status_code == 404


def test_onde_mais_barato_usa_o_ultimo_preco_de_cada_mercado_na_janela(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    medida = {"medida_base": "ml", "conteudo": "1000"}

    def compra(cnpj: str, total: str, emissao: str) -> None:
        comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total=total, nova=medida,
                emissao=emissao, cnpj=cnpj)  # fmt: skip

    # A: média cara, mas o último é o mais barato. B: já foi barato, o último não é.
    compra(CNPJ_A, "8.00", "01/10/2026 09:00:00")
    compra(CNPJ_A, "5.50", "10/11/2026 09:00:00")
    compra(CNPJ_B, "4.00", "20/10/2026 09:00:00")
    compra(CNPJ_B, "6.20", "12/11/2026 09:00:00")
    # C é o mais barato de todos, mas há 120 dias: fora da janela de 90.
    compra(CNPJ_C, "3.00", "20/07/2026 09:00:00")

    r = client.get("/precos/onde-mais-barato", params={"produto_id": leite})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["produto_nome"], corpo["dias"]) == ("leite", 90)
    assert [
        (m["posicao"], m["mercado_nome"], m["comparavel"], m["por"]) for m in corpo["ranking"]
    ] == [
        (1, "MERCADO 11", "5.5000", "l"),
        (2, "MERCADO 44", "6.2000", "l"),
    ]
    assert corpo["ranking"][0]["dias_atras"] == 7  # 10/11 a 17/11
    assert corpo["ranking"][1]["dias_atras"] == 5
    assert corpo["ranking"][0]["variante_nome"] == "LEITE 1L"

    # Janela maior traz o C, o mais barato.
    longa = client.get("/precos/onde-mais-barato", params={"produto_id": leite, "dias": 150}).json()
    assert [m["mercado_nome"] for m in longa["ranking"]] == [
        "MERCADO 77",
        "MERCADO 11",
        "MERCADO 44",
    ]
    # Janela curta tira o mercado A (10/11 está a 7 dias; 6 dias não o alcança).
    curta = client.get("/precos/onde-mais-barato", params={"produto_id": leite, "dias": 6}).json()
    assert [m["mercado_nome"] for m in curta["ranking"]] == ["MERCADO 44"]


def test_onde_mais_barato_aceita_o_nome_do_produto(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "Leite Integral")
    novo_produto(client, "leite desnatado")
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="5.00",
            emissao="10/11/2026 09:00:00", nova=MEDIDA_1L)  # fmt: skip

    # Sem caixa nem acento, e o nome pode ser parte dele quando só um serve.
    for busca in ("leite integral", "LEITE  INTEGRAL", "integral"):
        r = client.get("/precos/onde-mais-barato", params={"busca": busca})
        assert r.status_code == 200, (busca, r.text)
        assert r.json()["produto_id"] == leite
        assert len(r.json()["ranking"]) == 1

    # "leite" serve a dois produtos: 409 com os candidatos.
    r = client.get("/precos/onde-mais-barato", params={"busca": "leite"})
    assert r.status_code == 409
    assert {c["nome"] for c in r.json()["candidatos"]} == {"Leite Integral", "leite desnatado"}

    assert client.get("/precos/onde-mais-barato", params={"busca": "caviar"}).status_code == 404
    assert client.get("/precos/onde-mais-barato").status_code == 422


def test_precos_do_mercado_comparam_com_a_media_dos_outros(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    leite = novo_produto(client, "leite")
    medida = {"medida_base": "ml", "conteudo": "1000"}
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="6.00", nova=medida,
            emissao="10/11/2026 09:00:00", cnpj=CNPJ_A)  # fmt: skip
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="4.00", nova=medida,
            emissao="01/11/2026 09:00:00", cnpj=CNPJ_B)  # fmt: skip
    comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="5.00", nova=medida,
            emissao="05/11/2026 09:00:00", cnpj=CNPJ_B)  # fmt: skip
    mercado_a = client.get("/mercados").json()
    id_a = next(m["id"] for m in mercado_a if m["cnpj"] == CNPJ_A)

    r = client.get(f"/precos/mercados/{id_a}")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert (corpo["mercado_nome"], corpo["total"]) == ("MERCADO 11", 1)
    (linha,) = corpo["itens"]
    assert (linha["produto_nome"], linha["por"], linha["ultimo_comparavel"]) == (
        "leite",
        "l",
        "6.0000",
    )
    # Os outros mercados pagaram em média R$ 4,50/L: este está 33,3% acima.
    assert (linha["media_outros_mercados"], linha["diferenca_percentual"]) == ("4.5000", "33.3")
    assert client.get("/precos/mercados/999999").status_code == 404


def test_preco_ignora_nota_apagada(client: TestClient, consulta: ConsultaFalsa) -> None:
    leite = novo_produto(client, "leite")
    nota = comprar(client, consulta, leite, "LEITE 1L", quantidade="1", total="5.00",
                   emissao="10/11/2026 09:00:00", nova=MEDIDA_1L)  # fmt: skip
    variante = nota["itens"][0]["variante_id"]
    assert historico(client, variante)["total"] == 1
    client.delete(f"/notas/{nota['id']}", headers=LAURA)
    assert historico(client, variante)["total"] == 0
    assert client.get("/precos", params={"produto_id": leite}).json() == []
