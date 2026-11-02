"""Seções do mercado na ordem de percurso e alguns produtos comuns.

    python -m compras.seed

Idempotente: seção ou produto que já existe (pelo nome, sem diferença de
caixa e acento) não é tocado, nem a ordem que o casal já ajustou. Rodar de
novo só acrescenta o que faltar.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras.db import SessionLocal, definir_autor
from compras.models import Produto, Secao
from compras.normalizar import normalizar

#: O caminho mais comum num mercado: frescos na entrada, limpeza e higiene no
#: fim. "Sem seção" é sempre a última (modelo-dados.md, `secoes`).
SEM_SECAO = "Sem seção"

SECOES: tuple[str, ...] = (
    "Hortifrúti",
    "Padaria",
    "Frios e laticínios",
    "Carnes",
    "Mercearia",
    "Bebidas",
    "Congelados",
    "Limpeza",
    "Higiene",
    SEM_SECAO,
)

#: (nome, seção, unidade padrão)
PRODUTOS: tuple[tuple[str, str, str], ...] = (
    ("Banana", "Hortifrúti", "kg"),
    ("Tomate", "Hortifrúti", "kg"),
    ("Cebola", "Hortifrúti", "kg"),
    ("Batata", "Hortifrúti", "kg"),
    ("Alho", "Hortifrúti", "un"),
    ("Pão francês", "Padaria", "kg"),
    ("Leite integral 1L", "Frios e laticínios", "un"),
    ("Ovos 12 un", "Frios e laticínios", "un"),
    ("Manteiga 200g", "Frios e laticínios", "un"),
    ("Queijo mussarela", "Frios e laticínios", "kg"),
    ("Presunto", "Frios e laticínios", "kg"),
    ("Iogurte natural", "Frios e laticínios", "un"),
    ("Peito de frango", "Carnes", "kg"),
    ("Carne moída", "Carnes", "kg"),
    ("Arroz 5kg", "Mercearia", "un"),
    ("Feijão preto 1kg", "Mercearia", "un"),
    ("Café 500g", "Mercearia", "un"),
    ("Açúcar 1kg", "Mercearia", "un"),
    ("Óleo de soja 900ml", "Mercearia", "un"),
    ("Macarrão 500g", "Mercearia", "un"),
    ("Água mineral 1,5L", "Bebidas", "un"),
    ("Papel higiênico 12 rolos", "Limpeza", "un"),
    ("Detergente 500ml", "Limpeza", "un"),
    ("Sabão em pó", "Limpeza", "un"),
    ("Água sanitária 2L", "Limpeza", "un"),
    ("Creme dental", "Higiene", "un"),
    ("Sabonete", "Higiene", "un"),
    ("Shampoo", "Higiene", "un"),
)


def semear(session: Session) -> tuple[int, int]:
    """Grava o que faltar; devolve (seções criadas, produtos criados)."""
    existentes = {
        s.nome.lower(): s for s in session.scalars(select(Secao).where(Secao.deleted_em.is_(None)))
    }
    proxima = (
        session.scalar(select(func.max(Secao.ordem)).where(Secao.deleted_em.is_(None))) or 0
    ) + 1
    secoes_criadas = 0
    for nome in SECOES:
        if nome.lower() in existentes:
            continue
        secao = Secao(nome=nome, ordem=proxima)
        session.add(secao)
        existentes[nome.lower()] = secao
        proxima += 1
        secoes_criadas += 1
    session.flush()

    # "Sem seção" por último, mesmo quando outra seção nasceu depois dela.
    sem = existentes[SEM_SECAO.lower()]
    maior = session.scalar(
        select(func.max(Secao.ordem)).where(Secao.deleted_em.is_(None), Secao.id != sem.id)
    )
    if maior is not None and sem.ordem <= maior:
        sem.ordem = maior + 1

    nomes = set(
        session.scalars(select(Produto.nome_normalizado).where(Produto.deleted_em.is_(None)))
    )
    produtos_criados = 0
    for nome, nome_secao, unidade in PRODUTOS:
        normalizado = normalizar(nome)
        if normalizado in nomes:
            continue
        session.add(
            Produto(
                nome=nome,
                nome_normalizado=normalizado,
                secao_id=existentes[nome_secao.lower()].id,
                unidade_padrao=unidade,
            )
        )
        nomes.add(normalizado)
        produtos_criados += 1
    session.flush()
    return secoes_criadas, produtos_criados


def run() -> tuple[int, int]:
    with SessionLocal() as session:
        definir_autor(session, "seed")
        criados = semear(session)
        session.commit()
    return criados


if __name__ == "__main__":
    secoes, produtos = run()
    print(f"seed: {secoes} seção(ões) e {produtos} produto(s) novos.")
