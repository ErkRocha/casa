"""Põe nome nas pessoas e titular em cada forma de pagamento.

    python -m scripts.reorganizar_titulares --de "Pessoa A=Laura" --de "Pessoa B=Erik"
    python -m scripts.reorganizar_titulares --simular      # mostra o plano e sai

O que faz, em duas partes:

1. **Renomeia pessoas.** `Pessoa A`/`Pessoa B` viram os nomes de verdade. Os
   ids não mudam, então nenhuma transação é tocada.

2. **Duplica as formas de pagamento por titular.** Cada forma sem titular vira
   duas: uma por pessoa individual, com o nome dela no fim do apelido.

O ponto delicado é a parte 2: as transações já importadas apontam para a forma
original. Criar duas novas e abandonar a antiga deixaria o histórico preso a
uma terceira opção sem dono, que continuaria aparecendo na lista para sempre.

Então a original é **renomeada** para o titular que a usou até agora
(`--titular-atual`), preservando os vínculos existentes, e só a segunda é
criada do zero. É por isso que o script precisa saber de quem eram os cartões.

Idempotente: forma que já tem sufixo de titular é pulada.
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.enums import TipoPessoa
from app.models import FormaPagamento, Pessoa, Transacao
from app.seed import SUFIXO_TITULAR


def _pessoas_individuais(sessao: Session) -> list[Pessoa]:
    return list(
        sessao.scalars(
            select(Pessoa)
            .where(Pessoa.tipo == TipoPessoa.INDIVIDUAL, Pessoa.deleted_em.is_(None))
            .order_by(Pessoa.id)
        )
    )


def renomear_pessoas(sessao: Session, mapa: dict[str, str]) -> list[str]:
    mudancas = []
    for antigo, novo in mapa.items():
        pessoa = sessao.scalar(
            select(Pessoa).where(Pessoa.nome == antigo, Pessoa.deleted_em.is_(None))
        )
        if pessoa is None:
            continue
        pessoa.nome = novo
        mudancas.append(f"pessoa #{pessoa.id}: {antigo} → {novo}")
    return mudancas


def _ja_tem_titular_no_nome(apelido: str, nomes: list[str]) -> bool:
    return any(apelido.endswith(f"{SUFIXO_TITULAR}{nome}") for nome in nomes)


def duplicar_formas(sessao: Session, titular_atual: str) -> list[str]:
    pessoas = _pessoas_individuais(sessao)
    if len(pessoas) != 2:
        raise SystemExit(
            f"esperava 2 pessoas individuais, encontrei {len(pessoas)}. "
            "O modelo é de casal (D-03) — conferir o cadastro antes de seguir."
        )

    nomes = [p.nome for p in pessoas]
    dono = next((p for p in pessoas if p.nome == titular_atual), None)
    if dono is None:
        raise SystemExit(f"`{titular_atual}` não está entre as pessoas cadastradas: {nomes}")
    outro = next(p for p in pessoas if p.id != dono.id)

    mudancas = []
    formas = list(
        sessao.scalars(
            select(FormaPagamento)
            .where(FormaPagamento.deleted_em.is_(None))
            .order_by(FormaPagamento.id)
        )
    )

    for forma in formas:
        if _ja_tem_titular_no_nome(forma.apelido, nomes):
            continue

        base = forma.apelido
        usos = (
            sessao.scalar(
                select(func.count(Transacao.id)).where(
                    Transacao.forma_pagamento_id == forma.id,
                    Transacao.deleted_em.is_(None),
                )
            )
            or 0
        )

        # A original fica com quem já usava — é o que mantém as transações
        # existentes apontando para o dono certo em vez de para um apelido órfão.
        forma.apelido = f"{base}{SUFIXO_TITULAR}{dono.nome}"
        forma.titular_id = dono.id
        mudancas.append(f"forma #{forma.id}: {base} → {forma.apelido} ({usos} transação(ões))")

        gemea = f"{base}{SUFIXO_TITULAR}{outro.nome}"
        if sessao.scalar(select(FormaPagamento).where(FormaPagamento.apelido == gemea)) is None:
            sessao.add(
                FormaPagamento(
                    apelido=gemea,
                    tipo=forma.tipo,
                    conta_id=forma.conta_id,
                    dia_fechamento=forma.dia_fechamento,
                    dia_vencimento=forma.dia_vencimento,
                    titular_id=outro.id,
                )
            )
            mudancas.append(f"forma criada: {gemea}")

    return mudancas


def _parse_mapa(pares: list[str]) -> dict[str, str]:
    mapa = {}
    for par in pares:
        antigo, _, novo = par.partition("=")
        if not antigo or not novo:
            raise SystemExit(f"--de espera 'Antigo=Novo', recebi {par!r}")
        mapa[antigo] = novo
    return mapa


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--de",
        action="append",
        default=[],
        metavar="ANTIGO=NOVO",
        help="Renomeia uma pessoa. Pode repetir.",
    )
    parser.add_argument(
        "--titular-atual",
        default="Erik",
        help=(
            "De quem são as formas de pagamento que já existem. "
            "As transações importadas continuam nelas. Padrão: Erik."
        ),
    )
    parser.add_argument(
        "--simular", action="store_true", help="Mostra o que faria e não grava nada."
    )
    args = parser.parse_args()

    with SessionLocal() as sessao:
        sessao.execute(text("SELECT set_config('app.autor', 'reorganizar_titulares', false)"))

        mudancas = renomear_pessoas(sessao, _parse_mapa(args.de))
        sessao.flush()  # o passo seguinte procura as pessoas pelo nome novo
        mudancas += duplicar_formas(sessao, args.titular_atual)

        if not mudancas:
            print("nada a fazer — pessoas e formas já estão organizadas.")
            return 0

        for linha in mudancas:
            print(("[simulação] " if args.simular else "") + linha)

        if args.simular:
            sessao.rollback()
            print("\nnada gravado. Rode sem --simular para aplicar.")
        else:
            sessao.commit()
            print(f"\n{len(mudancas)} alteração(ões) gravada(s).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
