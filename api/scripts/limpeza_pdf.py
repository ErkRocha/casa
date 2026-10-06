"""Remove o dado de PDF que a Pluggy vai cobrir (fase 5b, passo 7).

    cd api && python -m scripts.limpeza_pdf --origem nubank_fatura=6 --origem nubank_extrato=7
    cd api && python -m scripts.limpeza_pdf --origem ... --executar

Cada `--origem` liga a origem de um parser de PDF ao id de um mapeamento da
Pluggy (`GET /contas-pluggy`). Só some o que é daquela origem e tem data a
partir do `sincronizar_desde` do mapeamento; o anterior fica.

Simula por padrão (ou com `--simular`): conta e não grava. Só `--executar`
grava — soft delete, com auditoria, nunca DELETE.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.base import RegraViolada
from app.services.limpeza_pdf import LimpezaPdfService, ResultadoLimpeza


def _correspondencia(pares: list[str]) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for par in pares:
        origem, _, id_ = par.partition("=")
        if not origem or not id_.isdigit():
            raise argparse.ArgumentTypeError(f"use origem=id_do_mapeamento, não {par!r}")
        resultado[origem.strip()] = int(id_)
    return resultado


def imprimir(r: ResultadoLimpeza) -> None:
    print("== SIMULAÇÃO (nada foi gravado) ==" if r.simulado else "== LIMPEZA EXECUTADA ==")
    for o in r.origens:
        print(f"\n{o.origem} -> mapeamento {o.mapeamento_id} ({o.rotulo}), corte {o.corte}")
        status = dict(o.itens_por_status)
        print(f"   transações: {o.transacoes} | itens de staging: {o.itens} {status}")
        print(
            f"   preservados antes do corte: {o.transacoes_preservadas} transação(ões), "
            f"{o.itens_preservados} item(ns)"
        )
        print(f"   importações que ficam canceladas: {o.importacoes_canceladas or 'nenhuma'}")
    if r.nao_tocadas:
        print(f"\norigens de PDF sem correspondência, não tocadas: {', '.join(r.nao_tocadas)}")
    print(f"\ntotal: {r.transacoes} transação(ões) e {r.itens} item(ns) de staging")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--origem", action="append", required=True, help="origem=id_mapeamento")
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--simular", action="store_true", help="só conta (padrão)")
    modo.add_argument("--executar", action="store_true", help="grava o soft delete")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        try:
            resultado = LimpezaPdfService(session).limpar(
                _correspondencia(args.origem), simular=not args.executar
            )
        except (RegraViolada, argparse.ArgumentTypeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        imprimir(resultado)
        if args.executar:
            session.commit()
        else:
            session.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
