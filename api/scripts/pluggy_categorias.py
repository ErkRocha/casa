"""Proposta de mapeamento das categorias da Pluggy (D-21).

    make pluggy-categorias              # ou: cd api && python -m scripts.pluggy_categorias
    make pluggy-categorias aplicar=1    # ... --aplicar

Lê os comprovantes das importações da Pluggy (o JSON bruto que a sync guarda
em cada uma), conta as categorias das transações `POSTED` e mostra, para
cada uma, o que acontece com ela: já mapeada, proposta (com o alvo achado
na árvore daqui), ambígua (fica sem mapeamento, com o motivo), transferência
(nunca vira despesa) ou sem proposta.

Sem `--aplicar`, só lê. Com ele, cria antes as categorias do seed que a
proposta usa e o banco ainda não tem ("Compras", "Compras › Online", "Pets"...)
e grava as propostas, tudo pelos services, com autor
`mapeamento_categorias_pluggy` na auditoria. Rodar de novo não duplica:
categoria já mapeada é pulada, e categoria já criada é achada pelo caminho.

No terminal só saem ids, nomes de categoria e contagens.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Categoria, CategoriaPluggy, Importacao
from app.services.categorias_pluggy import (
    CategoriaACriar,
    CategoriaPluggyService,
    caminhos_vivos,
    categorias_por_caminho,
    criar_caminho,
    planejar_criacao,
    proposta_para,
    resolver_alvo,
)
from app.services.comprovante_pluggy import ler_comprovante

AUTOR = "mapeamento_categorias_pluggy"


def contar_categorias(session: Session) -> Counter[tuple[str | None, str | None]]:
    """(categoryId, category) -> transações POSTED distintas, em todos os comprovantes."""
    vistas: dict[str, tuple[str | None, str | None]] = {}
    for importacao in session.scalars(
        select(Importacao)
        .where(Importacao.origem == "pluggy", Importacao.deleted_em.is_(None))
        .order_by(Importacao.id)
    ):
        comprovante = ler_comprovante(importacao.arquivo_conteudo)
        for t in comprovante.transacoes.values():
            if t.status == "POSTED":
                vistas[t.id] = (t.category_id, t.category)
    return Counter(vistas.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("--aplicar", action="store_true", help="grava as propostas com alvo")
    args = parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        contagem = contar_categorias(session)
        if not contagem:
            print("Nenhuma transação POSTED nos comprovantes das importações da Pluggy.")
            return 0

        mapeadas = {
            m.pluggy_categoria_id: m
            for m in session.scalars(
                select(CategoriaPluggy).where(CategoriaPluggy.deleted_em.is_(None))
            )
        }
        caminhos = categorias_por_caminho(session)
        vivas = caminhos_vivos(session)
        #: (id da Pluggy, nome, categoria existente ou nula, caminho, nós a criar)
        a_gravar: list[tuple[str, str, Categoria | None, str, list[CategoriaACriar]]] = []
        resumo: Counter[str] = Counter()

        print(f"{'transações':>10}  {'categoryId':<10}  categoria da Pluggy -> destino")
        for (pluggy_id, nome), n in sorted(contagem.items(), key=lambda x: (-x[1], x[0][1] or "")):
            rotulo = f"{n:>10}  {pluggy_id or '—':<10}  {nome or '(sem nome)'}"
            if not pluggy_id or not nome:
                print(f"{rotulo} -> sem categoryId ou nome: não dá para mapear")
                resumo["sem_id"] += n
                continue
            if pluggy_id in mapeadas:
                m = mapeadas[pluggy_id]
                estado = "ativa" if m.ativo else "inativa"
                print(f"{rotulo} -> já mapeada ({estado}) para a categoria #{m.categoria_id}")
                resumo["ja_mapeada"] += n
                continue

            tipo, detalhe = proposta_para(nome)
            if tipo == "mapear":
                assert isinstance(detalhe, tuple)
                alvo = resolver_alvo(caminhos, detalhe)
                criacao = planejar_criacao(caminhos, vivas, detalhe) if alvo is None else None
                if alvo is not None:
                    caminho = next(c for c in detalhe if resolver_alvo(caminhos, (c,)) is alvo)
                    print(f"{rotulo} -> proposta: {caminho} (#{alvo.id})")
                    a_gravar.append((pluggy_id, nome, alvo, caminho, []))
                    resumo["proposta"] += n
                elif criacao is not None:
                    caminho, nos = criacao
                    novas = ", ".join(no.caminho for no in nos)
                    print(f"{rotulo} -> proposta: {caminho} (categoria a criar: {novas})")
                    a_gravar.append((pluggy_id, nome, None, caminho, nos))
                    resumo["proposta_criar"] += n
                else:
                    print(f"{rotulo} -> PROPOSTA SEM ALVO: nenhum de {', '.join(detalhe)} existe")
                    resumo["sem_alvo"] += n
            elif tipo == "ambigua":
                print(f"{rotulo} -> AMBÍGUA, fica sem mapeamento: {detalhe}")
                resumo["ambigua"] += n
            elif tipo == "transferencia":
                print(f"{rotulo} -> transferência, fica sem mapeamento (D-21)")
                resumo["transferencia"] += n
            else:
                print(f"{rotulo} -> SEM PROPOSTA: categoria fora da lista conhecida")
                resumo["sem_proposta"] += n

        total = sum(contagem.values())
        print(f"\ntransações POSTED nos comprovantes: {total}")
        for chave, texto in [
            ("ja_mapeada", "já mapeadas"),
            ("proposta", "com proposta e alvo"),
            ("proposta_criar", "com proposta e alvo a criar"),
            ("sem_alvo", "com proposta sem alvo no banco"),
            ("ambigua", "ambíguas"),
            ("transferencia", "transferências"),
            ("sem_proposta", "sem proposta"),
            ("sem_id", "sem categoryId"),
        ]:
            if resumo[chave]:
                print(f"   {texto}: {resumo[chave]}")

        a_criar = _categorias_a_criar(a_gravar)
        if not args.aplicar:
            if a_criar:
                print(f"\n{len(a_criar)} categoria(s) seriam criadas: {', '.join(a_criar)}")
            print(f"\n{len(a_gravar)} mapeamento(s) seriam criados. Nada foi gravado.")
            print("Revise a lista e rode com --aplicar para gravar.")
            session.rollback()
            return 0

        session.execute(text("SELECT set_config('app.autor', :autor, true)"), {"autor": AUTOR})
        service = CategoriaPluggyService(session)
        for pluggy_id, nome, categoria, caminho, nos in a_gravar:
            if categoria is None:
                antes = len(caminhos)
                categoria = criar_caminho(session, caminhos, nos)
                if len(caminhos) > antes:
                    print(f"   categoria criada: {caminho} (#{categoria.id})")
            service.criar(
                {
                    "pluggy_categoria_id": pluggy_id,
                    "pluggy_categoria_nome": nome,
                    "categoria_id": categoria.id,
                }
            )
            print(f"   criado: {pluggy_id} {nome} -> {caminho}")
        session.commit()
        print(f"\n{len(a_criar)} categoria(s) e {len(a_gravar)} mapeamento(s) criados.")
    return 0


def _categorias_a_criar(
    a_gravar: list[tuple[str, str, Categoria | None, str, list[CategoriaACriar]]],
) -> list[str]:
    """Caminhos que a aplicação criaria, sem repetir a raiz compartilhada."""
    vistos: dict[str, None] = {}
    for *_resto, nos in a_gravar:
        for no in nos:
            vistos.setdefault(no.caminho, None)
    return list(vistos)


if __name__ == "__main__":
    sys.exit(main())
