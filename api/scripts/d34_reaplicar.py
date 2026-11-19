"""Reaplica a D-34 nos dados gravados: estornos e aplicações/resgates.

    make d34-reaplicar                # simulação (padrão)
    make d34-reaplicar executar=1     # grava SÓ as aplicações e resgates
    cd api && python -m scripts.d34_reaplicar [--simular | --executar] [--item ...]

Simula por padrão (`--simular` só deixa isso explícito): não grava nada e
termina com "Nada foi gravado.".

* Estornos (item 1): receita num cartão de crédito passaria a abater o gasto,
  na categoria e na pessoa da compra original. O script mostra quantos
  achariam a original, quantos ficariam com a categoria sugerida pela Pluggy e
  o efeito por mês. `--executar` recusa: "o estorno aguarda a mudança de
  schema da D-34". Nenhuma escrita para estorno.
* Aplicações e resgates (item 2): a transação já gravada volta à revisão como
  transferência (o usuário escolhe a outra conta); rendimento segue receita.
  Nunca onde o usuário editou (auditoria, D-06).

`--executar` com `--item aplicacoes`, ou sem `--item`, grava o item 2 (autor
`d34_reaplicar`) e recusa o item 1; `--executar --item estornos` só recusa.

No terminal só saem contagens, somas, meses e categorias: nada de descrição.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.d34_reaplicar import (
    MENSAGEM_ESTORNO_AGUARDA_SCHEMA,
    AguardaSchema,
    D34ReaplicarService,
    PlanoD34,
)

CENTAVO = Decimal("0.01")


def _brl(valor: Decimal) -> str:
    texto = f"{valor.quantize(CENTAVO):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def _soma(valores: list[Decimal]) -> Decimal:
    return sum(valores, Decimal("0"))


def _mes(competencia: date) -> str:
    return competencia.strftime("%Y-%m")


def imprimir_estornos(plano: PlanoD34) -> None:
    print("\n-- ESTORNOS (item 1: SÓ simulação; o estorno aguarda schema) --")
    todos = plano.estornos
    if not todos:
        print("nenhuma receita em cartão de crédito.")
        return
    original = plano.estornos_com("original")
    sugestao = plano.estornos_com("sugestao")
    sem = plano.estornos_com("sem_destino")
    editados = plano.estornos_com("editado")
    print(f"receitas em cartão de crédito (estornos de hoje): {len(todos)}")
    print(f"   com a compra original achada (categoria e pessoa dela): {len(original)}")
    print(f"   com a categoria sugerida pela Pluggy e o titular do cartão: {len(sugestao)}")
    print(f"   sem original nem sugestão (só o titular, sem categoria): {len(sem)}")
    print(f"   pulados por edição do usuário: {len(editados)}")
    aplicaveis = plano.estornos_com("original", "sugestao", "sem_destino")
    por_categoria: dict[str, list[Decimal]] = defaultdict(list)
    por_pessoa: dict[str, int] = defaultdict(int)
    for e in aplicaveis:
        por_categoria[e.categoria or "(sem categoria)"].append(e.valor)
        por_pessoa[e.pessoa or "Conjunto"] += 1
    if por_categoria:
        print("por categoria de destino:")
        for rotulo, valores in sorted(por_categoria.items(), key=lambda x: (-len(x[1]), x[0])):
            print(f"   {len(valores):>4}  {rotulo}  {_brl(_soma(valores))}")
        print("por pessoa: " + ", ".join(f"{k} {v}" for k, v in sorted(por_pessoa.items())))
    print(f"soma dos estornos que seriam abatidos: {_brl(_soma([e.valor for e in aplicaveis]))}")


def imprimir_aplicacoes(plano: PlanoD34) -> None:
    print("\n-- APLICAÇÕES E RESGATES (item 2) --")
    todas = plano.aplicacoes
    if not todas:
        print("nenhuma transação vinda de aplicação ou resgate.")
        return
    viram = plano.aplicacoes_com("transferencia")
    rendimento = plano.aplicacoes_com("rendimento")
    editadas = plano.aplicacoes_com("editado")
    como_receita = [a for a in viram if a.tipo.value == "receita"]
    como_despesa = [a for a in viram if a.tipo.value == "despesa"]
    print(f"transações de aplicação ou resgate da Pluggy: {len(todas)}")
    print(
        f"   virariam transferência: {len(viram)} "
        f"(hoje receita {len(como_receita)}, despesa {len(como_despesa)}) "
        f"somando {_brl(_soma([a.valor for a in viram]))}"
    )
    print(
        f"   seguem receita, rendimento: {len(rendimento)} "
        f"somando {_brl(_soma([a.valor for a in rendimento]))}"
    )
    print(f"   puladas por edição do usuário: {len(editadas)}")


def imprimir_meses(plano: PlanoD34) -> None:
    print("\n-- TOTAIS POR MÊS (competência) --")
    meses = plano.meses()
    if not meses:
        print("nenhum mês muda.")
        return
    print(
        f"{'mês':<8}{'gasto antes':>16}{'gasto depois':>16}"
        f"{'receitas antes':>18}{'receitas depois':>18}"
    )
    for mes in meses:
        antes = plano.atuais.get(mes)
        depois = plano.depois(mes)
        gasto_antes = antes.despesas if antes else Decimal("0")
        receitas_antes = antes.receitas if antes else Decimal("0")
        print(
            f"{_mes(mes):<8}{_brl(gasto_antes):>16}{_brl(depois.despesas):>16}"
            f"{_brl(receitas_antes):>18}{_brl(depois.receitas):>18}"
        )
    print(
        "gasto depois = despesa menos estorno (gasto líquido) e menos aplicação; "
        "receitas depois = sem estorno e sem resgate."
    )


def imprimir(plano: PlanoD34, *, itens: str) -> None:
    if itens in ("todos", "estornos"):
        imprimir_estornos(plano)
    if itens in ("todos", "aplicacoes"):
        imprimir_aplicacoes(plano)
    imprimir_meses(plano)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--simular", action="store_true", help="só lê (o padrão)")
    modo.add_argument("--executar", action="store_true", help="grava o item 2; recusa o item 1")
    parser.add_argument("--item", choices=("todos", "estornos", "aplicacoes"), default="todos")
    args = parser.parse_args(argv)

    if args.executar and args.item == "estornos":
        print(f"Recusado: {MENSAGEM_ESTORNO_AGUARDA_SCHEMA}. Nada foi gravado.", file=sys.stderr)
        return 2

    from app.db import SessionLocal

    with SessionLocal() as session:
        service = D34ReaplicarService(session)
        plano = service.planejar()
        if not args.executar:
            session.rollback()
            print("== D-34: estornos e aplicações/resgates (SIMULAÇÃO) ==")
            imprimir(plano, itens=args.item)
            print("\nNada foi gravado.")
            return 0

        print("== D-34: EXECUÇÃO (só aplicações e resgates) ==")
        if args.item == "todos":
            try:
                service.executar_estornos(plano)
            except AguardaSchema as exc:
                print(f"Estornos recusados: {exc}. Nada foi gravado para estornos.")
        try:
            resultado = service.executar_aplicacoes(plano)
        except Exception as exc:
            session.rollback()
            print(f"Falhou e foi desfeito: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        session.commit()
        imprimir_aplicacoes(plano)
        print(
            f"\ngravado: {resultado['devolvidas_a_revisao']} voltaram à revisão como "
            f"transferência; mudaram desde o plano (puladas): {resultado['mudou_desde_o_plano']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
