"""O roteiro de preparo (modelo-cardapio.md, "Preparo")."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.apoio import LAURA, pessoa, receita, refeicao, semana

SEG = "2026-11-16"
DOM = "2026-11-15"  # a sessão com que a semana nasce


@pytest.fixture(autouse=True)
def _duas_pessoas(client: TestClient) -> None:
    """Duas porções por refeição, para as contas ficarem redondas."""
    pessoa(client, "Laura", "1")
    pessoa(client, "Erik", "1")


def _frango(client: TestClient, **campos: Any) -> dict[str, Any]:
    padrao: dict[str, Any] = {
        "tempo_preparo_min": 90,
        "pode_antecipar": True,
        "dura_dias": 3,
        "pode_congelar": True,
        "rendimento": "4",
    }
    return receita(client, "Frango assado", [], **{**padrao, **campos})


def _ids(sessao: dict[str, Any]) -> list[int]:
    return [d["refeicao_id"] for p in sessao["passos"] for d in p["destinos"]]


def _roteiro(client: TestClient, semana_id: int) -> dict[str, Any]:
    r = client.get(f"/semanas/{semana_id}/preparo")
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_geladeira_ate_dura_dias_e_congelador_depois(client: TestClient) -> None:
    frango = _frango(client)
    s = semana(client, SEG)
    segunda = refeicao(client, s["id"], "2026-11-16", "almoco", frango["id"])
    sexta = refeicao(client, s["id"], "2026-11-20", "janta", frango["id"])

    roteiro = _roteiro(client, s["id"])
    assert [x["data"] for x in roteiro["sessoes"]] == [DOM]
    passos = roteiro["sessoes"][0]["passos"]
    assert len(passos) == 1  # a mesma receita, um passo só
    passo = passos[0]
    assert passo["receita"] == {
        "id": frango["id"],
        "nome": "Frango assado",
        "tempo_preparo_min": 90,
    }
    assert passo["porcoes"] == "4.00" and passo["fator"] == "1.000"
    assert passo["porcoes_geladeira"] == "2.00" and passo["porcoes_congelador"] == "2.00"
    assert passo["destinos"] == [
        {
            "refeicao_id": segunda["id"],
            "dia": "2026-11-16",
            "tipo": "almoco",
            "porcoes": "2.00",
            "onde": "geladeira",
            "descongelar_em": None,
        },
        {
            "refeicao_id": sexta["id"],
            "dia": "2026-11-20",
            "tipo": "janta",
            "porcoes": "2.00",
            "onde": "congelador",
            "descongelar_em": "2026-11-19",  # o dia anterior à refeição
        },
    ]
    assert passo["avisos"] == [] and roteiro["avisos"] == [] and roteiro["no_dia"] == []


def test_o_limite_da_validade_e_inclusivo(client: TestClient) -> None:
    frango = _frango(client, dura_dias=3, pode_congelar=False)
    s = semana(client, SEG)
    # sessão no domingo 15: dia 18 = 3 dias depois (cabe); dia 19 = 4 (não cabe)
    refeicao(client, s["id"], "2026-11-18", "almoco", frango["id"])
    roteiro = _roteiro(client, s["id"])
    assert roteiro["avisos"] == []
    refeicao(client, s["id"], "2026-11-19", "almoco", frango["id"])
    roteiro = _roteiro(client, s["id"])
    assert len(roteiro["avisos"]) == 1


def test_alem_da_validade_sem_congelar_vira_aviso(client: TestClient) -> None:
    salada = receita(
        client, "Salada de folhas", [], pode_antecipar=True, dura_dias=2, pode_congelar=False
    )
    s = semana(client, SEG)
    sabado = refeicao(client, s["id"], "2026-11-21", "almoco", salada["id"])

    roteiro = _roteiro(client, s["id"])
    assert len(roteiro["avisos"]) == 1
    aviso = roteiro["avisos"][0]
    assert aviso["refeicao_id"] == sabado["id"]
    assert aviso["texto"].startswith(
        "Salada de folhas não dura até sábado (dura 2 dias) e não congela"
    )
    # a refeição continua no passo: o casal decide
    passo = roteiro["sessoes"][0]["passos"][0]
    assert [d["refeicao_id"] for d in passo["destinos"]] == [sabado["id"]]
    assert passo["destinos"][0]["onde"] == "geladeira"
    assert passo["avisos"] == [aviso["texto"]]


def test_nao_antecipavel_vai_para_no_dia(client: TestClient) -> None:
    omelete = receita(client, "Omelete", [], tipo="janta", tempo_preparo_min=10)
    s = semana(client, SEG)
    ref = refeicao(client, s["id"], "2026-11-17", "janta", omelete["id"])
    refeicao(client, s["id"], "2026-11-18", "almoco", observacao="sobras")  # sem receita: fora

    roteiro = _roteiro(client, s["id"])
    assert roteiro["sessoes"][0]["passos"] == []
    assert roteiro["no_dia"] == [
        {
            "refeicao_id": ref["id"],
            "dia": "2026-11-17",
            "tipo": "janta",
            "receita": {"id": omelete["id"], "nome": "Omelete", "tempo_preparo_min": 10},
        }
    ]


def test_antecipavel_sem_sessao_ate_o_dia_vai_para_no_dia(client: TestClient) -> None:
    frango = _frango(client)
    s = semana(client, SEG)
    client.delete(f"/sessoes/{s['sessoes'][0]['id']}", headers=LAURA)
    ref = refeicao(client, s["id"], "2026-11-17", "almoco", frango["id"])
    roteiro = _roteiro(client, s["id"])
    assert roteiro["sessoes"] == []
    assert [x["refeicao_id"] for x in roteiro["no_dia"]] == [ref["id"]]


def test_refeicao_vai_para_a_sessao_mais_recente_ate_o_dia(client: TestClient) -> None:
    frango = _frango(client)
    s = semana(client, SEG)
    quarta = client.post(
        f"/semanas/{s['id']}/sessoes",
        json={"data": "2026-11-18", "rotulo": "quarta"},
        headers=LAURA,
    ).json()
    ate_terca = refeicao(client, s["id"], "2026-11-17", "almoco", frango["id"])
    na_quarta = refeicao(
        client, s["id"], "2026-11-18", "janta", frango["id"]
    )  # a sessão do dia vale
    sexta = refeicao(client, s["id"], "2026-11-20", "almoco", frango["id"])

    roteiro = _roteiro(client, s["id"])
    por_data = {x["data"]: x for x in roteiro["sessoes"]}
    assert set(por_data) == {DOM, "2026-11-18"}
    assert _ids(por_data[DOM]) == [ate_terca["id"]]
    assert _ids(por_data["2026-11-18"]) == [na_quarta["id"], sexta["id"]]
    assert por_data["2026-11-18"]["rotulo"] == "quarta"

    # sexta, 2 dias depois da sessão de quarta: geladeira (no domingo seria 5 dias)
    destino_sexta = por_data["2026-11-18"]["passos"][0]["destinos"][1]
    assert destino_sexta["onde"] == "geladeira"

    # apagar a sessão de quarta: as refeições dela voltam para a do domingo
    client.delete(f"/sessoes/{quarta['id']}", headers=LAURA)
    depois = _roteiro(client, s["id"])
    assert [x["data"] for x in depois["sessoes"]] == [DOM]
    destinos = depois["sessoes"][0]["passos"][0]["destinos"]
    assert [d["refeicao_id"] for d in destinos] == [ate_terca["id"], na_quarta["id"], sexta["id"]]
    assert [d["onde"] for d in destinos] == ["geladeira", "geladeira", "congelador"]


def test_sessao_no_sabado_anterior_vale_para_a_semana_toda(client: TestClient) -> None:
    frango = _frango(client)
    s = semana(client, SEG)
    client.post(f"/semanas/{s['id']}/sessoes", json={"data": "2026-11-14"}, headers=LAURA)
    refeicao(client, s["id"], "2026-11-16", "almoco", frango["id"])
    # a mais recente até o dia: o domingo (15), não o sábado (14)
    assert [x["data"] for x in _roteiro(client, s["id"])["sessoes"] if x["passos"]] == [DOM]


def test_passos_ordenados_pelo_tempo_de_preparo(client: TestClient) -> None:
    def antecipavel(nome: str, tempo: int | None) -> dict[str, Any]:
        return receita(client, nome, [], pode_antecipar=True, dura_dias=5, tempo_preparo_min=tempo)

    rapida = antecipavel("Arroz", 25)
    demorada = antecipavel("Feijão", 60)
    empate_b = antecipavel("Batata-doce", 25)
    sem_tempo = antecipavel("Salada", None)
    s = semana(client, SEG)
    for r in (rapida, demorada, empate_b, sem_tempo):
        refeicao(client, s["id"], "2026-11-17", "almoco", r["id"])

    nomes = [p["receita"]["nome"] for p in _roteiro(client, s["id"])["sessoes"][0]["passos"]]
    assert nomes == ["Feijão", "Arroz", "Batata-doce", "Salada"]


def test_fator_nao_arredonda_para_receita_inteira(client: TestClient) -> None:
    frango = _frango(client, rendimento="4")
    s = semana(client, SEG)
    for dia in ("2026-11-16", "2026-11-17", "2026-11-18"):
        refeicao(client, s["id"], dia, "almoco", frango["id"])
    passo = _roteiro(client, s["id"])["sessoes"][0]["passos"][0]
    assert passo["porcoes"] == "6.00"
    assert passo["fator"] == "1.500"  # 1,5 receita
    assert passo["porcoes_geladeira"] == "6.00" and passo["porcoes_congelador"] == "0.00"


def test_roteiro_de_semana_inexistente_e_404(client: TestClient) -> None:
    assert client.get("/semanas/9999/preparo").status_code == 404
