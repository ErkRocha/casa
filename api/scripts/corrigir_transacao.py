"""Correção pontual de uma transação, pedida pelo usuário, fora do painel.

    make corrigir-transacao args="observacao 1250 'motivo...'"            # simula
    make corrigir-transacao args="transferencia 1250 --origem 7 --destino 6" executar=1

Passa pelo service (as mesmas regras do painel) e audita como a API: a
sessão marca `app.autor` com o autor do painel ("usuario"), ou com
`--autor`. Sem `--executar`, mostra o antes e o depois e desfaz tudo.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import sessao_com_autor
from app.services.transacoes import TransacaoService

CAMPOS = ("tipo", "valor", "data", "competencia", "categoria_id", "observacao")


def _resumo(t: dict[str, Any]) -> str:
    return ", ".join(f"{c}={t.get(c)!s}" for c in CAMPOS)


def corrigir(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    p.add_argument("--executar", action="store_true", help="grava (sem ele, só simula)")
    p.add_argument("--autor", default=None, help='autor na auditoria (padrão: o da API, "usuario")')
    sub = p.add_subparsers(dest="acao", required=True)
    obs = sub.add_parser("observacao", help="grava a observação (o motivo) na transação")
    obs.add_argument("id", type=int)
    obs.add_argument("texto")
    tr = sub.add_parser("transferencia", help="despesa ou receita que era dinheiro entre contas")
    tr.add_argument("id", type=int)
    tr.add_argument("--origem", type=int, required=True)
    tr.add_argument("--destino", type=int, required=True)
    args = p.parse_args(argv)

    with sessao_com_autor(args.autor) as session:
        svc = TransacaoService(session)
        antes = svc.get(args.id)
        if args.acao == "observacao":
            depois = svc.atualizar(args.id, {"observacao": args.texto})
        else:
            depois = svc.virar_transferencia(args.id, args.origem, args.destino)
        print(f"antes : {_resumo(antes)}")
        print(f"depois: {_resumo(depois)}")
        if args.executar:
            session.commit()
            print("gravado.")
        else:
            session.rollback()
            print("simulação: nada foi gravado (use --executar).")
    return 0


if __name__ == "__main__":
    sys.exit(corrigir())
