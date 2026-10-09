"""Sincroniza a Pluggy para o staging (fase 5b, passos 6 e 8).

    make sync                 # ou: cd api && python -m scripts.pluggy_sync
    make sync simular=1       # ou: ... --simular

Sem flag, grava: uma importação de origem `pluggy` com os itens novos de
todas as contas mapeadas, e `ultimo_sync_em` de quem foi lido sem erro. Sem
item novo, não cria importação. Rodar duas vezes seguidas não cria nada na
segunda.

`--simular` lê a Pluggy de verdade e o banco, monta tudo o que a sync
gravaria e imprime, sem gravar nada — nem `ultimo_sync_em`. A amostra mostra
data, valor, tipo, competência, forma, pessoa e confiança, sem a descrição.

Nada aqui escreve em `transacoes` (regra 5): a sync só enche a revisão.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.conversao_pluggy import FUSO
from app.models import Categoria, FormaPagamento, Pessoa
from app.pluggy import PluggyCliente, RespostaBruta
from app.services.sync_pluggy import ResultadoSync, SyncPluggyService

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_ENV = RAIZ / ".env"
AMOSTRA_POR_CONTA = 8


def imprimir(resultado: ResultadoSync, session: Session) -> None:
    formas = {f.id: f.apelido for f in session.scalars(select(FormaPagamento))}
    pessoas = {p.id: p.nome for p in session.scalars(select(Pessoa))}
    categorias = {c.id: c.nome for c in session.scalars(select(Categoria))}
    modo = "SIMULAÇÃO (nada foi gravado)" if resultado.simulado else "SYNC"
    print(f"== {modo} ==")
    for c in resultado.contas:
        print(f"\n[{c.mapeamento_id}] {c.rotulo}")
        if c.erro:
            print(f"   ERRO: {c.erro}")
            continue
        print(f"   janela {c.janela_inicio} a {c.janela_fim}")
        print(
            f"   novos {c.novos} | já existentes {c.ja_existentes} | pendentes ignoradas "
            f"{c.pendentes_ignoradas} | fora da janela {c.fora_da_janela} | possíveis "
            f"duplicatas {c.possiveis_duplicatas}"
        )
        if c.com_fatura or c.fallback_competencia:
            print(
                f"   compras de cartão com fatura achada: {c.com_fatura}; "
                f"fallback de competência: {len(c.fallback_competencia)}"
            )
            for id_ in c.fallback_competencia:
                print(f"      fallback: {id_}")
        categoria_do = {a["id_externo"]: a.get("categoria_id") for a in c.amostra}
        for e in c.encargos:
            cat = categorias.get(categoria_do.get(f"bill:{e.bill_id}:encargos") or 0, "—")
            print(
                f"   encargos fatura {e.competencia:%m/%Y}: R$ {e.valor} "
                f"(bill {e.bill_id}, categoria {cat})"
            )
        for a in c.avisos:
            print(f"   aviso: {a}")
        for linha in c.amostra[:AMOSTRA_POR_CONTA]:
            print("   " + _linha(linha, formas, pessoas))
        if len(c.amostra) > AMOSTRA_POR_CONTA:
            print(f"   ... e mais {len(c.amostra) - AMOSTRA_POR_CONTA} item(ns)")
    if resultado.formas_novas:
        verbo = "seria criada" if resultado.simulado else "criada"
        print("\nformas de pagamento novas (D-21):")
        for f in resultado.formas_novas:
            print(f"   {verbo}: {f.apelido} ({f.tipo.value}, conta {f.conta_id})")
    print(f"\nitens novos no total: {resultado.itens_novos}")
    if resultado.importacao_id is not None:
        print(f"importação criada: #{resultado.importacao_id}")


def _linha(a: dict[str, Any], formas: dict[int, str], pessoas: dict[int, str]) -> str:
    marcas = []
    if a["observacao"] and "Possível duplicata" in a["observacao"]:
        marcas.append("DUPLICATA?")
    if (a["id_externo"] or "").startswith("bill:"):
        marcas.append("ENCARGOS")
    if a["observacao"] and "Competência" in a["observacao"]:
        marcas.append("COMPETÊNCIA ESTIMADA")
    pessoa = pessoas.get(a["pessoa_id"], "conjunto") if a["pessoa_id"] else "conjunto"
    forma = (
        f"nova: {a['forma_nova']}"
        if a.get("forma_nova")
        else formas.get(a["forma_pagamento_id"], "?")
    )
    return (
        f"{a['data']:%d/%m/%Y}  {a['valor']:>9}  {a['tipo']:<13} comp {a['competencia']:%m/%Y}  "
        f"{forma:<32} {pessoa:<8} "
        f"conf {a['confianca_conversao']}/{a['confianca_staging']}  {' '.join(marcas)}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--simular", action="store_true", help="lê tudo e não grava nada")
    args = parser.parse_args(argv)
    cfg = Settings(_env_file=ARQUIVO_ENV)
    if cfg.pluggy_client_id is None or cfg.pluggy_client_secret is None:
        print("PLUGGY_CLIENT_ID e PLUGGY_CLIENT_SECRET não estão definidos.", file=sys.stderr)
        return 2

    from app.db import SessionLocal

    respostas: list[RespostaBruta] = []
    hoje = datetime.now(FUSO).date()
    with (
        PluggyCliente(
            cfg.pluggy_client_id, cfg.pluggy_client_secret, ao_responder=respostas.append
        ) as cliente,
        SessionLocal() as session,
    ):
        servico = SyncPluggyService(session, cliente, hoje=hoje, respostas_brutas=lambda: respostas)
        try:
            resultado = servico.sincronizar(simular=args.simular)
        except Exception as exc:
            # A gravação é uma transação só: falhou, nada fica pela metade.
            session.rollback()
            print(f"A gravação falhou e foi desfeita: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        if args.simular:
            session.rollback()
        else:
            session.commit()
        imprimir(resultado, session)
    return 1 if any(c.erro for c in resultado.contas) else 0


if __name__ == "__main__":
    sys.exit(main())
