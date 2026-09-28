"""Popula o banco com 12 meses de lançamentos plausíveis.

**Só para testar a tela na mão.** Não é seed: `app/seed.py` cria os cadastros
que o sistema precisa para funcionar; isto aqui inventa transações para os
gráficos terem o que desenhar. Nunca rode contra dados de verdade.

    python -m scripts.demo_data              # 12 meses até o mês corrente
    python -m scripts.demo_data --limpar     # apaga o que este script criou antes

Determinístico: mesma semente, mesmos números. Rodar duas vezes sem `--limpar`
esbarra no índice de deduplicação, que é exatamente o comportamento esperado.
"""

from __future__ import annotations

import argparse
import calendar
import random
import sys
from datetime import date
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import TipoTransacao
from app.models import Categoria, Conta, FormaPagamento, Local, Pessoa, Transacao
from app.seed import SUFIXO_TITULAR

#: Semente fixa: a demo é sempre a mesma, então dá para comparar telas entre
#: execuções e conversar sobre "aquele pico de dezembro".
SEMENTE = 42

#: Marca as transações criadas aqui, para `--limpar` saber o que apagar.
MARCA = "[demo]"

MESES_DE_HISTORICO = 12

#: Despesas fixas: (subcategoria, dia, balde, forma, valor, descrição, local).
#: `None` no balde = gasto conjunto (D-03).
FIXAS = [
    (
        "Aluguel",
        1,
        None,
        "Boleto/Débito automático",
        "2200.00",
        "Aluguel do apartamento",
        "Imobiliária Lopes",
    ),
    ("Condomínio", 5, None, "Boleto/Débito automático", "420.00", "Condomínio", "Edifício Aurora"),
    (
        "Plano de saúde",
        10,
        None,
        "Boleto/Débito automático",
        "430.00",
        "Plano de saúde",
        "Amil Saúde",
    ),
    ("Streaming", 3, None, "Cartão de crédito", "39.90", "Netflix", "Netflix"),
    ("Streaming", 4, None, "Cartão de crédito", "21.90", "Spotify", "Spotify"),
    ("Software", 7, None, "Cartão de crédito", "35.00", "Microsoft 365", "Microsoft"),
    ("Academia", 8, 0, "Cartão de débito", "99.00", "Mensalidade da academia", "SmartFit"),
    ("Contas", 12, None, "Boleto/Débito automático", "180.00", "Conta de energia", "Enel"),
    ("Contas", 14, None, "Pix", "95.00", "Internet", "Vivo Fibra"),
]

RECEITAS = [
    ("Salário", 5, 0, "Pix", "5200.00", "Salário", "Empresa Tech Solutions"),
    ("Salário", 5, 1, "Pix", "3800.00", "Salário", "Consultoria Alfa"),
]

#: Despesas variáveis: (subcategoria, peso, faixa de valor, descrições, locais).
VARIAVEIS = [
    (
        "Mercado",
        10,
        (70, 320),
        ["Compras do mês", "Feira", "Mercado"],
        ["Supermercado Extra", "Pão de Açúcar", "Carrefour"],
    ),
    (
        "Restaurante",
        6,
        (35, 140),
        ["Almoço", "Jantar", "Café"],
        ["Sabor Caseiro", "Cantina Italiana", "Sushi Kenzo"],
    ),
    ("Delivery", 4, (25, 85), ["Pedido delivery"], ["iFood", "Rappi"]),
    ("Combustível", 5, (120, 260), ["Abastecimento"], ["Posto Ipiranga", "Posto Shell"]),
    ("App/Corrida", 6, (12, 55), ["Corrida"], ["Uber", "99"]),
    ("Farmácia", 4, (20, 140), ["Farmácia"], ["Drogasil", "Farmácia São Paulo"]),
    ("Cinema/Shows", 3, (30, 120), ["Cinema", "Show"], ["Cinemark", "Teatro Municipal"]),
    ("Vestuário", 2, (60, 300), ["Roupas"], ["Renner", "Zara"]),
    (
        "Cuidados pessoais",
        2,
        (35, 110),
        ["Cabeleireiro", "Barbearia"],
        ["Studio Hair", "Barbearia Vintage"],
    ),
    (
        "Manutenção",
        1,
        (60, 450),
        ["Serviço de manutenção"],
        ["Chaveiro Central", "Assistência Silva"],
    ),
    ("Consultas", 1, (120, 380), ["Consulta médica"], ["Clínica Vitalis"]),
    ("Cursos", 1, (50, 280), ["Curso online"], ["Alura", "Udemy"]),
    ("Livros", 1, (30, 75), ["Livro"], ["Livraria Cultura"]),
    ("Presentes", 1, (50, 280), ["Presente"], ["Amazon", "Loja Encanto"]),
]

