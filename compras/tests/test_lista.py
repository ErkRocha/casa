"""Lista: adicionar, comprar, desfazer, tirar, com os dois celulares ao mesmo tempo."""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from compras.db import SessionLocal, definir_autor, engine
from compras.enums import SituacaoItem
from compras.main import app
from compras.models import ItemLista, Produto
from compras.services.lista import ListaService
from tests.apoio import ERIK, LAURA, adicionar, item, produto_id

pytestmark = pytest.mark.usefixtures("semeado")


def _pendentes(session: Session, nome_normalizado: str) -> int:
    session.expire_all()
    return int(
        session.scalar(
            select(func.count())
            .select_from(ItemLista)
            .join(Produto)
            .where(
                Produto.nome_normalizado == nome_normalizado,
                ItemLista.situacao == SituacaoItem.PENDENTE,
                ItemLista.deleted_em.is_(None),
            )
        )
        or 0
    )


# --- quem -------------------------------------------------------------------


def test_escrita_sem_x_quem_e_recusada(client: TestClient) -> None:
    resposta = adicionar(client, "Leite integral 1L", quem={})
    assert resposta.status_code == 400
    assert "X-Quem" in resposta.json()["detail"]
    assert adicionar(client, "Leite integral 1L", quem={"X-Quem": "  "}).status_code == 400


def test_x_quem_vira_autor_na_auditoria(client: TestClient, session: Session) -> None:
    criado = item(client, "Leite integral 1L", quem=ERIK)
    assert criado["adicionado_por"] == "Erik"
    autor = session.execute(
        text(
            "SELECT autor FROM compras.auditoria "
            "WHERE tabela = 'itens_lista' AND registro_id = :id AND acao = 'INSERT'"
        ),
        {"id": criado["id"]},
    ).scalar_one()
    assert autor == "Erik"


# --- adicionar --------------------------------------------------------------


def test_adicionar_produto_conhecido_pelo_nome(client: TestClient) -> None:
    resposta = adicionar(client, "leite INTEGRAL 1l", quantidade="2")
    assert resposta.status_code == 201, resposta.text
    corpo = resposta.json()
    assert corpo["produto_nome"] == "Leite integral 1L"
    assert corpo["secao_nome"] == "Frios e laticínios"
    assert corpo["quantidade"] == "2.000"
    assert corpo["unidade"] == "un"  # a unidade padrão do produto
    assert corpo["situacao"] == "pendente"
    assert corpo["origem"] == "manual"
    assert corpo["ja_estava"] is False


def test_adicionar_produto_novo_cria_em_sem_secao(client: TestClient) -> None:
    corpo = item(client, "Fermento biológico")
    assert corpo["secao_nome"] == "Sem seção"
    assert client.get("/produtos", params={"busca": "fermento"}).json()[0]["nome"] == (
        "Fermento biológico"
    )


def test_produto_id_e_nome_juntos_ou_nenhum_sao_recusados(client: TestClient) -> None:
    leite = produto_id(client, "leite")
    corpo = {"id_cliente": str(uuid.uuid4()), "produto_id": leite, "produto_nome": "Leite"}
    assert client.post("/lista/itens", json=corpo, headers=LAURA).status_code == 422
    vazio = {"id_cliente": str(uuid.uuid4())}
    assert client.post("/lista/itens", json=vazio, headers=LAURA).status_code == 422


def test_dois_leites_um_depois_do_outro_viram_um_item(client: TestClient, session: Session) -> None:
    primeiro = adicionar(client, "Leite integral 1L", quantidade="1", quem=LAURA)
    segundo = adicionar(client, "Leite integral 1L", quantidade="3", quem=ERIK)

    assert primeiro.status_code == 201
    assert segundo.status_code == 200
    assert segundo.json()["ja_estava"] is True
    assert segundo.json()["id"] == primeiro.json()["id"]
    # Não soma nem troca o autor: os dois quiseram dizer a mesma coisa.
    assert segundo.json()["quantidade"] == "1.000"
    assert segundo.json()["adicionado_por"] == "Laura"
    assert _pendentes(session, "LEITE INTEGRAL 1L") == 1


