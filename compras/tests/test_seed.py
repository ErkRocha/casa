"""Seed: seções na ordem do percurso, produtos comuns, idempotente."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.models import SEM_SECAO, Produto, Secao
from compras.seed import PRODUTOS, SECOES, run


def test_seed_cria_secoes_na_ordem_e_produtos(session: Session) -> None:
    assert run() == (len(SECOES), len(PRODUTOS))

    nomes = list(session.scalars(select(Secao.nome).order_by(Secao.ordem)))
    assert nomes == list(SECOES)
    assert nomes[0] == "Hortifrúti"
    assert nomes[-1] == SEM_SECAO

    leite = session.scalar(select(Produto).where(Produto.nome_normalizado == "LEITE INTEGRAL 1L"))
    assert leite is not None
    assert leite.secao.nome == "Frios e laticínios"


def test_seed_de_novo_nao_duplica_nem_reordena(session: Session) -> None:
    run()
    padaria = session.scalar(select(Secao).where(Secao.nome == "Padaria"))
    assert padaria is not None
    padaria.ordem = 50  # o casal mudou a ordem
    session.commit()

    assert run() == (0, 0)
    session.expire_all()
    assert session.scalar(select(func.count()).select_from(Produto)) == len(PRODUTOS)
    assert session.scalar(select(Secao.ordem).where(Secao.nome == "Padaria")) == 50
    # "Sem seção" continua a última, mesmo depois da mudança.
    ultima = session.scalar(select(Secao.nome).order_by(Secao.ordem.desc()).limit(1))
    assert ultima == SEM_SECAO
