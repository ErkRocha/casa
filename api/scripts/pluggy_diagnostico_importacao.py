"""Diagnóstico de uma importação da Pluggy — somente leitura (D-21).

    make pluggy-diagnostico-importacao [i=4]
    cd api && python -m scripts.pluggy_diagnostico_importacao [--importacao 4]

Sem `--importacao`, usa a primeira importação da Pluggy (a da primeira sync).
Conta os itens vivos por conta da Pluggy e por forma de pagamento, quantos
têm categoria, e responde:

a. os itens de cartão existem e estão com a forma do cartão (a do
   mapeamento)?
b. os itens de conta corrente estão todos com a forma Pix, mesmo sendo
   débito, boleto etc.? — cruzando a forma gravada com a operação que a
   Pluggy informou;

e lista as operações (`operationType`) e as categorias da Pluggy que
aparecem, com contagens. Operação e categoria saem do comprovante da
importação (o JSON bruto da Pluggy), porque o staging não as guarda.

No terminal: ids, contagens, nomes de forma, conta e categoria. Nenhuma
descrição, valor ou dado de pessoa. Não grava nada.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ContaPluggy, FormaPagamento, Importacao, ImportacaoItem
from app.services.comprovante_pluggy import ler_comprovante

SEM_MAPEAMENTO = "conta da Pluggy sem mapeamento"


@dataclass
class Diagnostico:
    importacao_id: int
    status: str
    criada_em: str
    itens: int = 0
    com_categoria: int = 0
    por_status: Counter[str] = field(default_factory=Counter)
    #: rótulo -> Counter("itens", "com_categoria")
    por_conta: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    por_forma: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    #: (a) cartão
    cartao_itens: int = 0
    cartao_com_forma_do_mapeamento: int = 0
    cartao_outras_formas: Counter[str] = field(default_factory=Counter)
    #: (b) conta corrente
    conta_itens: int = 0
    conta_por_tipo_de_forma: Counter[str] = field(default_factory=Counter)
    #: (operação da Pluggy, tipo da forma gravada) nos itens de conta corrente
    conta_operacao_x_forma: Counter[tuple[str, str]] = field(default_factory=Counter)
    #: (BANK|CREDIT, operação)
    operacoes: Counter[tuple[str, str]] = field(default_factory=Counter)
    #: (categoryId, nome) -> itens
    categorias: Counter[tuple[str, str]] = field(default_factory=Counter)
    encargos: int = 0
    fora_do_comprovante: int = 0


def primeira_importacao_pluggy(session: Session) -> int | None:
    return session.scalar(
        select(Importacao.id)
        .where(Importacao.origem == "pluggy", Importacao.deleted_em.is_(None))
        .order_by(Importacao.id)
        .limit(1)
    )


def diagnosticar(session: Session, importacao_id: int) -> Diagnostico:
    importacao = session.get(Importacao, importacao_id)
    if importacao is None or importacao.deleted_em is not None:
        raise SystemExit(f"Importação {importacao_id} não existe.")
    if importacao.origem != "pluggy":
        raise SystemExit(f"A importação {importacao_id} não é da Pluggy ({importacao.origem}).")

    d = Diagnostico(
        importacao_id=importacao.id,
        status=importacao.status.value,
        criada_em=f"{importacao.criado_em:%d/%m/%Y %H:%M}",
    )
    comprovante = ler_comprovante(importacao.arquivo_conteudo)
    formas = {f.id: f for f in session.scalars(select(FormaPagamento))}
    mapas: dict[str, ContaPluggy] = {}
    for candidato in session.scalars(select(ContaPluggy).order_by(ContaPluggy.id)):
        # O vivo vence o apagado; entre vivos, o mais novo.
        atual = mapas.get(candidato.pluggy_account_id)
        if atual is None or atual.deleted_em is not None or candidato.deleted_em is None:
            mapas[candidato.pluggy_account_id] = candidato

    itens = session.scalars(
        select(ImportacaoItem)
        .where(ImportacaoItem.importacao_id == importacao_id, ImportacaoItem.deleted_em.is_(None))
        .order_by(ImportacaoItem.id)
    )
    for item in itens:
        d.itens += 1
        d.por_status[item.status.value] += 1
        tem_categoria = item.categoria_sugerida_id is not None
        d.com_categoria += tem_categoria
        forma = formas.get(item.forma_pagamento_sugerida_id or 0)
        rotulo_forma = f"{forma.apelido} ({forma.tipo.value})" if forma else "sem forma"
        d.por_forma[rotulo_forma]["itens"] += 1
        d.por_forma[rotulo_forma]["com_categoria"] += tem_categoria

        id_externo = item.id_externo or ""
        if id_externo.startswith("bill:"):
            d.encargos += 1
            conta_id = comprovante.conta_da_fatura(id_externo.split(":")[1])
            operacao, categoria = "(encargo deduzido)", None
        else:
            transacao = comprovante.transacoes.get(id_externo)
            if transacao is None:
                d.fora_do_comprovante += 1
                d.por_conta["(transação fora do comprovante)"]["itens"] += 1
                continue
            conta_id = transacao.account_id
            operacao = transacao.operation_type or "(sem operação)"
            categoria = (transacao.category_id or "—", transacao.category or "(sem categoria)")

        conta = comprovante.contas.get(conta_id or "")
        tipo_conta = conta.type if conta else "?"
        mapa = mapas.get(conta_id or "")
        rotulo_conta = (
            f"[{mapa.id}] {mapa.conta.nome} / {mapa.forma_pagamento.apelido} ({tipo_conta})"
            + (" — mapeamento desativado" if mapa.deleted_em or not mapa.ativo else "")
            if mapa
            else f"{SEM_MAPEAMENTO} ({tipo_conta})"
        )
        d.por_conta[rotulo_conta]["itens"] += 1
        d.por_conta[rotulo_conta]["com_categoria"] += tem_categoria
        d.operacoes[(tipo_conta, operacao)] += 1
        if categoria is not None:
            d.categorias[categoria] += 1

        tipo_forma = forma.tipo.value if forma else "sem forma"
        if tipo_conta == "CREDIT":
            d.cartao_itens += 1
            if mapa is not None and item.forma_pagamento_sugerida_id == mapa.forma_pagamento_id:
                d.cartao_com_forma_do_mapeamento += 1
            else:
                d.cartao_outras_formas[rotulo_forma] += 1
        elif tipo_conta == "BANK":
            d.conta_itens += 1
            d.conta_por_tipo_de_forma[tipo_forma] += 1
            d.conta_operacao_x_forma[(operacao, tipo_forma)] += 1
    return d


def imprimir(d: Diagnostico) -> None:
    print(f"== Importação #{d.importacao_id} (Pluggy), de {d.criada_em}, status {d.status} ==")
    print(f"itens vivos: {d.itens}, com categoria: {d.com_categoria}")
    print("por status: " + ", ".join(f"{k} {v}" for k, v in sorted(d.por_status.items())))

    print("\npor conta da Pluggy (mapeamento):")
    for rotulo, c in sorted(d.por_conta.items()):
        print(f"   {c['itens']:>5} itens, {c['com_categoria']:>5} com categoria  {rotulo}")

    print("\npor forma de pagamento gravada:")
    for rotulo, c in sorted(d.por_forma.items(), key=lambda x: -x[1]["itens"]):
        print(f"   {c['itens']:>5} itens, {c['com_categoria']:>5} com categoria  {rotulo}")

    print("\n(a) itens de cartão com a forma do cartão (a do mapeamento):")
    if d.cartao_itens == 0:
        print("   NÃO HÁ itens de cartão nesta importação.")
    elif d.cartao_com_forma_do_mapeamento == d.cartao_itens:
        print(f"   CONFIRMADO: os {d.cartao_itens} itens de cartão estão com a forma do cartão.")
    else:
        print(
            f"   REFUTADO: {d.cartao_com_forma_do_mapeamento} de {d.cartao_itens} estão com a "
            "forma do cartão. Os outros:"
        )
        for rotulo, n in d.cartao_outras_formas.most_common():
            print(f"      {n:>5}  {rotulo}")

    print("\n(b) itens de conta corrente todos com a forma Pix:")
    if d.conta_itens == 0:
        print("   NÃO HÁ itens de conta corrente nesta importação.")
    else:
        pix = d.conta_por_tipo_de_forma.get("pix", 0)
        veredito = "CONFIRMADO" if pix == d.conta_itens else "REFUTADO"
        print(f"   {veredito}: {pix} de {d.conta_itens} itens de conta estão com forma Pix.")
        print(
            "   formas gravadas: "
            + ", ".join(f"{k} {v}" for k, v in d.conta_por_tipo_de_forma.most_common())
        )
        print("   operação da Pluggy x forma gravada:")
        for (operacao, forma), n in sorted(
            d.conta_operacao_x_forma.items(), key=lambda x: (-x[1], x[0])
        ):
            print(f"      {n:>5}  {operacao:<34} -> {forma}")

    print("\noperações da Pluggy (operationType):")
    for (tipo_conta, operacao), n in sorted(d.operacoes.items(), key=lambda x: (x[0][0], -x[1])):
        print(f"   {n:>5}  {tipo_conta:<7} {operacao}")

    print("\ncategorias da Pluggy:")
    for (categoria_id, nome), n in d.categorias.most_common():
        print(f"   {n:>5}  {categoria_id:<10} {nome}")

    if d.encargos or d.fora_do_comprovante:
        print(
            f"\nencargos deduzidos (sem transação na Pluggy): {d.encargos}; "
            f"itens sem a transação no comprovante: {d.fora_do_comprovante}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--importacao", type=int, help="padrão: a primeira da Pluggy")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        importacao_id = args.importacao or primeira_importacao_pluggy(session)
        if importacao_id is None:
            print("Nenhuma importação da Pluggy no banco.", file=sys.stderr)
            return 2
        imprimir(diagnosticar(session, importacao_id))
        session.rollback()
    return 0


if __name__ == "__main__":
    sys.exit(main())
