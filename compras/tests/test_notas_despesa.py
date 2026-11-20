"""A nota e a despesa de finanças (D-33): sugestão, ligação com transação ou
pendente, consolidação depois da sync e "lançar despesa pela nota".

Finanças é falsa (`tests.financas_apoio`) e a SEFAZ também: nenhuma rede.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from compras.financas import (
    FormaPagamentoResumo,
    PendenteResumo,
    SituacaoTransacao,
    TransacaoResumo,
)
from tests.apoio import LAURA
from tests.financas_apoio import FinancasFalsa
from tests.nfce_apoio import CNPJ_B, ConsultaFalsa, Item
from tests.test_notas import associar, nota_lida

LEITE = Item("LEITE INTEG FICTICIO 1L", "2", "9.98", codigo="7891234567895")
ARROZ = Item("ARROZ FICTICIO 5KG", "1", "30.00", codigo="7890000000017")
DIA = date(2026, 11, 2)  # a emissão padrão da página de teste (10h15 em SP)


def _forma_da_nota(session: Session, nota_id: int, forma: str | None) -> None:
    session.execute(
        text("UPDATE compras.notas_fiscais SET forma_pagamento_nota = :f WHERE id = :i"),
        {"f": forma, "i": nota_id},
    )
    session.commit()


def _tx(
    id_: int,
    dia: date = DIA,
    valor: str = "9.98",
    forma: str | None = None,
    tipo: str | None = None,
    **kw: Any,
) -> TransacaoResumo:
    return TransacaoResumo(id_, dia, Decimal(valor), "MERCADO", forma, tipo, **kw)


def _pend(
    id_externo: str,
    dia: date = DIA,
    valor: str = "9.98",
    forma: str | None = None,
    tipo: str | None = None,
) -> PendenteResumo:
    return PendenteResumo(id_externo, dia, Decimal(valor), "MERCADO", forma, tipo)


def _nota(client: TestClient, consulta: ConsultaFalsa, **kw: Any) -> dict[str, Any]:
    return nota_lida(client, consulta, [LEITE], **kw)


def _ligar(client: TestClient, nota_id: int, corpo: dict[str, Any]) -> Any:
    return client.put(f"/notas/{nota_id}/transacao", json=corpo, headers=LAURA)


# --- sugestão -----------------------------------------------------------------------


def test_sugestao_junta_transacoes_e_pendentes_de_um_dia_antes_a_um_depois(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [
        _tx(1, date(2026, 11, 1)),
        _tx(2, date(2026, 11, 3)),
        _tx(3, date(2026, 11, 4)),  # dois dias depois: fora
        _tx(4, valor="9.99"),  # valor diferente: fora
    ]
    fin.pendentes_do_cartao = [_pend("p-1", date(2026, 11, 3)), _pend("p-2", date(2026, 10, 30))]

    r = client.get(f"/notas/{nota['id']}/sugestoes-transacao")
    assert r.status_code == 200, r.text
    achadas = r.json()
    assert [(s["tipo"], s.get("transacao_id"), s.get("id_externo")) for s in achadas] == [
        ("transacao", 1, None),
        ("transacao", 2, None),
        ("pendente", None, "p-1"),
    ]
    assert {"data", "valor", "descricao", "cartao"} <= set(achadas[0])
    assert fin.pedidos == [(date(2026, 11, 1), date(2026, 11, 3), Decimal("9.98"))]


def test_a_forma_da_nota_ordena_primeiro_e_depois_o_dia_mais_proximo(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa, session: Session
) -> None:
    nota = _nota(client, consulta)
    _forma_da_nota(session, nota["id"], "Cartão de Crédito")
    fin.transacoes = [
        _tx(1, DIA, forma="Pix Banco", tipo="pix"),
        _tx(2, date(2026, 11, 3), forma="Cartão Nubank", tipo="credito"),
        _tx(3, date(2026, 11, 1), forma="Débito", tipo="debito"),
    ]
    fin.pendentes_do_cartao = [_pend("p-1", DIA, forma="Cartão Nubank", tipo="credito")]

    ids = [
        s.get("transacao_id") or s["id_externo"]
        for s in client.get(f"/notas/{nota['id']}/sugestoes-transacao").json()
    ]
    # Crédito primeiro (o do mesmo dia antes do de um dia depois), o resto pelo dia.
    assert ids == ["p-1", 2, 1, 3]
    combinam = [
        s["forma_combina"] for s in client.get(f"/notas/{nota['id']}/sugestoes-transacao").json()
    ]
    assert combinam == [True, True, False, False]


def test_forma_desconhecida_ou_ausente_nao_muda_a_ordem(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa, session: Session
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [
        _tx(1, date(2026, 11, 3), forma="Pix", tipo="pix"),
        _tx(2, DIA, forma="Cartão", tipo="credito"),
    ]
    for forma in (None, "Vale Refeição"):
        _forma_da_nota(session, nota["id"], forma)
        achadas = client.get(f"/notas/{nota['id']}/sugestoes-transacao").json()
        assert [s["transacao_id"] for s in achadas] == [2, 1]
        assert not any(s["forma_combina"] for s in achadas)


def test_pix_e_dinheiro_e_debito_tem_tipo_proprio(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa, session: Session
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [
        _tx(1, DIA, tipo="credito"),
        _tx(2, date(2026, 11, 3), tipo="pix"),
        _tx(3, date(2026, 11, 1), tipo="dinheiro"),
        _tx(4, DIA, tipo="debito"),
    ]
    for forma, primeiro in [("Pix", 2), ("Dinheiro", 3), ("Cartão de Débito", 4)]:
        _forma_da_nota(session, nota["id"], forma)
        achadas = client.get(f"/notas/{nota['id']}/sugestoes-transacao").json()
        assert achadas[0]["transacao_id"] == primeiro, forma


def test_a_forma_lida_pelo_qr_code_ordena_a_sugestao(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    # Sem UPDATE: a forma vem da página do QR code, pelo leitor.
    nota = _nota(client, consulta, formas=[("Cartão de Débito", "9.98")])
    assert nota["forma_pagamento_nota"] == "Cartão de Débito"
    fin.transacoes = [_tx(1, DIA, tipo="credito"), _tx(2, date(2026, 11, 3), tipo="debito")]
    achadas = client.get(f"/notas/{nota['id']}/sugestoes-transacao").json()
    assert [(s["transacao_id"], s["forma_combina"]) for s in achadas] == [(2, True), (1, False)]


# --- ligar --------------------------------------------------------------------------


def test_liga_a_transacao_ou_a_pendente_um_de_cada_vez(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [_tx(7)]
    fin.pendentes_do_cartao = [_pend("p-1")]

    r = _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})
    assert r.status_code == 200, r.text
    assert (r.json()["transacao_id"], r.json()["pendente_id_externo"]) == (None, "p-1")

    # Trocar para a transação limpa a pendente (a check do banco recusa os dois).
    r = _ligar(client, nota["id"], {"transacao_id": 7})
    assert (r.json()["transacao_id"], r.json()["pendente_id_externo"]) == (7, None)

    r = _ligar(client, nota["id"], {})
    assert (r.json()["transacao_id"], r.json()["pendente_id_externo"]) == (None, None)
    _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})
    r = _ligar(client, nota["id"], {"transacao_id": None, "pendente_id_externo": None})
    assert r.json()["pendente_id_externo"] is None


def test_ligar_exige_um_so_e_que_exista_em_financas(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [_tx(7)]
    fin.pendentes_do_cartao = [_pend("p-1")]

    assert (
        _ligar(client, nota["id"], {"transacao_id": 7, "pendente_id_externo": "p-1"}).status_code
        == 422
    )
    assert _ligar(client, nota["id"], {"transacao_id": 404}).status_code == 422
    assert _ligar(client, nota["id"], {"pendente_id_externo": "nao-existe"}).status_code == 422
    assert _ligar(client, 9999, {"transacao_id": 7}).status_code == 404
    assert client.get(f"/notas/{nota['id']}").json()["transacao_id"] is None


def test_ligar_exige_quem(client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [_tx(7)]
    assert client.put(f"/notas/{nota['id']}/transacao", json={"transacao_id": 7}).status_code == 400


# --- consolidar ---------------------------------------------------------------------


def test_pendente_que_virou_transacao_passa_para_ela_sem_perguntar(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa, session: Session
) -> None:
    nota = _nota(client, consulta)
    fin.pendentes_do_cartao = [_pend("p-1")]
    _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})

    # Ainda pendente: nada muda.
    r = client.post("/notas/consolidar-ligacoes")
    assert r.status_code == 200, r.text
    assert r.json() == {"verificadas": 1, "consolidadas": 0, "desfeitas": 0, "movidas": 0}
    assert client.get(f"/notas/{nota['id']}").json()["pendente_id_externo"] == "p-1"

    # A Pluggy confirmou: a pendente some e a transação nasce com o mesmo id.
    fin.pendentes_do_cartao = []
    fin.transacoes = [_tx(55)]
    fin.pluggy = {"p-1": 55}
    r = client.post("/notas/consolidar-ligacoes")
    assert r.json() == {"verificadas": 1, "consolidadas": 1, "desfeitas": 0, "movidas": 0}
    visto = client.get(f"/notas/{nota['id']}").json()
    assert (visto["transacao_id"], visto["pendente_id_externo"]) == (55, None)

    # Idempotente.
    assert client.post("/notas/consolidar-ligacoes").json() == {
        "verificadas": 1,
        "consolidadas": 0,
        "desfeitas": 0,
        "movidas": 0,
    }
    autores = session.execute(
        text(
            "SELECT DISTINCT autor FROM compras.auditoria "
            "WHERE tabela = 'notas_fiscais' AND acao = 'UPDATE' ORDER BY 1"
        )
    ).scalars()
    assert "leitura_nfce" in set(autores)


def test_pendente_cancelada_devolve_a_nota_a_fila_sem_despesa(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.pendentes_do_cartao = [_pend("p-1")]
    _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})

    fin.pendentes_do_cartao = []  # sumiu e não virou transação
    r = client.post("/notas/consolidar-ligacoes")
    assert r.json() == {"verificadas": 1, "consolidadas": 0, "desfeitas": 1, "movidas": 0}
    visto = client.get(f"/notas/{nota['id']}").json()
    assert (visto["transacao_id"], visto["pendente_id_externo"]) == (None, None)


def test_transacao_juntada_pela_revisao_leva_a_nota_para_a_do_banco(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [_tx(1000, lancada_pela_nota=True)]
    _ligar(client, nota["id"], {"transacao_id": 1000})

    # A revisão juntou: a lançada pela nota foi apagada e aponta para a do banco.
    fin.transacoes = [_tx(2000, forma="Cartão da Laura", tipo="credito")]
    fin.situacoes = {1000: SituacaoTransacao(1000, False, 2000)}
    r = client.post("/notas/consolidar-ligacoes")
    assert r.json() == {"verificadas": 1, "consolidadas": 0, "desfeitas": 0, "movidas": 1}
    assert client.get(f"/notas/{nota['id']}").json()["transacao_id"] == 2000
    assert client.post("/notas/consolidar-ligacoes").json()["movidas"] == 0


def test_consolidar_segue_a_cadeia_de_substitutas(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.transacoes = [_tx(1)]
    _ligar(client, nota["id"], {"transacao_id": 1})
    fin.transacoes = [_tx(3)]
    fin.situacoes = {1: SituacaoTransacao(1, False, 2), 2: SituacaoTransacao(2, False, 3)}
    client.post("/notas/consolidar-ligacoes")
    assert client.get(f"/notas/{nota['id']}").json()["transacao_id"] == 3


def test_consolidar_com_financas_fora_nao_altera_nada(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.pendentes_do_cartao = [_pend("p-1")]
    _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})
    fin.indisponivel = True
    assert client.post("/notas/consolidar-ligacoes").status_code == 502
    fin.indisponivel = False
    assert client.get(f"/notas/{nota['id']}").json()["pendente_id_externo"] == "p-1"


def test_nota_sem_ligacao_fica_sem_despesa_e_nao_atrapalha(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    assert client.post("/notas/consolidar-ligacoes").json()["verificadas"] == 0
    visto = client.get(f"/notas/{nota['id']}").json()
    assert visto["transacao_id"] is None and visto["pendente_id_externo"] is None
    # Segue lida, com itens e preços, sem despesa.
    assert visto["status"] == "lida"


# --- lançar despesa pela nota -------------------------------------------------------


def _secao(client: TestClient, nome: str) -> int:
    r = client.post("/secoes", json={"nome": nome}, headers=LAURA)
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _produto_na_secao(client: TestClient, nome: str, secao_id: int) -> int:
    r = client.post(
        "/produtos",
        json={"nome": nome, "secao_id": secao_id, "id_cliente": str(uuid.uuid4())},
        headers=LAURA,
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def _categoria_da_secao(client: TestClient, secao_id: int, categoria: int | None) -> None:
    r = client.patch(
        f"/secoes/{secao_id}", json={"categoria_id_financas": categoria}, headers=LAURA
    )
    assert r.status_code == 200, r.text


FORMAS = [
    FormaPagamentoResumo(1, "Cartão da Laura", "credito"),
    FormaPagamentoResumo(2, "Pix Banco", "pix"),
]


def test_previa_traz_o_que_a_nota_sabe_e_as_formas_de_financas(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa, session: Session
) -> None:
    nota = _nota(client, consulta)
    _forma_da_nota(session, nota["id"], "Cartão de Crédito")
    fin.formas = FORMAS

    r = client.get(f"/notas/{nota['id']}/lancar-despesa")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["valor"] == "9.98"
    assert corpo["data"] == "2026-11-02"
    assert corpo["descricao"] == "MERCADO FICTICIO DO BAIRRO LTDA"
    assert corpo["forma_pagamento_nota"] == "Cartão de Crédito"
    assert corpo["forma_pagamento_id_sugerida"] == 1
    assert [f["apelido"] for f in corpo["formas_pagamento"]] == ["Cartão da Laura", "Pix Banco"]
    assert (corpo["categoria_id_sugerida"], corpo["categoria_origem"]) == (None, None)


def test_categoria_sugerida_e_a_de_mais_valor_entre_os_itens(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    fin.categorias_de_despesa = {10, 20}
    mercearia = _secao(client, "Mercearia")
    limpeza = _secao(client, "Limpeza")
    _categoria_da_secao(client, mercearia, 10)
    _categoria_da_secao(client, limpeza, 20)
    leite = _produto_na_secao(client, "leite", mercearia)
    arroz = _produto_na_secao(client, "arroz", mercearia)
    sabao = _produto_na_secao(client, "sabão", limpeza)
    sabao_item = Item("SABAO FICTICIO", "1", "25.00", codigo="7890000000024")
    nota = nota_lida(client, consulta, [LEITE, ARROZ, sabao_item])
    for linha, produto in [(1, leite), (2, arroz), (3, sabao)]:
        assert associar(client, nota, linha, produto).status_code == 200

    corpo = client.get(f"/notas/{nota['id']}/lancar-despesa").json()
    # Mercearia soma 39,98; Limpeza, 25,00.
    assert (corpo["categoria_id_sugerida"], corpo["categoria_origem"]) == (10, "itens")


def test_secao_sem_categoria_nao_conta_e_sem_nada_cai_na_ultima_do_mercado(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    fin.categorias_de_despesa = {10}
    fin.formas = FORMAS
    # Uma nota anterior do mesmo mercado, ligada a uma despesa com categoria.
    anterior = nota_lida(client, consulta, [ARROZ], numero=1)
    fin.transacoes = [_tx(500, valor="30.00")]
    fin.categoria_da = {500: 10}
    _ligar(client, anterior["id"], {"transacao_id": 500})
    # Outro mercado, ligada a outra categoria: não vale.
    outro = nota_lida(client, consulta, [ARROZ], numero=2, cnpj=CNPJ_B)
    fin.transacoes.append(_tx(501, valor="30.00"))
    fin.categoria_da[501] = 99
    _ligar(client, outro["id"], {"transacao_id": 501})

    nova = _nota(client, consulta, numero=3)
    sem_categoria = _secao(client, "Sem categoria de finanças")
    assert (
        associar(client, nova, 1, _produto_na_secao(client, "leite", sem_categoria)).status_code
        == 200
    )

    corpo = client.get(f"/notas/{nova['id']}/lancar-despesa").json()
    assert (corpo["categoria_id_sugerida"], corpo["categoria_origem"]) == (10, "ultima_do_mercado")

    # Mercado sem nenhuma anterior ligada: sem sugestão.
    sozinha = nota_lida(client, consulta, [LEITE], numero=4, cnpj="55666777000199")
    corpo = client.get(f"/notas/{sozinha['id']}/lancar-despesa").json()
    assert corpo["categoria_id_sugerida"] is None


def test_lancar_cria_a_despesa_marcada_liga_e_marca_a_nota(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.categorias_de_despesa = {10}
    corpo = {
        "data": "2026-11-02",
        "valor": "9.98",
        "descricao": "Mercado do Bairro",
        "pessoa_id": 3,
        "forma_pagamento_id": 1,
        "categoria_id": 10,
    }
    r = client.post(f"/notas/{nota['id']}/lancar-despesa", json=corpo, headers=LAURA)
    assert r.status_code == 200, r.text
    assert r.json()["transacao_id"] == 1001
    assert r.json()["despesa_lancada_pela_nota"] is True
    assert r.json()["pendente_id_externo"] is None

    (criada,) = fin.criadas
    assert (criada.data, criada.valor, criada.descricao) == (
        DIA,
        Decimal("9.98"),
        "Mercado do Bairro",
    )
    assert (criada.pessoa_id, criada.forma_pagamento_id, criada.categoria_id) == (3, 1, 10)
    assert criada.local_nome == "MERCADO FICTICIO DO BAIRRO LTDA"

    visto = client.get(f"/notas/{nota['id']}").json()
    assert visto["transacao_id"] == 1001 and visto["despesa_lancada_pela_nota"] is True

    # Já ligada: 409, nos dois.
    assert (
        client.post(f"/notas/{nota['id']}/lancar-despesa", json=corpo, headers=LAURA).status_code
        == 409
    )
    assert client.get(f"/notas/{nota['id']}/lancar-despesa").status_code == 409
    assert len(fin.criadas) == 1


def test_lancar_conjunto_e_sem_categoria(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    corpo = {"data": "2026-11-03", "valor": "10.00", "descricao": "x", "forma_pagamento_id": 2}
    r = client.post(f"/notas/{nota['id']}/lancar-despesa", json=corpo, headers=LAURA)
    assert r.status_code == 200, r.text
    assert (fin.criadas[0].pessoa_id, fin.criadas[0].categoria_id) == (None, None)


def test_lancar_com_financas_fora_da_503_e_nao_grava_nada(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.indisponivel = True
    corpo = {"data": "2026-11-02", "valor": "9.98", "descricao": "x", "forma_pagamento_id": 1}
    r = client.post(f"/notas/{nota['id']}/lancar-despesa", json=corpo, headers=LAURA)
    assert r.status_code == 503, r.text
    fin.indisponivel = False
    visto = client.get(f"/notas/{nota['id']}").json()
    assert (visto["transacao_id"], visto["despesa_lancada_pela_nota"]) == (None, False)
    assert fin.criadas == []


def test_lancar_recusado_por_financas_e_422_e_categoria_de_receita_tambem(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    base = {"data": "2026-11-02", "valor": "9.98", "descricao": "x", "forma_pagamento_id": 1}
    r = client.post(
        f"/notas/{nota['id']}/lancar-despesa", json={**base, "categoria_id": 77}, headers=LAURA
    )
    assert r.status_code == 422  # não é categoria de despesa
    fin.recusa = "forma de pagamento inexistente"
    r = client.post(f"/notas/{nota['id']}/lancar-despesa", json=base, headers=LAURA)
    assert r.status_code == 422 and "recusou" in r.json()["detail"]
    assert client.get(f"/notas/{nota['id']}").json()["transacao_id"] is None
    # Valor e quem são obrigatórios.
    assert (
        client.post(
            f"/notas/{nota['id']}/lancar-despesa", json={**base, "valor": "0"}, headers=LAURA
        ).status_code
        == 422
    )
    assert client.post(f"/notas/{nota['id']}/lancar-despesa", json=base).status_code == 400


def test_lancar_pela_nota_ligada_a_pendente_tambem_e_409(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = _nota(client, consulta)
    fin.pendentes_do_cartao = [_pend("p-1")]
    _ligar(client, nota["id"], {"pendente_id_externo": "p-1"})
    assert client.get(f"/notas/{nota['id']}/lancar-despesa").status_code == 409


# --- seção com categoria de finanças -----------------------------------------------


def test_secao_guarda_a_categoria_de_finanças_conferida_pela_api(
    client: TestClient, fin: FinancasFalsa
) -> None:
    fin.categorias_de_despesa = {10}
    secao = _secao(client, "Mercearia")
    assert client.get("/secoes").json()[0]["categoria_id_financas"] is None

    r = client.patch(f"/secoes/{secao}", json={"categoria_id_financas": 10}, headers=LAURA)
    assert r.status_code == 200 and r.json()["categoria_id_financas"] == 10
    assert r.json()["nome"] == "Mercearia"

    # Categoria que não é de despesa (ou não existe): 422, e fica a anterior.
    r = client.patch(f"/secoes/{secao}", json={"categoria_id_financas": 11}, headers=LAURA)
    assert r.status_code == 422
    assert client.get("/secoes").json()[0]["categoria_id_financas"] == 10

    # Renomear não mexe na categoria; nulo limpa.
    r = client.patch(f"/secoes/{secao}", json={"nome": "Mercearia seca"}, headers=LAURA)
    assert (r.json()["nome"], r.json()["categoria_id_financas"]) == ("Mercearia seca", 10)
    r = client.patch(f"/secoes/{secao}", json={"categoria_id_financas": None}, headers=LAURA)
    assert r.json()["categoria_id_financas"] is None
    assert client.patch(f"/secoes/{secao}", json={}, headers=LAURA).status_code == 422
    assert client.patch(f"/secoes/{secao}", json={"nome": None}, headers=LAURA).status_code == 422


def test_secao_com_financas_fora_da_502(client: TestClient, fin: FinancasFalsa) -> None:
    secao = _secao(client, "Mercearia")
    fin.indisponivel = True
    r = client.patch(f"/secoes/{secao}", json={"categoria_id_financas": 10}, headers=LAURA)
    assert r.status_code == 502
