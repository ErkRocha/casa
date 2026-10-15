"""Script da proposta de categorias da Pluggy (D-21)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.enums import StatusImportacao
from app.models import Auditoria, Categoria, CategoriaPluggy, Importacao
from app.services.categorias_pluggy import categorias_por_caminho
from scripts import pluggy_categorias


def _transacao(id_: str, categoria_id: str, categoria: str, status: str = "POSTED") -> dict:
    return {
        "id": id_,
        "accountId": "acc-1",
        "date": "2026-09-01T15:00:00Z",
        "amount": -10,
        "status": status,
        "category": categoria,
        "categoryId": categoria_id,
    }


@pytest.fixture
def importacao(session: Session, semeado: None) -> Importacao:
    corpo = {
        "respostas": [
            {
                "metodo": "GET",
                "caminho": "/v2/transactions",
                "params": {"accountId": "acc-1"},
                "status": 200,
                "corpo": {
                    "results": [
                        _transacao("t1", "11000000", "Groceries"),
                        _transacao("t2", "11000000", "Groceries"),
                        _transacao("t3", "09010000", "Online shopping"),
                        _transacao("t4", "05070000", "Transfer - PIX"),
                        _transacao("t5", "17010000", "Account fees"),
                        _transacao("t7", "08080000", "Office supplies"),
                        _transacao("t8", "08030000", "Pet supplies and vet"),
                        _transacao("t9", "07000000", "Services"),
                        _transacao("t6", "12010000", "Eating out", status="PENDING"),
                    ],
                    "next": None,
                },
            }
        ]
    }
    imp = Importacao(
        arquivo_nome="pluggy.json",
        hash_arquivo="h-categorias",
        arquivo_conteudo=json.dumps(corpo).encode(),
        arquivo_tipo="application/json",
        origem="pluggy",
        status=StatusImportacao.AGUARDANDO_REVISAO,
    )
    session.add(imp)
    session.commit()
    return imp


def test_conta_so_posted_e_sem_repetir(session: Session, importacao: Importacao) -> None:
    contagem = pluggy_categorias.contar_categorias(session)
    assert contagem[("11000000", "Groceries")] == 2
    assert ("12010000", "Eating out") not in contagem


def test_sem_aplicar_nao_grava(
    session: Session, importacao: Importacao, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pluggy_categorias.main([]) == 0
    saida = capsys.readouterr().out
    assert "proposta: Alimentação › Mercado" in saida
    assert "proposta: Compras › Online" in saida
    # Decisão de 15/10/2026: Services fica sem mapeamento de propósito.
    assert "AMBÍGUA" in saida and "Services" in saida
    assert "transferência" in saida
    # "Juros e encargos" não está no seed: proposta sem alvo.
    assert "PROPOSTA SEM ALVO" in saida
    assert session.scalar(select(func.count()).select_from(CategoriaPluggy)) == 0


def test_aplicar_grava_so_as_propostas_com_alvo_e_nao_repete(
    session: Session, importacao: Importacao
) -> None:
    assert pluggy_categorias.main(["--aplicar"]) == 0
    mapeadas = {
        m.pluggy_categoria_nome: m.categoria_id for m in session.scalars(select(CategoriaPluggy))
    }
    # Account fees -> "Juros e encargos", que não está no seed: sem alvo.
    assert set(mapeadas) == {
        "Groceries",
        "Online shopping",
        "Office supplies",
        "Pet supplies and vet",
    }
    caminhos = {c.id: c for c in categorias_por_caminho(session).values()}
    assert caminhos[mapeadas["Groceries"]].nome == "Mercado"
    assert caminhos[mapeadas["Online shopping"]].nome == "Online"
    assert caminhos[mapeadas["Office supplies"]].nome == "Compras"
    assert caminhos[mapeadas["Pet supplies and vet"]].nome == "Pets"
    autores = set(
        session.scalars(select(Auditoria.autor).where(Auditoria.tabela == "categorias_pluggy"))
    )
    assert autores == {"mapeamento_categorias_pluggy"}

    assert pluggy_categorias.main(["--aplicar"]) == 0
    assert session.scalar(select(func.count()).select_from(CategoriaPluggy)) == 4


def _apagar(session: Session, *nomes: str) -> None:
    for categoria in session.scalars(select(Categoria).where(Categoria.nome.in_(nomes))):
        categoria.deleted_em = func.now()
    session.commit()


def test_aplicar_cria_as_categorias_que_faltam_uma_vez(
    session: Session, importacao: Importacao, capsys: pytest.CaptureFixture[str]
) -> None:
    """Banco de antes de 15/10/2026: sem Compras nem Pets."""
    _apagar(session, "Online", "Eletrônicos")
    _apagar(session, "Compras", "Pets")

    assert pluggy_categorias.main([]) == 0
    saida = capsys.readouterr().out
    assert "categoria a criar: Compras, Compras › Online" in saida
    assert "3 categoria(s) seriam criadas: Compras, Compras › Online, Pets" in saida
    vivas = select(func.count()).select_from(Categoria).where(Categoria.deleted_em.is_(None))
    antes = session.scalar(vivas)

    assert pluggy_categorias.main(["--aplicar"]) == 0
    session.expire_all()
    assert session.scalar(vivas) == antes + 3
    caminhos = categorias_por_caminho(session)
    compras = caminhos["COMPRAS"]
    online = caminhos["COMPRAS › ONLINE"]
    assert online.categoria_pai_id == compras.id
    assert "PETS" in caminhos
    autores = set(
        session.scalars(
            select(Auditoria.autor).where(
                Auditoria.tabela == "categorias", Auditoria.registro_id == compras.id
            )
        )
    )
    assert autores == {"mapeamento_categorias_pluggy"}

    assert pluggy_categorias.main(["--aplicar"]) == 0
    session.expire_all()
    assert session.scalar(vivas) == antes + 3


def test_nao_cria_por_cima_de_categoria_inativa(
    session: Session, importacao: Importacao, capsys: pytest.CaptureFixture[str]
) -> None:
    pets = session.scalar(select(Categoria).where(Categoria.nome == "Pets"))
    assert pets is not None
    pets.ativo = False
    session.commit()

    assert pluggy_categorias.main(["--aplicar"]) == 0
    assert "PROPOSTA SEM ALVO: nenhum de Pets existe" in capsys.readouterr().out
    assert (
        session.scalar(
            select(func.count())
            .select_from(Categoria)
            .where(Categoria.nome == "Pets", Categoria.deleted_em.is_(None))
        )
        == 1
    )
    nomes = set(session.scalars(select(CategoriaPluggy.pluggy_categoria_nome)))
    assert "Pet supplies and vet" not in nomes
