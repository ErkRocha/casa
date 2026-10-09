"""Reprocessa os itens pendentes de uma importação da Pluggy (D-21).

    make pluggy-reprocessar [i=4] [proposta=1]       # simulação (padrão)
    cd api && python -m scripts.pluggy_reprocessar [--importacao 4] [--com-proposta]
    cd api && python -m scripts.pluggy_reprocessar --importacao 4 --executar

Passa cada item **pendente** pelo caminho de hoje — forma pela operação,
categoria (regra > mapeamento da Pluggy > local) e o critério de promoção
da sync — e diz quantos seriam promovidos, quantos ficariam na revisão e
por quê, quantos ficariam sem categoria e como as formas se distribuem.

Simula por padrão (`--simular` só deixa isso explícito). `--com-proposta`
considera em memória a proposta de categorias da Pluggy ainda não gravada
(`make pluggy-categorias`), sem gravar nada — e não pode ser usada com
`--executar`. `--executar` grava, com autor `reprocessamento_pluggy`, e
promove os limpos pelo `aprovar()` da revisão.

No terminal só saem contagens, nomes de forma e de motivo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.promocao_pluggy import MOTIVOS
from app.services.reprocessamento_pluggy import (
    PlanoReprocessamento,
    ReprocessamentoPluggyService,
)
from scripts.pluggy_diagnostico_importacao import primeira_importacao_pluggy


def imprimir(plano: PlanoReprocessamento, *, executado: bool) -> None:
    modo = "EXECUÇÃO" if executado else "SIMULAÇÃO (nada foi gravado)"
    extra = " com a proposta de categorias em memória" if plano.com_proposta else ""
    print(f"== Reprocessamento da importação #{plano.importacao_id}: {modo}{extra} ==")
    print(
        "itens vivos por status: "
        + ", ".join(f"{k} {v}" for k, v in sorted(plano.por_status.items()))
    )
    mantidos = sum(plano.mantidos.values())
    print(f"pendentes reavaliados: {len(plano.itens)} | pendentes mantidos como estão: {mantidos}")
    for motivo, n in plano.mantidos.most_common():
        print(f"   {motivo}: {n}")

    verbo = "promovidos" if executado else "seriam promovidos"
    print(f"\n{verbo}: {plano.promoveria}")
    na_revisao = plano.na_revisao
    print(f"ficariam na revisão: {sum(na_revisao.values())}")
    for motivo, texto in MOTIVOS.items():
        if na_revisao[motivo]:
            print(f"   {texto}: {na_revisao[motivo]}")

    print(f"\nsem categoria (entre os reavaliados): {plano.sem_categoria}")
    print(
        "origem da categoria: "
        + ", ".join(f"{k} {v}" for k, v in plano.por_origem_categoria.most_common())
    )
    if plano.proposta_usada:
        print(f"categorias da proposta usadas em memória: {len(plano.proposta_usada)}")

    print("\nformas de pagamento (reavaliados):")
    for rotulo, n in plano.por_forma.most_common():
        print(f"   {n:>5}  {rotulo}")
    novas = plano.formas_novas
    if novas:
        verbo_forma = "criadas" if executado else "seriam criadas"
        print(f"formas {verbo_forma}: " + ", ".join(f.apelido for f in novas))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--importacao", type=int, help="padrão: a primeira da Pluggy")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--simular", action="store_true", help="só lê (o padrão)")
    modo.add_argument("--executar", action="store_true", help="grava e promove os limpos")
    parser.add_argument(
        "--com-proposta",
        action="store_true",
        help="simula com a proposta de categorias em memória (não grava)",
    )
    args = parser.parse_args(argv)
    if args.executar and args.com_proposta:
        parser.error("--com-proposta só vale na simulação: grave o mapeamento antes de executar.")

    from app.db import SessionLocal

    with SessionLocal() as session:
        importacao_id = args.importacao or primeira_importacao_pluggy(session)
        if importacao_id is None:
            print("Nenhuma importação da Pluggy no banco.", file=sys.stderr)
            return 2
        service = ReprocessamentoPluggyService(session)
        plano = service.planejar(importacao_id, com_proposta=args.com_proposta)
        if not args.executar:
            session.rollback()
            imprimir(plano, executado=False)
            return 0
        try:
            resultado = service.executar(plano)
        except Exception as exc:
            session.rollback()
            print(f"Falhou e foi desfeito: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        session.commit()
        imprimir(plano, executado=True)
        print(
            f"\nitens atualizados: {resultado['atualizados']}; promovidos: "
            f"{resultado['promovidos']}; duplicados na promoção: {resultado['duplicados']}"
        )
        for erro in resultado["erros"]:
            print(f"   promoção recusada, item {erro['item_id']}: {erro['erro']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
