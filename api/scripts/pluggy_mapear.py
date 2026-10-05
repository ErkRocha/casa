"""Lista as contas da Pluggy ainda sem mapeamento (fase 5b, passo 4).

    make pluggy-mapear [item=ID]
    cd api && python -m scripts.pluggy_mapear --item ID

Para cada conexão (item), lê as contas na Pluggy e mostra as que ainda não
têm linha viva em `contas_pluggy`, com tipo e nome. Embaixo, as contas e
formas de pagamento daqui, com os ids que o cadastro pede.

Só lê: nada é gravado na Pluggy nem no banco. O cadastro é pela API
(`POST /contas-pluggy`), onde a validação da forma contra a conta mora.

Cartão de crédito (`CREDIT`) aponta para a conta corrente que paga a fatura,
com a forma `credito` daquele cartão — o mesmo encaixe que a fatura em PDF
usa. Os ids dos items vêm de `--item`, de `PLUGGY_ITEM_IDS` ou, se a Pluggy
liberar, de `GET /v2/items`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

if __package__ in (None, ""):
    # Execução direta (`python api/scripts/pluggy_mapear.py`).
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Conta as ContaLocal
from app.models import FormaPagamento
from app.pluggy import Conta, PluggyAutenticacaoErro, PluggyCliente, PluggyErro
from app.pluggy import Item as ItemPluggy
from app.services.pluggy_mapeamento import ContaPluggyService

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = RAIZ / ".env"


class _Ambiente(BaseSettings):
    model_config = SettingsConfigDict(env_file=ARQUIVO_ENV, extra="ignore")

    pluggy_item_ids: str = ""


class LeitorContas(Protocol):
    """O pedaço do `PluggyCliente` que o script usa. Facilita o teste."""

    def listar_contas(self, item_id: str, tipo: str | None = None) -> list[Conta]: ...

    def listar_items(self) -> list[ItemPluggy]: ...


@dataclass(frozen=True, slots=True)
class Pendente:
    item_id: str
    conta: Conta


def nao_mapeadas(
    cliente: LeitorContas, item_ids: Iterable[str], session: Session
) -> list[Pendente]:
    """Contas da Pluggy sem mapeamento vivo, na ordem em que a Pluggy lista."""
    mapeados = ContaPluggyService(session).ids_mapeados()
    return [
        Pendente(item_id, conta)
        for item_id in item_ids
        for conta in cliente.listar_contas(item_id)
        if conta.id not in mapeados
    ]


def _rotulo(conta: Conta) -> str:
    nome = conta.marketing_name or conta.name or "(sem nome)"
    final = f" final {conta.number[-4:]}" if conta.number else ""
    return f"{conta.type}/{conta.subtype or '?'}  {nome}{final}"


def imprimir(pendentes: list[Pendente], session: Session) -> None:
    if not pendentes:
        print("Todas as contas da Pluggy já estão mapeadas.")
    else:
        print(f"Contas da Pluggy sem mapeamento: {len(pendentes)}")
        item_atual = None
        for p in pendentes:
            if p.item_id != item_atual:
                item_atual = p.item_id
                print(f"\n  item {p.item_id}")
            print(f"    conta {p.conta.id}  {_rotulo(p.conta)}")

    print("\nContas daqui:")
    for c in session.scalars(
        select(ContaLocal).where(ContaLocal.deleted_em.is_(None)).order_by(ContaLocal.id)
    ):
        print(f"  {c.id:>3}  {c.nome} ({c.tipo.value}){'' if c.ativo else '  [inativa]'}")

    print("\nFormas de pagamento (a forma tem que ser da conta escolhida):")
    for f in session.scalars(
        select(FormaPagamento)
        .where(FormaPagamento.deleted_em.is_(None), FormaPagamento.ativo.is_(True))
        .order_by(FormaPagamento.id)
    ):
        print(f"  {f.id:>3}  {f.apelido} ({f.tipo.value}), conta {f.conta_id}")

    if pendentes:
        print(
            "\nPara mapear: POST /contas-pluggy com pluggy_item_id, pluggy_account_id, "
            "conta_id, forma_pagamento_id e sincronizar_desde.\n"
            "Cartão (CREDIT): conta = a corrente que paga a fatura; forma = o crédito "
            "daquele cartão."
        )


def _item_ids(argumento: list[str] | None, cliente: LeitorContas) -> list[str]:
    if argumento:
        return argumento
    do_env = [i.strip() for i in _Ambiente().pluggy_item_ids.split(",") if i.strip()]
    return do_env or [item.id for item in cliente.listar_items()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--item", action="append", help="id do item; pode repetir")
    args = parser.parse_args(argv)

    cfg = Settings(_env_file=ARQUIVO_ENV)
    if cfg.pluggy_client_id is None or cfg.pluggy_client_secret is None:
        print("PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET não estão definidos.", file=sys.stderr)
        return 2

    # Import tardio: `app.db` monta a engine na importação, e o erro de
    # credencial acima deve sair antes de qualquer conexão.
    from app.db import SessionLocal

    try:
        with PluggyCliente(cfg.pluggy_client_id, cfg.pluggy_client_secret) as cliente:
            item_ids = _item_ids(args.item, cliente)
            with SessionLocal() as session:
                pendentes = nao_mapeadas(cliente, item_ids, session)
                imprimir(pendentes, session)
    except PluggyAutenticacaoErro as exc:
        print(f"Credencial recusada pela Pluggy: {exc}", file=sys.stderr)
        return 1
    except PluggyErro as exc:
        print(f"Falha ao falar com a Pluggy: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
