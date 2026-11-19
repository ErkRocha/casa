"""Duas notas reais anonimizadas do mesmo mercado (Zaffari, 17/10 e 15/11/2026).

A Consulta Completa não traz GTIN: o mesmo item tem o mesmo código interno nas
duas notas, e é por ele que a segunda já vem associada à variante que a
primeira ensinou. O histórico de preço junta as duas compras.

Páginas em `tests/amostras/` (anonimizadas; ver o README de lá). A SEFAZ é falsa.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from tests.apoio import LAURA
from tests.nfce_apoio import ConsultaFalsa, chave, url_qr
from tests.test_notas import novo_produto

AMOSTRAS = Path(__file__).parent / "amostras"
NOVEMBRO = AMOSTRAS / "nfce_rs_anonimizada.html"
OUTUBRO = AMOSTRAS / "nfce_rs_anonimizada_out.html"
CNPJ_ZAFFARI = "93015006002914"
SUCO = "SUCO NATURALE LARANJA INT 3L"


def _ler(client: TestClient, consulta: ConsultaFalsa, pagina: Path, numero: int) -> dict[str, Any]:
    c = chave(cnpj=CNPJ_ZAFFARI, numero=numero)
    consulta.paginas[c] = pagina.read_bytes()
    r = client.post("/notas", json={"entrada": url_qr(c)}, headers=LAURA)
    assert r.status_code == 201, r.text
    nota: dict[str, Any] = r.json()
    assert nota["status"] == "lida", nota
    assert nota["leitor_versao"] == "sefaz-rs-completa-1"
    return nota


def _linha(nota: dict[str, Any], descricao: str) -> dict[str, Any]:
    (item,) = [i for i in nota["itens"] if i["descricao_original"] == descricao]
    return dict(item)


def _associar(
    client: TestClient, nota: dict[str, Any], item: dict[str, Any], **corpo: Any
) -> dict[str, Any]:
    r = client.put(f"/notas/{nota['id']}/itens/{item['id']}/variante", json=corpo, headers=LAURA)
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_suco_da_primeira_nota_ja_vem_associado_na_segunda(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    novembro = _ler(client, consulta, NOVEMBRO, 1)
    assert (novembro["valor_total"], len(novembro["itens"])) == ("398.56", 24)
    assert novembro["forma_pagamento_nota"] == "Cartão de Crédito"
    assert novembro["sem_produto"] == 24

    suco_nov = _linha(novembro, SUCO)
    assert suco_nov["codigo"] == "1095728"
    assert suco_nov["preco_cheio"] == "29.98"
    # O tamanho está na descrição: só sugestão, até o usuário confirmar.
    assert suco_nov["sugestao_medida"] == {"medida_base": "ml", "conteudo": "3000.000"}

    produto = novo_produto(client, "suco de laranja")
    associado = _associar(
        client,
        novembro,
        suco_nov,
        produto_id=produto,
        nova={"medida_base": "ml", "conteudo": "3000"},
    )
    variante = associado["variante_id"]
    ficha = client.get(f"/variantes/{variante}").json()
    assert (ficha["produto_nome"], ficha["medida_base"], ficha["conteudo"]) == (
        "suco de laranja",
        "ml",
        "3000.000",
    )
    # A variante guardou o código do Zaffari, sem zeros, e o GTIN continua vazio.
    assert [(c["codigo"], c["mercado_id"]) for c in ficha["codigos"]] == [
        ("1095728", novembro["mercado_id"])
    ]
    assert ficha["gtin"] is None

    outubro = _ler(client, consulta, OUTUBRO, 2)
    assert (outubro["valor_total"], len(outubro["itens"])) == ("323.03", 7)
    assert outubro["mercado_id"] == novembro["mercado_id"]
    suco_out = _linha(outubro, SUCO)
    assert suco_out["codigo"] == "1095728"
    # Já associado, sozinho, à MESMA variante.
    assert suco_out["variante_id"] == variante
    assert suco_out["produto_id"] == produto
    assert suco_out["origem_associacao"] == "apelido"
    assert outubro["sem_produto"] == 6

    # Duas compras do mesmo suco, a mesma R$ 29,98: R$ 9,99 o litro.
    r = client.get(f"/precos/variantes/{variante}")
    assert r.status_code == 200, r.text
    historico = r.json()
    assert historico["total"] == 2
    assert [(i["data"][:10], i["preco_pago"]) for i in historico["itens"]] == [
        ("2026-11-15", "29.98"),
        ("2026-10-17", "29.98"),
    ]
    for compra in historico["itens"]:
        assert compra["comparavel"]["por"] == "l"
        assert Decimal(compra["comparavel"]["valor"]).quantize(Decimal("0.01")) == Decimal("9.99")
        assert compra["preco_pago_estimado"] is False

    onde = client.get("/precos/onde-mais-barato", params={"busca": "suco de laranja"}).json()
    assert [(m["por"], m["data"][:10]) for m in onde["ranking"]] == [("l", "2026-11-15")]


def test_pao_cacetinho_pesado_em_kg_da_preco_por_quilo(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    novembro = _ler(client, consulta, NOVEMBRO, 1)
    pao = _linha(novembro, "PAO CACETINHO")
    assert (pao["quantidade"], pao["unidade"], pao["valor_total"]) == ("0.512", "KG", "8.14")

    produto = novo_produto(client, "pão")
    # KG na nota marca a variante como pesada, sem perguntar.
    associado = _associar(client, novembro, pao, produto_id=produto, nova={})
    assert associado["comparavel"] is not None
    assert associado["comparavel"]["por"] == "kg"
    # 8,14 / 0,5119 kg = 15,90 o quilo (o preço da gôndola).
    assert Decimal(associado["comparavel"]["valor"]).quantize(Decimal("0.01")) == Decimal("15.90")
    ficha = client.get(f"/variantes/{associado['variante_id']}").json()
    assert (ficha["pesada"], ficha["medida_base"], ficha["conteudo"]) == (True, "g", None)