def _corrida(nome: str) -> list[tuple[int, dict[str, object]]]:
    """Laura e Erik adicionam `nome` no mesmo instante, cada um com a sua conexão."""
    largada = threading.Barrier(2)
    respostas: list[tuple[int, dict[str, object]]] = []

    def celular(quem: dict[str, str]) -> None:
        with TestClient(app) as c:
            largada.wait()
            r = adicionar(c, nome, quem=quem)
            respostas.append((r.status_code, r.json()))

    fios = [threading.Thread(target=celular, args=(q,)) for q in (LAURA, ERIK)]
    for f in fios:
        f.start()
    for f in fios:
        f.join(timeout=30)
    return respostas


def test_dois_leites_ao_mesmo_tempo_viram_um_item(session: Session) -> None:
    """Dois celulares, duas conexões, o mesmo instante.

    Cinco rodadas, com produto novo em cada (o produto também nasce na
    corrida). O único parcial do banco decide; o service só escolhe a
    resposta.
    """
    for rodada in range(5):
        nome = f"Leite de corrida {rodada}"
        respostas = _corrida(nome)

        assert sorted(s for s, _ in respostas) == [200, 201], respostas
        assert len({c["id"] for _, c in respostas}) == 1
        assert sorted(bool(c["ja_estava"]) for _, c in respostas) == [False, True]
        assert _pendentes(session, nome.upper()) == 1
        produtos = session.scalar(
            select(func.count())
            .select_from(Produto)
            .where(Produto.nome_normalizado == nome.upper())
        )
        assert produtos == 1


def test_reenvio_com_o_mesmo_id_cliente_nao_duplica(client: TestClient, session: Session) -> None:
    pedido = uuid.uuid4()
    primeiro = adicionar(client, "Café 500g", id_cliente=pedido)
    reenvio = adicionar(client, "Café 500g", id_cliente=pedido)

    assert primeiro.status_code == 201
    assert reenvio.status_code == 200
    assert reenvio.json()["id"] == primeiro.json()["id"]
    assert reenvio.json()["ja_estava"] is False

    # Depois de comprado, o reenvio atrasado continua sendo o mesmo pedido,
    # e não um café novo na lista.
    client.post(f"/lista/itens/{primeiro.json()['id']}/comprar", headers=LAURA)
    atrasado = adicionar(client, "Café 500g", id_cliente=pedido)
    assert atrasado.status_code == 200
    assert atrasado.json()["situacao"] == "comprado"
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(ItemLista)) == 1


# --- comprar, desfazer, tirar -----------------------------------------------


def test_comprar_e_repetir_mantem_o_primeiro_comprador(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L")
    comprado = client.post(f"/lista/itens/{leite['id']}/comprar", headers=ERIK)
    assert comprado.status_code == 200
    assert comprado.json()["situacao"] == "comprado"
    assert comprado.json()["comprado_por"] == "Erik"
    assert comprado.json()["comprado_em"] is not None

    de_novo = client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)
    assert de_novo.status_code == 200
    assert de_novo.json()["comprado_por"] == "Erik"
    assert de_novo.json()["comprado_em"] == comprado.json()["comprado_em"]


def test_comprar_item_tirado_da_lista_devolve_409_com_o_item(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L")
    client.delete(f"/lista/itens/{leite['id']}", headers=ERIK)
    resposta = client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)
    assert resposta.status_code == 409
    assert resposta.json()["item"]["id"] == leite["id"]
    assert resposta.json()["item"]["deleted_em"] is not None


def test_item_inexistente_e_404(client: TestClient) -> None:
    assert client.post("/lista/itens/999/comprar", headers=LAURA).status_code == 404


def test_produto_volta_a_lista_depois_de_comprado(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L")
    client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)
    outro = adicionar(client, "Leite integral 1L", quem=ERIK)
    assert outro.status_code == 201
    assert outro.json()["id"] != leite["id"]


def test_desfazer_volta_a_pendente(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L")
    client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)
    desfeito = client.post(f"/lista/itens/{leite['id']}/desfazer", headers=LAURA)
    assert desfeito.status_code == 200
    assert desfeito.json()["situacao"] == "pendente"
    assert desfeito.json()["comprado_por"] is None
    # Repetir não muda nada.
    assert client.post(f"/lista/itens/{leite['id']}/desfazer", headers=LAURA).status_code == 200


def test_desfazer_com_outro_pendente_do_mesmo_produto_e_409(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L")
    client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)
    item(client, "Leite integral 1L", quem=ERIK)
    resposta = client.post(f"/lista/itens/{leite['id']}/desfazer", headers=LAURA)
    assert resposta.status_code == 409
    assert resposta.json()["item"]["situacao"] == "comprado"