#: Orçamentos por categoria raiz, para o painel ter linhas.
ORCAMENTOS = {
    "Alimentação": "1800.00",
    "Transporte": "500.00",
    "Lazer": "400.00",
    "Assinaturas": "150.00",
}


def _primeiro_dia(d: date) -> date:
    return d.replace(day=1)


def _somar_meses(competencia: date, meses: int) -> date:
    total = competencia.month - 1 + meses
    return date(competencia.year + total // 12, total % 12 + 1, 1)


def _indice_por_nome(session: Session) -> dict[str, dict[str, int]]:
    """Mapa nome -> id de cada cadastro, para não repetir SELECT."""
    return {
        "categoria": {
            f"{c.categoria_pai_id or 0}:{c.nome}": c.id
            for c in session.scalars(select(Categoria).where(Categoria.deleted_em.is_(None)))
        },
        "sub": {
            c.nome: c.id
            for c in session.scalars(
                select(Categoria).where(
                    Categoria.deleted_em.is_(None), Categoria.categoria_pai_id.isnot(None)
                )
            )
        },
        "raiz": {
            c.nome: c.id
            for c in session.scalars(
                select(Categoria).where(
                    Categoria.deleted_em.is_(None), Categoria.categoria_pai_id.is_(None)
                )
            )
        },
        # Duas entradas por forma. As tabelas deste gerador citam o apelido
        # base ("Pix"), mas o cadastro guarda um por titular ("Pix - Erik").
        # Sem a tradução, o `.get()` devolveria None e a demo inteira nasceria
        # sem forma de pagamento — em silêncio, porque a coluna aceita nulo.
        #
        #   "<base>"              -> a forma de menor id, para gasto conjunto
        #   "<base>|<pessoa_id>"  -> a forma daquela pessoa
        **_indice_de_formas(session),
    }


def _base_do_apelido(apelido: str) -> str:
    antes, separador, _ = apelido.rpartition(SUFIXO_TITULAR)
    return antes if separador else apelido


def _indice_de_formas(session: Session) -> dict[str, dict[str, int]]:
    por_base: dict[str, int] = {}
    for forma in session.scalars(
        select(FormaPagamento)
        .where(FormaPagamento.deleted_em.is_(None))
        .order_by(FormaPagamento.id)
    ):
        base = _base_do_apelido(forma.apelido)
        # `setdefault`: o primeiro id vence, para a escolha do balde conjunto
        # ser estável entre execuções — a demo promete ser determinística.
        por_base.setdefault(base, forma.id)
        por_base.setdefault(forma.apelido, forma.id)
        if forma.titular_id is not None:
            por_base[f"{base}|{forma.titular_id}"] = forma.id
    return {"forma": por_base}


def _local_id(session: Session, cache: dict[str, int], nome: str) -> int:
    if nome in cache:
        return cache[nome]
    import unicodedata

    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c)
    )
    normalizado = " ".join(sem_acento.upper().split())

    local = session.scalar(select(Local).where(Local.nome_normalizado == normalizado))
    if local is None:
        local = Local(nome=nome, nome_normalizado=normalizado)
        session.add(local)
        session.flush()
    cache[nome] = local.id
    return local.id


def limpar(session: Session) -> int:
    """Soft delete de tudo que este script criou. Nunca DELETE físico."""
    resultado = session.execute(
        text(
            "UPDATE transacoes SET deleted_em = now() "
            "WHERE observacao = :marca AND deleted_em IS NULL"
        ),
        {"marca": MARCA},
    )
    session.execute(text("UPDATE orcamentos SET deleted_em = now() WHERE deleted_em IS NULL"))
    return int(resultado.rowcount or 0)


