"""Remove as compras em aberto da D-23, agora só exibidas (D-28).

    make pluggy-remover-abertas                # simulação (padrão)
    make pluggy-remover-abertas executar=1     # grava
    cd api && python -m scripts.remover_abertas_d28 [--simular | --executar]

Para cada item vivo do staging com a marca de compra em aberto: soft delete
do item e da transação (liberando o id da Pluggy para a versão lançada). A
transação que o usuário editou fica, e o item ganha uma nota.

Simula por padrão (`--simular` só deixa isso explícito). `--executar` grava,
com autor `remover_abertas_d28` na auditoria.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.remover_abertas_d28 import PlanoRemocao, RemoverAbertasD28Service


def imprimir(plano: PlanoRemocao, *, executado: bool) -> None:
    modo = "EXECUÇÃO" if executado else "SIMULAÇÃO (nada foi gravado)"
    print(f"== Compras em aberto da D-23 (D-28): {modo} ==")
    if not plano.linhas:
        print("nenhum item em aberto no staging.")
        return
    print(f"{'item':>6}  {'data':<10}  {'valor':>10}  {'cartão':<32}  ação")
    for linha in plano.linhas:
        data = f"{linha.data:%d/%m/%Y}" if linha.data else "—"
        valor = f"{linha.valor:.2f}" if linha.valor is not None else "—"
        acao = linha.acao.value if executado else f"{linha.acao.value} (simulação)"
        print(f"{linha.item_id:>6}  {data:<10}  {valor:>10}  {linha.cartao[:32]:<32}  {acao}")
    verbo_r = "removidos" if executado else "seriam removidos"
    verbo_m = "mantidos" if executado else "seriam mantidos"
    print(f"\n{verbo_r}: {len(plano.a_remover)} | {verbo_m} (editados): {len(plano.mantidas)}")
    for linha in plano.mantidas:
        print(f"   item {linha.item_id} / transação {linha.transacao_id}: edição do usuário")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--simular", action="store_true", help="só lê (o padrão)")
    modo.add_argument("--executar", action="store_true", help="grava")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        service = RemoverAbertasD28Service(session)
        plano = service.planejar()
        if not args.executar:
            session.rollback()
            imprimir(plano, executado=False)
            return 0
        try:
            service.executar(plano)
        except Exception as exc:
            session.rollback()
            print(f"Falhou e foi desfeito: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        session.commit()
        imprimir(plano, executado=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
