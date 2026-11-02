"""Nota fiscal pela API: leitura, deduplicação, associação, preços e sugestão.

A consulta à SEFAZ e a API de finanças são falsas (`dependency_overrides`):
nenhum teste sai da máquina. As páginas são inventadas (`nfce_apoio`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from compras.deps import consulta_publica, financas
from compras.financas import FinancasIndisponivel, TransacaoResumo
from compras.main import app
from compras.nfce.consulta import Resposta
from compras.nfce.leitor_svrs import FUSO
from tests.apoio import ERIK, LAURA, produto_id
from tests.nfce_apoio import CNPJ_A, CNPJ_B, ConsultaFalsa, Item, chave, pagina, url_qr

LEITE = Item("LEITE INTEG FICTICIO 1L", "2", "9.98", codigo="7891234567895")
BANANA = Item("BANANA PRATA KG", "1.5", "10.50", unidade="KG", valor_unitario="7.00")


@dataclass
class FinancasFalsa:
    transacoes: list[TransacaoResumo] = field(default_factory=list)
    indisponivel: bool = False
    pedidos: list[tuple[date, Decimal]] = field(default_factory=list)

    def despesas(self, dia: date, valor: Decimal) -> list[TransacaoResumo]:
        if self.indisponivel:
            raise FinancasIndisponivel("A API de finanças não respondeu: ConnectError.")
        self.pedidos.append((dia, valor))
        return [t for t in self.transacoes if t.data == dia and t.valor == valor]

    def existe(self, transacao_id: int) -> bool:
        return any(t.id == transacao_id for t in self.transacoes)


@pytest.fixture
def consulta() -> Iterator[ConsultaFalsa]:
    falsa = ConsultaFalsa()
    app.dependency_overrides[consulta_publica] = lambda: falsa
    yield falsa
    app.dependency_overrides.pop(consulta_publica, None)


@pytest.fixture
def fin() -> Iterator[FinancasFalsa]:
    falsa = FinancasFalsa()
    app.dependency_overrides[financas] = lambda: falsa
    yield falsa
    app.dependency_overrides.pop(financas, None)


def ler(client: TestClient, entrada: str, quem: dict[str, str] = LAURA) -> Any:
    return client.post("/notas", json={"entrada": entrada}, headers=quem)


def nota_lida(
    client: TestClient, consulta: ConsultaFalsa, itens: list[Item], *, numero: int = 1,
    cnpj: str = CNPJ_A, **kw: Any,
) -> dict[str, Any]:  # fmt: skip
    c = chave(cnpj=cnpj, numero=numero)
    consulta.paginas[c] = pagina(itens, cnpj=cnpj, **kw)
    r = ler(client, url_qr(c))
    assert r.status_code == 201, r.text
    corpo: dict[str, Any] = r.json()
    assert corpo["status"] == "lida", corpo
    return corpo


def novo_produto(client: TestClient, nome: str) -> int:
    import uuid

    r = client.post(
        "/produtos", json={"nome": nome, "id_cliente": str(uuid.uuid4())}, headers=LAURA
    )
    assert r.status_code == 201, r.text
    return int(r.json()["id"])


def associar(client: TestClient, nota: dict[str, Any], linha: int, produto: int) -> Any:
    item = next(i for i in nota["itens"] if i["linha_num"] == linha)
    return client.put(
        f"/notas/{nota['id']}/itens/{item['id']}/produto", json={"produto_id": produto},
        headers=LAURA,
    )  # fmt: skip


# --- leitura e deduplicação ---------------------------------------------------------


def test_le_a_nota_guarda_o_conteudo_e_cria_o_mercado(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    nota = nota_lida(client, consulta, [LEITE, BANANA], desconto="0.48")

    assert nota["chave_acesso"] == chave()
    assert nota["lida_por"] == "Laura"
    assert nota["valor_total"] == "20.00"
    assert nota["desconto_total"] == "0.48"
    assert datetime.fromisoformat(nota["emitida_em"]) == datetime(
        2026, 11, 2, 10, 15, 30, tzinfo=FUSO
    )
    assert nota["leitor_versao"] == "svrs-html-1"
    assert [i["descricao_original"] for i in nota["itens"]] == [LEITE.descricao, BANANA.descricao]
    assert nota["soma_itens"] == "20.48"
    # O desconto da nota inteira aparece como diferença, sem bloquear.
    assert nota["diferenca"] == "-0.48"
    assert nota["sem_produto"] == 2

    mercados = client.get("/mercados").json()
    assert [(m["cnpj"], m["nome"], m["cidade"]) for m in mercados] == [
        (CNPJ_A, "MERCADO FICTICIO DO BAIRRO LTDA", "PORTO ALEGRE")
    ]
    # A resposta da SEFAZ fica inteira, byte a byte.
    guardado = session.execute(
        text("SELECT conteudo_original, conteudo_tipo FROM compras.notas_fiscais")
    ).one()
    assert bytes(guardado[0]) == consulta.paginas[chave()]
    assert guardado[1] == "text/html"
    # O conteúdo bruto não vai na resposta.
    assert "conteudo_original" not in nota


def test_a_mesma_chave_duas_vezes_devolve_a_mesma_nota(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    primeira = nota_lida(client, consulta, [LEITE])
    # Pela chave colada, por outra pessoa: a mesma nota, sem buscar de novo.
    r = ler(client, chave(), ERIK)
    assert r.status_code == 200
    assert r.json()["id"] == primeira["id"]
    assert r.json()["lida_por"] == "Laura"
    assert len(consulta.buscas) == 1
    assert len(client.get("/notas").json()) == 1


def test_duas_leituras_da_mesma_nota_ao_mesmo_tempo_viram_uma() -> None:
    """Os dois celulares leem o mesmo QR code no mesmo instante."""
    c = chave()
    lenta = ConsultaFalsa(paginas={c: pagina([LEITE])})
    original = lenta.buscar

    def devagar(url: str) -> Resposta:
        time.sleep(0.3)
        return original(url)

    lenta.buscar = devagar  # type: ignore[method-assign]
    app.dependency_overrides[consulta_publica] = lambda: lenta
    try:
        largada = threading.Barrier(2)
        respostas: list[tuple[int, int]] = []

        def celular(quem: dict[str, str]) -> None:
            with TestClient(app) as cli:
                largada.wait()
                r = ler(cli, url_qr(c), quem)
                respostas.append((r.status_code, r.json()["id"]))

        fios = [threading.Thread(target=celular, args=(q,)) for q in (LAURA, ERIK)]
        for f in fios:
            f.start()
        for f in fios:
            f.join(timeout=30)
    finally:
        app.dependency_overrides.pop(consulta_publica, None)

    assert sorted(s for s, _ in respostas) == [200, 201]
    assert len({i for _, i in respostas}) == 1
    with TestClient(app) as cli:
        assert len(cli.get("/notas").json()) == 1
        assert len(cli.get("/mercados").json()) == 1


@pytest.mark.parametrize(
    "entrada",
    [
        "https://exemplo.com/?p=" + chave(),
        chave(modelo="55"),
        chave(uf="35"),
        "1234",
    ],
)
def test_entrada_invalida_nao_grava_nada(
    client: TestClient, consulta: ConsultaFalsa, entrada: str
) -> None:
    r = ler(client, entrada)
    assert r.status_code == 422, r.text
    assert consulta.buscas == []
    assert client.get("/notas").json() == []
    assert client.get("/mercados").json() == []


def test_ler_exige_quem(client: TestClient, consulta: ConsultaFalsa) -> None:
    assert client.post("/notas", json={"entrada": chave()}).status_code == 400


# --- erros e releitura ------------------------------------------------------------------


def test_consulta_falhou_fica_com_erro_e_relida_depois(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    consulta.falhar = True
    r = ler(client, url_qr(chave()))
    assert r.status_code == 201
    nota = r.json()
    assert nota["status"] == "erro"
    assert "SEFAZ" in nota["erro_mensagem"]
    assert nota["itens"] == []
    # O mercado já sai do CNPJ da chave, com o CNPJ formatado como nome.
    assert nota["mercado_nome"] == "11.222.333/0001-81"

    consulta.falhar = False
    consulta.paginas[chave()] = pagina([LEITE])
    relida = client.post(f"/notas/{nota['id']}/reler", headers=LAURA)
    assert relida.status_code == 200, relida.text
    assert relida.json()["status"] == "lida"
    assert relida.json()["erro_mensagem"] is None
    assert relida.json()["mercado_nome"] == "MERCADO FICTICIO DO BAIRRO LTDA"
    assert len(relida.json()["itens"]) == 1

    # Lida, não há o que reler.
    assert client.post(f"/notas/{nota['id']}/reler", headers=LAURA).status_code == 409


def test_leitor_nao_entendeu_guarda_o_conteudo_e_rele_sem_buscar(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    consulta.paginas[chave()] = b"<html><body>Pagina diferente</body></html>"
    nota = ler(client, url_qr(chave())).json()
    assert nota["status"] == "erro"
    assert "svrs-html-1" in nota["erro_mensagem"]
    assert session.execute(
        text("SELECT conteudo_original IS NOT NULL FROM compras.notas_fiscais")
    ).scalar_one()

    # Releitura do conteúdo guardado: continua não entendendo, e não busca.
    r = client.post(f"/notas/{nota['id']}/reler", headers=LAURA)
    assert r.json()["status"] == "erro"
    assert len(consulta.buscas) == 1

    # Pedindo, busca de novo.
    consulta.paginas[chave()] = pagina([LEITE])
    r = client.post(f"/notas/{nota['id']}/reler?buscar_de_novo=true", headers=LAURA)
    assert r.json()["status"] == "lida"
    assert len(consulta.buscas) == 2


def test_pagina_de_outro_cnpj_e_erro(client: TestClient, consulta: ConsultaFalsa) -> None:
    consulta.paginas[chave()] = pagina([LEITE], cnpj=CNPJ_B)
    nota = ler(client, url_qr(chave())).json()
    assert nota["status"] == "erro"
    assert "não é o da chave" in nota["erro_mensagem"]
    assert nota["itens"] == []


def test_remover_e_ler_de_novo(client: TestClient, consulta: ConsultaFalsa) -> None:
    nota = nota_lida(client, consulta, [LEITE])
    r = client.delete(f"/notas/{nota['id']}", headers=LAURA)
    assert r.status_code == 200
    assert r.json()["deleted_em"] is not None
    assert client.get("/notas").json() == []
    assert client.get(f"/notas/{nota['id']}").status_code == 404

    de_novo = ler(client, chave())
    assert de_novo.status_code == 201
    assert de_novo.json()["id"] != nota["id"]


def test_descricao_original_e_imutavel(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    nota_lida(client, consulta, [LEITE])
    with pytest.raises(DBAPIError, match="imutável"):
        session.execute(text("UPDATE compras.nota_itens SET descricao_original = 'OUTRA'"))
    session.rollback()


# --- associação e apelidos -----------------------------------------------------------------


def test_associar_cria_apelido_e_a_proxima_nota_vem_associada(
    client: TestClient, consulta: ConsultaFalsa, semeado: None
) -> None:
    leite = produto_id(client, "leite integral")
    primeira = nota_lida(client, consulta, [LEITE, BANANA], numero=1)

    r = associar(client, primeira, 1, leite)
    assert r.status_code == 200, r.text
    assert (r.json()["produto_id"], r.json()["origem_associacao"]) == (leite, "usuario")
    fila = client.get("/notas/itens-sem-produto").json()
    assert [i["descricao_original"] for i in fila] == [BANANA.descricao]

    segunda = nota_lida(client, consulta, [LEITE], numero=2)
    item = segunda["itens"][0]
    # O GTIN é aprendido junto e casa antes do texto.
    assert (item["produto_id"], item["origem_associacao"]) == (leite, "gtin")
    assert segunda["sem_produto"] == 0


def test_texto_aprendido_vale_no_mesmo_mercado_e_em_outro_se_ninguem_discorda(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = novo_produto(client, "banana prata")
    banana_nanica = novo_produto(client, "banana nanica")
    nota_a = nota_lida(client, consulta, [BANANA], numero=1, cnpj=CNPJ_A)
    associar(client, nota_a, 1, banana)

    # Outro mercado, mesmo texto: só um apelido existe, então vale.
    nota_b = nota_lida(client, consulta, [BANANA], numero=2, cnpj=CNPJ_B)
    assert (nota_b["itens"][0]["produto_id"], nota_b["itens"][0]["origem_associacao"]) == (
        banana,
        "apelido",
    )
    # O usuário diz que, no mercado B, esse texto é a nanica.
    associar(client, nota_b, 1, banana_nanica)

    # Mercado A continua com o dele; mercado B com o dele.
    a2 = nota_lida(client, consulta, [BANANA], numero=3, cnpj=CNPJ_A)
    b2 = nota_lida(client, consulta, [BANANA], numero=4, cnpj=CNPJ_B)
    assert a2["itens"][0]["produto_id"] == banana
    assert b2["itens"][0]["produto_id"] == banana_nanica


def test_dois_mercados_discordam_terceiro_fica_sem_produto(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    um = novo_produto(client, "banana prata")
    outro = novo_produto(client, "banana nanica")
    associar(client, nota_lida(client, consulta, [BANANA], numero=1, cnpj=CNPJ_A), 1, um)
    nota_b = nota_lida(client, consulta, [BANANA], numero=2, cnpj=CNPJ_B)
    associar(client, nota_b, 1, outro)

    cnpj_c = "77888999000155"
    terceira = nota_lida(client, consulta, [BANANA], numero=3, cnpj=cnpj_c)
    assert terceira["itens"][0]["produto_id"] is None


def test_correcao_troca_o_apelido_e_reforco_conta_acertos(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    certo = novo_produto(client, "banana prata")
    errado = novo_produto(client, "banana nanica")
    n1 = nota_lida(client, consulta, [BANANA], numero=1)
    associar(client, n1, 1, errado)

    n2 = nota_lida(client, consulta, [BANANA], numero=2)
    assert n2["itens"][0]["produto_id"] == errado
    associar(client, n2, 1, certo)  # corrige
    apelido = session.execute(
        text("SELECT produto_id, acertos, criado_por FROM compras.apelidos")
    ).one()
    assert tuple(apelido) == (certo, 1, "correcao")

    n3 = nota_lida(client, consulta, [BANANA], numero=3)
    assert n3["itens"][0]["produto_id"] == certo
    associar(client, n3, 1, certo)  # reforça
    assert session.execute(text("SELECT acertos FROM compras.apelidos")).scalar_one() == 2


def test_associar_produto_inexistente_ou_item_de_outra_nota(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    n1 = nota_lida(client, consulta, [BANANA], numero=1)
    n2 = nota_lida(client, consulta, [BANANA], numero=2)
    assert associar(client, n1, 1, 999_999).status_code == 404
    item_da_n2 = n2["itens"][0]["id"]
    r = client.put(
        f"/notas/{n1['id']}/itens/{item_da_n2}/produto", json={"produto_id": 1}, headers=LAURA
    )
    assert r.status_code == 404


def test_apelido_de_produto_apagado_nao_associa(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = novo_produto(client, "banana prata")
    associar(client, nota_lida(client, consulta, [BANANA], numero=1), 1, banana)
    assert client.delete(f"/produtos/{banana}", headers=LAURA).status_code == 200
    n2 = nota_lida(client, consulta, [BANANA], numero=2)
    assert n2["itens"][0]["produto_id"] is None


# --- preços ---------------------------------------------------------------------------------


def test_historico_de_preco_por_produto_e_mercado(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = novo_produto(client, "banana prata")

    def compra(numero: int, cnpj: str, unit: str, emissao: str, unidade: str = "KG") -> None:
        item = Item(BANANA.descricao, "1", unit, unidade=unidade, valor_unitario=unit)
        nota = nota_lida(
            client, consulta, [item], numero=numero, cnpj=cnpj, emissao=emissao,
            razao=f"MERCADO {cnpj[:2]}",
        )  # fmt: skip
        if nota["itens"][0]["produto_id"] is None:
            associar(client, nota, 1, banana)

    compra(1, CNPJ_A, "6.99", "01/10/2026 09:00:00")
    compra(2, CNPJ_A, "7.49", "15/10/2026 09:00:00")
    compra(3, CNPJ_A, "5.99", "01/11/2026 09:00:00")
    compra(4, CNPJ_B, "8.10", "02/11/2026 09:00:00")
    # Mesma banana em unidade, no mercado A: não se mistura com o quilo.
    compra(5, CNPJ_A, "1.20", "02/11/2026 09:00:00", unidade="UN")

    linhas = client.get("/precos", params={"produto_id": banana}).json()
    por_chave = {(row["mercado_nome"], row["unidade"]): row for row in linhas}
    assert set(por_chave) == {("MERCADO 11", "KG"), ("MERCADO 11", "UN"), ("MERCADO 44", "KG")}
    mercado_a = por_chave[("MERCADO 11", "KG")]
    assert mercado_a["compras"] == 3
    assert mercado_a["ultimo_preco"] == "5.9900"
    assert mercado_a["preco_min"] == "5.9900"
    assert mercado_a["preco_max"] == "7.4900"
    assert mercado_a["preco_medio"] == "6.8233"
    ultima = datetime.fromisoformat(mercado_a["ultima_compra_em"]).astimezone(FUSO)
    assert ultima.date() == date(2026, 11, 1)
    assert por_chave[("MERCADO 44", "KG")]["ultimo_preco"] == "8.1000"
    unidade = por_chave[("MERCADO 11", "UN")]
    assert (unidade["compras"], unidade["ultimo_preco"]) == (1, "1.2000")
    # O mais barato primeiro, dentro do produto.
    assert [r["ultimo_preco"] for r in linhas] == sorted(r["ultimo_preco"] for r in linhas)


def test_preco_ignora_item_sem_produto_e_nota_apagada(
    client: TestClient, consulta: ConsultaFalsa
) -> None:
    banana = novo_produto(client, "banana prata")
    n1 = nota_lida(client, consulta, [BANANA], numero=1)
    assert client.get("/precos").json() == []  # sem produto, sem preço
    associar(client, n1, 1, banana)
    assert len(client.get("/precos").json()) == 1
    client.delete(f"/notas/{n1['id']}", headers=LAURA)
    assert client.get("/precos").json() == []


# --- sugestão de transação de finanças -------------------------------------------------------


def test_sugere_despesa_do_mesmo_dia_e_valor_e_vincula_quando_confirmado(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    nota = nota_lida(client, consulta, [LEITE], emissao="02/11/2026 23:30:00")
    fin.transacoes = [
        TransacaoResumo(7, date(2026, 11, 2), Decimal("9.98"), "MERCADO FICTICIO", "Nubank"),
        TransacaoResumo(8, date(2026, 11, 2), Decimal("50.00"), "OUTRA", None),
        TransacaoResumo(9, date(2026, 11, 3), Decimal("9.98"), "DIA SEGUINTE", None),
    ]
    r = client.get(f"/notas/{nota['id']}/sugestoes-transacao")
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()] == [7]
    # 23h30 em São Paulo continua sendo dia 2 (em UTC já seria dia 3).
    assert fin.pedidos == [(date(2026, 11, 2), Decimal("9.98"))]
    # Sugerir não vincula.
    assert client.get(f"/notas/{nota['id']}").json()["transacao_id"] is None

    assert (
        client.put(
            f"/notas/{nota['id']}/transacao", json={"transacao_id": 404}, headers=LAURA
        ).status_code
        == 422
    )
    r = client.put(f"/notas/{nota['id']}/transacao", json={"transacao_id": 7}, headers=LAURA)
    assert r.status_code == 200
    assert r.json()["transacao_id"] == 7
    r = client.put(f"/notas/{nota['id']}/transacao", json={"transacao_id": None}, headers=LAURA)
    assert r.json()["transacao_id"] is None


def test_sugestao_de_nota_com_erro_ou_financas_fora(
    client: TestClient, consulta: ConsultaFalsa, fin: FinancasFalsa
) -> None:
    consulta.falhar = True
    com_erro = ler(client, chave(numero=1)).json()
    assert client.get(f"/notas/{com_erro['id']}/sugestoes-transacao").status_code == 422

    consulta.falhar = False
    nota = nota_lida(client, consulta, [LEITE], numero=2)
    fin.indisponivel = True
    r = client.get(f"/notas/{nota['id']}/sugestoes-transacao")
    assert r.status_code == 502
    assert "finanças" in r.json()["detail"]


def test_auditoria_registra_a_leitura_e_quem_associou(
    client: TestClient, consulta: ConsultaFalsa, session: Session
) -> None:
    banana = novo_produto(client, "banana prata")
    nota = nota_lida(client, consulta, [BANANA])
    client.put(
        f"/notas/{nota['id']}/itens/{nota['itens'][0]['id']}/produto",
        json={"produto_id": banana},
        headers=ERIK,
    )
    linhas = session.execute(
        text(
            "SELECT tabela || ':' || acao, string_agg(DISTINCT autor, ',') "
            "FROM compras.auditoria "
            "WHERE tabela IN ('notas_fiscais', 'nota_itens', 'apelidos') GROUP BY 1"
        )
    ).all()
    autores: dict[str, str] = {str(r[0]): str(r[1]) for r in linhas}
    assert autores["notas_fiscais:INSERT"] == "leitura_nfce"
    assert autores["nota_itens:INSERT"] == "leitura_nfce"
    assert autores["nota_itens:UPDATE"] == "Erik"
    assert autores["apelidos:INSERT"] == "Erik"