def gerar(session: Session, hoje: date) -> int:
    rnd = random.Random(SEMENTE)
    idx = _indice_por_nome(session)
    cache_local: dict[str, int] = {}

    pessoas = list(
        session.scalars(select(Pessoa).where(Pessoa.deleted_em.is_(None)).order_by(Pessoa.id))
    )
    if len(pessoas) < 2:
        raise SystemExit("Rode `python -m app.seed` antes — faltam as duas pessoas.")

    conta = session.scalar(select(Conta).where(Conta.deleted_em.is_(None)).order_by(Conta.id))
    baldes = [pessoas[0].id, pessoas[1].id, None]

    competencia_atual = _primeiro_dia(hoje)
    inicio = _somar_meses(competencia_atual, -(MESES_DE_HISTORICO - 1))

    criadas = 0
    mes = inicio
    while mes <= competencia_atual:
        # No mês corrente só existe o que já aconteceu até hoje.
        ultimo_dia = (
            hoje.day if mes == competencia_atual else calendar.monthrange(mes.year, mes.month)[1]
        )

        for sub, dia, balde, forma, valor, desc, local in FIXAS + RECEITAS:
            if dia > ultimo_dia:
                continue
            eh_receita = (sub, dia, balde, forma, valor, desc, local) in RECEITAS
            criadas += _inserir(
                session,
                idx,
                cache_local,
                conta,
                data=date(mes.year, mes.month, dia),
                competencia=mes,
                valor=Decimal(valor),
                tipo=TipoTransacao.RECEITA if eh_receita else TipoTransacao.DESPESA,
                descricao=desc,
                sub=sub,
                pessoa_id=None if balde is None else pessoas[balde].id,
                forma=forma,
                local=local,
            )

        # Dezembro gasta mais; o gráfico fica mais interessante e é verdade.
        quantidade = rnd.randint(8, 11) + (4 if mes.month == 12 else 0)
        if mes == competencia_atual:
            quantidade = max(2, quantidade * ultimo_dia // 30)

        pool = [item for item in VARIAVEIS for _ in range(item[1])]
        for _ in range(quantidade):
            sub, _peso, (mini, maxi), descs, locais = rnd.choice(pool)
            criadas += _inserir(
                session,
                idx,
                cache_local,
                conta,
                data=date(mes.year, mes.month, rnd.randint(1, ultimo_dia)),
                competencia=mes,
                valor=Decimal(str(round(rnd.uniform(mini, maxi), 2))),
                tipo=TipoTransacao.DESPESA,
                descricao=rnd.choice(descs),
                sub=sub,
                pessoa_id=rnd.choice(baldes),
                forma=rnd.choice(["Cartão de crédito", "Cartão de débito", "Pix", "Dinheiro"]),
                local=rnd.choice(locais),
            )

        mes = _somar_meses(mes, 1)

    # Orçamentos do mês corrente, para o painel ter o que mostrar.
    for raiz, meta in ORCAMENTOS.items():
        categoria_id = idx["raiz"].get(raiz)
        if categoria_id is None:
            continue
        session.execute(
            text(
                "INSERT INTO orcamentos (categoria_id, competencia, valor_meta) "
                "VALUES (:c, :m, :v) ON CONFLICT DO NOTHING"
            ),
            {"c": categoria_id, "m": competencia_atual, "v": meta},
        )

    return criadas


def _inserir(
    session: Session,
    idx: dict[str, dict[str, int]],
    cache_local: dict[str, int],
    conta: Conta | None,
    **campos: object,
) -> int:
    sub = campos.pop("sub")
    forma = campos.pop("forma")
    local = campos.pop("local")

    # Cada um paga com o próprio cartão; gasto conjunto cai na forma padrão.
    pessoa_id = campos.get("pessoa_id")
    forma_id = idx["forma"].get(f"{forma}|{pessoa_id}") if pessoa_id else None

    transacao = Transacao(
        **campos,  # type: ignore[arg-type]
        categoria_id=idx["sub"].get(str(sub)),
        forma_pagamento_id=forma_id if forma_id else idx["forma"].get(str(forma)),
        local_id=_local_id(session, cache_local, str(local)),
        conta_id=conta.id if conta else None,
        observacao=MARCA,
    )
    session.add(transacao)
    try:
        session.flush()
    except IntegrityError:
        # Colisão de deduplicação: mesma data, valor e forma. Esperado num
        # gerador aleatório — pula e segue.
        session.rollback()
        return 0
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limpar", action="store_true", help="Apaga os dados de demo e sai")
    parser.add_argument("--hoje", help="Data de referência (AAAA-MM-DD). Padrão: hoje.")
    args = parser.parse_args()

    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()

    with SessionLocal() as session:
        session.execute(text("SELECT set_config('app.autor', 'demo_data', false)"))

        if args.limpar:
            removidas = limpar(session)
            session.commit()
            print(f"{removidas} transações de demo removidas (soft delete).")
            return

        criadas = gerar(session, hoje)
        session.commit()
        print(f"{criadas} transações de demonstração criadas, até {hoje.isoformat()}.")
        print("Para desfazer: python -m scripts.demo_data --limpar")


if __name__ == "__main__":
    sys.exit(main())
