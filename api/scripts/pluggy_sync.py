"""Sincroniza a Pluggy para o staging (fase 5b, passos 6 e 8).

    make sync                 # ou: cd api && python -m scripts.pluggy_sync
    make sync simular=1       # ou: ... --simular

Sem flag, grava: uma importação de origem `pluggy` com os itens novos de
todas as contas mapeadas, e `ultimo_sync_em` de quem foi lido sem erro. Sem
item novo, não cria importação. Rodar duas vezes seguidas não cria nada na
segunda.

Duas sincronizações nunca rodam juntas: com outra em curso (a agendada, ou o
"Atualizar agora" do painel), esta desiste com código 3, sem gravar nada.

`--simular` lê a Pluggy de verdade e o banco, monta tudo o que a sync
gravaria e imprime, sem gravar nada — nem `ultimo_sync_em`. A amostra mostra
data, valor, tipo, competência, forma, pessoa e confiança, sem a descrição.

Em `transacoes` só entra o item limpo, pela exceção da D-21 (regra 5): a
sync o promove pelo mesmo `aprovar()` da revisão, com autor `sync_pluggy`.
O resto fica na revisão, e o resumo diz quantos e por quê.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Categoria, FormaPagamento, Pessoa
from app.services.promocao_pluggy import MOTIVOS, ROTULOS_REJEICAO
from app.services.sync_pluggy import ResultadoSync

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
        if c.abertas or c.atualizar or c.canceladas:
            print(
                f"   compras pendentes do cartão (D-28): {c.abertas} lidas | "
                f"só para exibição {len(c.pendentes)} | resto da D-23 no staging, "
                f"a atualizar {len(c.atualizar)} | canceladas {len(c.canceladas)}"
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
    verbo_p = "ficariam" if resultado.simulado else "ficam"
    print(
        f"pendentes do cartão que {verbo_p} só para exibição (D-28): {resultado.pendentes_exibicao}"
    )
    verbo = "seriam promovidos" if resultado.simulado else "promovidos"
    print(f"{verbo} automaticamente (D-21): {resultado.promovidos}")
    if resultado.rejeitados:
        verbo_r = "seriam rejeitados" if resultado.simulado else "rejeitados"
        print(f"{verbo_r} automaticamente (D-22): {sum(resultado.rejeitados.values())}")
        for chave, n in resultado.rejeitados.most_common():
            print(f"   {ROTULOS_REJEICAO.get(chave, chave)}: {n}")
    if not resultado.simulado and (
        resultado.abertas_confirmadas
        or resultado.abertas_atualizadas
        or resultado.abertas_canceladas
    ):
        print(
            f"resto da D-23: {resultado.abertas_confirmadas} confirmadas pelo banco, "
            f"{resultado.abertas_atualizadas} atualizadas, "
            f"{resultado.abertas_canceladas} canceladas"
        )
    print(f"na revisão: {sum(resultado.na_revisao.values())}")
    for motivo, texto in MOTIVOS.items():
        if resultado.na_revisao[motivo]:
            print(f"   {texto}: {resultado.na_revisao[motivo]}")
    for erro in resultado.erros_promocao:
        print(f"   promoção recusada, item {erro['item_id']}: {erro['erro']}")
    if resultado.importacao_id is not None:
        print(f"importação criada: #{resultado.importacao_id}")


def _linha(a: dict[str, Any], formas: dict[int, str], pessoas: dict[int, str]) -> str:
    marcas = ["PROMOVE" if a.get("destino") == "promover" else "REVISÃO"]
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

    # O mesmo caminho do agendador e do botão do painel, com a trava que
    # impede duas sincronizações ao mesmo tempo.
    from app.services.execucao_sync import SyncOcupada, executar

    try:
        resultado = executar(cfg, simular=args.simular, ao_terminar=imprimir)
    except SyncOcupada:
        print(
            "Outra sincronização está rodando agora (a agendada ou a do painel). "
            "Nada foi feito; tente de novo quando ela terminar.",
            file=sys.stderr,
        )
        return 3
    except Exception as exc:
        # A gravação é uma transação só: falhou, nada fica pela metade.
        print(f"A gravação falhou e foi desfeita: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 1 if any(c.erro for c in resultado.contas) else 0


if __name__ == "__main__":
    sys.exit(main())
