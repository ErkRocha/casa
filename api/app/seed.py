"""Dados iniciais. Idempotente — rodar de novo não duplica nada.

`make seed`. Nomes de pessoa e conta são chute razoável para começar: renomeie
pelo painel, os ids não mudam.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import TipoConta, TipoPagamento, TipoPessoa, TipoTransacao
from app.models import Categoria, Conta, FormaPagamento, Pessoa

log = logging.getLogger(__name__)

#: (nome, tipo, cor, [subcategorias]).
#:
#: A ordem das raízes de despesa é a mesma de `CATEGORY_RAMP_ORDER` no front —
#: é ela que fixa o passo da rampa de cor de cada categoria. Categoria nova
#: entra no fim; inserir no meio repinta todas as seguintes.
ARVORE_CATEGORIAS: list[tuple[str, TipoTransacao, str | None, list[str]]] = [
    ("Alimentação", TipoTransacao.DESPESA, "cat-1", ["Mercado", "Restaurante", "Delivery"]),
    ("Casa", TipoTransacao.DESPESA, "cat-2", ["Aluguel", "Contas", "Condomínio", "Manutenção"]),
    (
        "Transporte",
        TipoTransacao.DESPESA,
        "cat-3",
        ["Combustível", "App/Corrida", "Transporte público"],
    ),
    ("Assinaturas", TipoTransacao.DESPESA, "cat-4", ["Streaming", "Software", "Academia"]),
    ("Saúde", TipoTransacao.DESPESA, "cat-5", ["Plano de saúde", "Farmácia", "Consultas"]),
    ("Lazer", TipoTransacao.DESPESA, "cat-6", ["Viagem", "Cinema/Shows", "Hobbies"]),
    ("Educação", TipoTransacao.DESPESA, "cat-7", ["Cursos", "Livros"]),
    ("Pessoal", TipoTransacao.DESPESA, "cat-8", ["Vestuário", "Cuidados pessoais"]),
    ("Presentes", TipoTransacao.DESPESA, "cat-9", []),
    ("Receita", TipoTransacao.RECEITA, None, ["Salário", "Freelance", "Outros"]),
]

#: A ordem importa: a primeira vira o balde A dos gráficos, a segunda o B.
#: Trocar a ordem depois de haver dados troca as cores da tela inteira.
PESSOAS: list[tuple[str, TipoPessoa]] = [
    ("Laura", TipoPessoa.INDIVIDUAL),
    ("Erik", TipoPessoa.INDIVIDUAL),
]

#: `titular_id` nulo = conjunta.
CONTAS: list[tuple[str, TipoConta]] = [
    ("Conta Corrente", TipoConta.CORRENTE),
    ("Carteira", TipoConta.CARTEIRA),
    ("Poupança", TipoConta.POUPANCA),
]

FORMAS_PAGAMENTO: list[tuple[str, TipoPagamento]] = [
    ("Cartão de crédito", TipoPagamento.CREDITO),
    ("Cartão de débito", TipoPagamento.DEBITO),
    ("Pix", TipoPagamento.PIX),
    ("Dinheiro", TipoPagamento.DINHEIRO),
    ("Boleto/Débito automático", TipoPagamento.BOLETO),
]

#: Cada forma nasce uma vez por pessoa, com o nome dela no fim do apelido:
#: "Cartão de crédito - Erik". É o que permite saber de quem foi o cartão na
#: hora de conferir uma fatura importada.
#:
#: O sufixo é redundante com `titular_id`, que a coluna já guardava — e a
#: redundância é o ponto. Quem escolhe a forma no painel vê uma lista de
#: apelidos, não de titulares; sem o nome no texto, "Cartão de crédito"
#: apareceria duas vezes idêntico. Quando a tela souber mostrar o titular ao
#: lado do apelido, o sufixo sai e o `titular_id` fica.
SUFIXO_TITULAR = " - "


def _seed_pessoas(session: Session) -> None:
    for nome, tipo in PESSOAS:
        existe = session.scalar(select(Pessoa).where(Pessoa.nome == nome))
        if existe is None:
            session.add(Pessoa(nome=nome, tipo=tipo))
            log.info("pessoa criada: %s", nome)


def _seed_contas(session: Session) -> None:
    for nome, tipo in CONTAS:
        existe = session.scalar(select(Conta).where(Conta.nome == nome))
        if existe is None:
            session.add(Conta(nome=nome, tipo=tipo, titular_id=None))
            log.info("conta criada: %s", nome)


def _seed_categorias(session: Session) -> None:
    for nome, tipo, cor, subs in ARVORE_CATEGORIAS:
        raiz = session.scalar(
            select(Categoria).where(Categoria.nome == nome, Categoria.categoria_pai_id.is_(None))
        )
        if raiz is None:
            raiz = Categoria(nome=nome, tipo=tipo, cor=cor, categoria_pai_id=None)
            session.add(raiz)
            session.flush()  # precisa do id para pendurar as subcategorias
            log.info("categoria criada: %s", nome)

        for sub_nome in subs:
            existe = session.scalar(
                select(Categoria).where(
                    Categoria.nome == sub_nome,
                    Categoria.categoria_pai_id == raiz.id,
                )
            )
            if existe is None:
                session.add(Categoria(nome=sub_nome, tipo=tipo, cor=cor, categoria_pai_id=raiz.id))
                log.info("subcategoria criada: %s › %s", nome, sub_nome)


def _seed_formas_pagamento(session: Session) -> None:
    conta_corrente = session.scalar(select(Conta).where(Conta.nome == "Conta Corrente"))
    carteira = session.scalar(select(Conta).where(Conta.nome == "Carteira"))

    titulares = list(
        session.scalars(
            select(Pessoa)
            .where(Pessoa.tipo == TipoPessoa.INDIVIDUAL, Pessoa.deleted_em.is_(None))
            .order_by(Pessoa.id)
        )
    )

    for apelido_base, tipo in FORMAS_PAGAMENTO:
        for titular in titulares:
            apelido = f"{apelido_base}{SUFIXO_TITULAR}{titular.nome}"
            existe = session.scalar(select(FormaPagamento).where(FormaPagamento.apelido == apelido))
            if existe is not None:
                continue
            conta = carteira if tipo is TipoPagamento.DINHEIRO else conta_corrente
            session.add(
                FormaPagamento(
                    apelido=apelido,
                    tipo=tipo,
                    conta_id=conta.id if conta else None,
                    titular_id=titular.id,
                )
            )
            log.info("forma de pagamento criada: %s", apelido)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with SessionLocal() as session:
        # O trigger de auditoria vai gravar isso como autor das linhas.
        session.execute(text("SELECT set_config('app.autor', 'seed', false)"))

        _seed_pessoas(session)
        _seed_contas(session)
        _seed_categorias(session)
        session.flush()
        _seed_formas_pagamento(session)

        session.commit()

    log.info("seed concluído")


if __name__ == "__main__":
    run()
