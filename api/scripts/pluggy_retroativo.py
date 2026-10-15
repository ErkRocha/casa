"""Preenchimento retroativo das transações promovidas da Pluggy (D-21).

    make pluggy-retroativo                # simulação (padrão)
    make pluggy-retroativo executar=1     # grava
    cd api && python -m scripts.pluggy_retroativo [--simular | --executar]

Nas transações vindas de importação da Pluggy, aplica o que a sync de hoje
faria e a primeira sync não fez: categoria pela ordem da D-21 (regra do
usuário > mapeamento da Pluggy > local), onde a transação está sem
categoria, e forma de pagamento pela operação (débito, boleto,
transferência) nas de conta corrente. Nunca onde a auditoria mostra que o
usuário editou aquele campo.

Simula por padrão (`--simular` só deixa isso explícito). `--executar` grava,
com autor `retroativo_d21` na auditoria. Rode depois de
`make pluggy-categorias aplicar=1`: sem o mapeamento gravado, só regra e
local dão categoria.

No terminal só saem contagens, nomes de categoria e de forma.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.retroativo_pluggy import PlanoRetroativo, RetroativoPluggyService


def imprimir(plano: PlanoRetroativo, *, executado: bool) -> None:
    modo = "EXECUÇÃO" if executado else "SIMULAÇÃO (nada foi gravado)"
    print(f"== Retroativo D-21 nas transações da Pluggy: {modo} ==")
    print(f"transações vivas vindas da Pluggy: {plano.avaliadas}")
    if plano.fora:
        print(f"fora da avaliação: {sum(plano.fora.values())}")
        for motivo, n in plano.fora.most_common():
            print(f"   {motivo}: {n}")

    verbo = "ganharam" if executado else "ganhariam"
    print(f"\n{verbo} categoria: {plano.ganham_categoria}")
    for rotulo, n in sorted(plano.por_categoria.items(), key=lambda x: (-x[1], x[0])):
        print(f"   {n:>5}  {rotulo}")
    if plano.ganham_categoria:
        print("   origem: " + ", ".join(f"{k} {v}" for k, v in plano.por_origem.most_common()))
    if plano.categoria_mantida:
        print("sem categoria e mantidas assim:")
        for motivo, n in plano.categoria_mantida.most_common():
            print(f"   {motivo}: {n}")

    verbo = "mudaram" if executado else "mudariam"
    print(f"\n{verbo} de forma: {plano.mudam_forma}")
    for (de, para), n in sorted(plano.por_forma.items(), key=lambda x: (-x[1], x[0])):
        print(f"   {n:>5}  {de} -> {para}")
    novas = plano.formas_novas
    if novas:
        verbo_forma = "criadas" if executado else "seriam criadas"
        print(f"formas {verbo_forma}: " + ", ".join(f.apelido for f in novas))
    if plano.forma_mantida:
        print("forma mantida (conta corrente):")
        for motivo, n in plano.forma_mantida.most_common():
            print(f"   {motivo}: {n}")

    pulados = plano.pulados_por_edicao
    print(
        f"\npuladas por edição do usuário: categoria {pulados['categoria']}, "
        f"forma {pulados['forma']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--simular", action="store_true", help="só lê (o padrão)")
    modo.add_argument("--executar", action="store_true", help="grava")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        service = RetroativoPluggyService(session)
        plano = service.planejar()
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
            f"\ngravado: categoria em {resultado['categorias']}, forma em "
            f"{resultado['formas']}; mudaram desde o plano (puladas): "
            f"{resultado['mudou_desde_o_plano']}"
        )
        for erro in resultado["erros"]:
            print(f"   recusada pelo banco, transação {erro['transacao_id']}: {erro['erro']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