def test_tirar_da_lista_e_soft_delete_e_repetir_nao_falha(
    client: TestClient, session: Session
) -> None:
    leite = item(client, "Leite integral 1L")
    tirado = client.delete(f"/lista/itens/{leite['id']}", headers=LAURA)
    assert tirado.status_code == 200
    assert tirado.json()["deleted_em"] is not None
    assert client.delete(f"/lista/itens/{leite['id']}", headers=ERIK).status_code == 200
    # A linha continua no banco (regra 2).
    session.expire_all()
    assert session.get(ItemLista, leite["id"]) is not None
    assert client.get("/lista").json()["itens"] == []


def test_atualizar_quantidade_e_observacao(client: TestClient) -> None:
    leite = item(client, "Leite integral 1L", quantidade="1")
    resposta = client.patch(
        f"/lista/itens/{leite['id']}",
        json={"quantidade": "6", "observacao": "o de caixinha"},
        headers=ERIK,
    )
    assert resposta.status_code == 200
    assert resposta.json()["quantidade"] == "6.000"
    assert resposta.json()["observacao"] == "o de caixinha"
    limpo = client.patch(f"/lista/itens/{leite['id']}", json={"observacao": None}, headers=ERIK)
    assert limpo.json()["observacao"] is None
    assert limpo.json()["quantidade"] == "6.000"


# --- leitura ----------------------------------------------------------------


def test_lista_na_ordem_do_percurso_com_comprados_recentes(client: TestClient) -> None:
    sabao = item(client, "Sabão em pó")
    banana = item(client, "Banana")
    pao = item(client, "Pão francês")
    leite = item(client, "Leite integral 1L")
    client.post(f"/lista/itens/{leite['id']}/comprar", headers=LAURA)

    corpo = client.get("/lista").json()
    assert corpo["cursor"]
    nomes = [i["produto_nome"] for i in corpo["itens"]]
    # Pendentes primeiro, na ordem das seções; o comprado recente no fim.
    assert nomes == ["Banana", "Pão francês", "Sabão em pó", "Leite integral 1L"]
    assert {i["id"] for i in corpo["itens"]} == {sabao["id"], banana["id"], pao["id"], leite["id"]}

    futuro = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    sem_comprados = client.get("/lista", params={"comprados_desde": futuro}).json()
    assert [i["produto_nome"] for i in sem_comprados["itens"]] == [
        "Banana",
        "Pão francês",
        "Sabão em pó",
    ]


def test_historico_de_comprados(client: TestClient) -> None:
    for nome in ("Banana", "Café 500g"):
        criado = item(client, nome)
        client.post(f"/lista/itens/{criado['id']}/comprar", headers=LAURA)
    item(client, "Tomate")  # pendente: fora do histórico

    pagina = client.get("/lista/historico", params={"limit": 1}).json()
    assert pagina["total"] == 2
    assert len(pagina["items"]) == 1
    cafe = produto_id(client, "café")
    so_cafe = client.get("/lista/historico", params={"produto_id": cafe}).json()
    assert [i["produto_nome"] for i in so_cafe["items"]] == ["Café 500g"]


def test_segundo_pedido_espera_o_primeiro_e_devolve_o_item_dele(client: TestClient) -> None:
    """A corrida sem depender de sorte: o primeiro celular gravou o leite e
    ainda não confirmou; o segundo pedido espera no índice único e, quando o
    primeiro confirma, devolve o item dele em vez de criar outro."""
    leite = produto_id(client, "leite")
    resultado: list[tuple[int, bool, bool]] = []

    def segundo_celular() -> None:
        with SessionLocal() as s:
            definir_autor(s, "Erik")
            achado, criado, ja_estava = ListaService(s, "Erik").criar(
                uuid.uuid4(), produto_id=leite
            )
            s.commit()
            resultado.append((achado.id, criado, ja_estava))

    with engine.connect() as primeiro:
        primeiro.execute(text("SELECT set_config('app.autor', 'Laura', false)"))
        id_primeiro = primeiro.execute(
            text(
                "INSERT INTO compras.itens_lista (produto_id, adicionado_por) "
                "VALUES (:p, 'Laura') RETURNING id"
            ),
            {"p": leite},
        ).scalar_one()

        fio = threading.Thread(target=segundo_celular)
        fio.start()
        fio.join(timeout=1.0)
        assert fio.is_alive(), "o segundo pedido não esperou o primeiro"
        primeiro.commit()

    fio.join(timeout=30)
    assert resultado == [(id_primeiro, False, True)]
