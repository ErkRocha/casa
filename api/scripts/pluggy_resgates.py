"""Investigação dos resgates e aplicações da Pluggy — somente leitura.

    make pluggy-resgates
    cd api && python -m scripts.pluggy_resgates

A primeira sync trouxe 41 itens `RESGATE_APLIC_FINANCEIRA` na conta
corrente, e o usuário não usa caixinha há muito tempo. Hipótese: é o resgate
automático da conta remunerada — o saldo é aplicado sozinho e resgatado a
cada pagamento. Se for, esses créditos não são receita: são o próprio
dinheiro voltando para cobrir uma saída.

Para cada movimento de aplicação ou resgate nos comprovantes das importações
da Pluggy, o script mostra a conta, o tipo gravado (receita, despesa,
transferência), se virou transação, o total por mês e se há, na mesma conta
e no mesmo dia, uma contraparte: saída do mesmo valor ou de soma próxima,
para o resgate; entrada, para a aplicação. No fim, conclui se a hipótese se
sustenta e propõe o tratamento — sem mudar classificação nenhuma.

No terminal só saem nomes de conta, operações, categorias da Pluggy,
contagens e somas. Nada de descrição.
"""

from __future__ import annotations

import argparse
import itertools
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conversao_pluggy import _data_local
from app.models import ContaPluggy, Importacao, ImportacaoItem, Transacao
from app.pluggy.modelos import Transacao as TransacaoPluggy
from app.services.comprovante_pluggy import ler_comprovante

CENTAVO = Decimal("0.01")

#: Operações de aplicação ou resgate, pelo nome: `RESGATE_APLIC_FINANCEIRA`,
#: `APLICACAO_FINANCEIRA` e o que mais a Pluggy chamar assim.
_APLICACAO = re.compile(r"APLIC|RESGATE|INVEST")

#: Até quantas contrapartes no mesmo dia a busca por subconjunto vai. Acima
#: disso, só a soma de todas (2^12 combinações é nada; 2^30 não).
_MAX_SUBCONJUNTO = 12

#: Contraparte achada, da mais forte para a mais fraca.
#: - igual: um movimento oposto do mesmo valor;
#: - soma_proxima: um conjunto de opostos cuja soma bate, com tolerância;
#: - cobre_parte: os opostos somam mais que o movimento (resgatou só o que
#:   faltava, ou aplicou só parte do que entrou);
#: - sem_relacao: há opostos no dia, mas somam menos;
#: - sem_contraparte: nenhum movimento oposto no dia.
CONTRAPARTES = ("igual", "soma_proxima", "cobre_parte", "sem_relacao", "sem_contraparte")

#: Faixas de valor, para separar rendimento (centavos) de resgate de verdade.
FAIXAS = (
    (Decimal("1"), "< R$ 1"),
    (Decimal("10"), "R$ 1 a 10"),
    (Decimal("100"), "R$ 10 a 100"),
    (None, ">= R$ 100"),
)


def e_aplicacao(operacao: str | None) -> bool:
    return bool(_APLICACAO.search((operacao or "").upper()))


@dataclass(frozen=True, slots=True)
class Movimento:
    id: str
    conta: str
    dia: date
    #: Absoluto: o sentido está em `entrada`.
    valor: Decimal
    entrada: bool
    operacao: str | None
    categoria: str | None


def movimentos_de(transacoes: Iterable[TransacaoPluggy]) -> list[Movimento]:
    """As transações já confirmadas, no dia de São Paulo."""
    movimentos: list[Movimento] = []
    for t in transacoes:
        if t.status == "PENDING":
            continue
        movimentos.append(
            Movimento(
                id=t.id,
                conta=t.account_id,
                dia=_data_local(t.date),
                valor=abs(t.amount),
                entrada=(t.type or "").upper() == "CREDIT",
                operacao=t.operation_type,
                categoria=t.category,
            )
        )
    return movimentos


def tolerancia(valor: Decimal) -> Decimal:
    """1% do valor, no mínimo dez centavos."""
    return max(Decimal("0.10"), (valor * Decimal("0.01")).quantize(CENTAVO))


def casar(alvo: Movimento, do_dia: Sequence[Movimento]) -> str:
    """A contraparte do movimento na mesma conta e no mesmo dia (`CONTRAPARTES`)."""
    opostos = [
        m.valor
        for m in do_dia
        if m.conta == alvo.conta
        and m.dia == alvo.dia
        and m.entrada != alvo.entrada
        and m.id != alvo.id
        and not e_aplicacao(m.operacao)
    ]
    if not opostos:
        return "sem_contraparte"
    if alvo.valor in opostos:
        return "igual"
    margem = tolerancia(alvo.valor)
    soma = sum(opostos, Decimal("0"))
    if abs(soma - alvo.valor) <= margem:
        return "soma_proxima"
    if len(opostos) <= _MAX_SUBCONJUNTO:
        for tamanho in range(2, len(opostos)):
            for grupo in itertools.combinations(opostos, tamanho):
                if abs(sum(grupo, Decimal("0")) - alvo.valor) <= margem:
                    return "soma_proxima"
    if soma > alvo.valor:
        return "cobre_parte"
    return "sem_relacao"


def faixa(valor: Decimal) -> str:
    for teto, rotulo in FAIXAS:
        if teto is None or valor < teto:
            return rotulo
    return FAIXAS[-1][1]


# --------------------------------------------------------------------------
# Análise
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Gravado:
    """O que o banco daqui tem para a transação da Pluggy."""

    #: "receita", "despesa", "transferencia" ou "sem item".
    tipo: str
    status: str
    virou_transacao: bool


SEM_ITEM = Gravado(tipo="sem item", status="sem item", virou_transacao=False)


@dataclass(slots=True)
class Linha:
    movimento: Movimento
    conta: str
    gravado: Gravado
    contraparte: str


@dataclass(slots=True)
class Analise:
    linhas: list[Linha] = field(default_factory=list)

    def de(self, *, entrada: bool) -> list[Linha]:
        return [linha for linha in self.linhas if linha.movimento.entrada is entrada]

    @property
    def resgates(self) -> list[Linha]:
        return self.de(entrada=True)

    @property
    def aplicacoes(self) -> list[Linha]:
        return self.de(entrada=False)


def analisar(
    movimentos: Sequence[Movimento],
    gravados: dict[str, Gravado],
    contas: dict[str, str],
) -> Analise:
    por_dia: dict[tuple[str, date], list[Movimento]] = defaultdict(list)
    for m in movimentos:
        por_dia[(m.conta, m.dia)].append(m)
    analise = Analise()
    for m in sorted(movimentos, key=lambda x: (x.conta, x.dia, x.id)):
        if not e_aplicacao(m.operacao):
            continue
        analise.linhas.append(
            Linha(
                movimento=m,
                conta=contas.get(m.conta, "conta sem mapeamento"),
                gravado=gravados.get(m.id, SEM_ITEM),
                contraparte=casar(m, por_dia[(m.conta, m.dia)]),
            )
        )
    return analise


def concluir(analise: Analise) -> tuple[str, list[str]]:
    """Veredito e proposta, a partir das contagens. Só texto: não muda nada."""
    resgates = analise.resgates
    n = len(resgates)
    if n == 0:
        return "SEM DADOS", ["Nenhum resgate nos comprovantes: nada a concluir."]
    conta = Counter(linha.contraparte for linha in resgates)
    fortes = conta["igual"] + conta["soma_proxima"]
    # Centavos sem saída do mesmo valor não explicam pagamento nenhum, mesmo
    # num dia com saídas maiores: ficam fora do "compatível".
    pequenos = sum(
        1
        for linha in resgates
        if linha.movimento.valor < Decimal("1")
        and linha.contraparte not in ("igual", "soma_proxima")
    )
    cobre_parte = sum(
        1
        for linha in resgates
        if linha.contraparte == "cobre_parte" and linha.movimento.valor >= Decimal("1")
    )
    receita = sum(
        1 for linha in resgates if linha.gravado.tipo == "receita" and linha.gravado.virou_transacao
    )
    total = _brl(sum((linha.movimento.valor for linha in resgates), Decimal("0")))
    nota_receita = f"{receita} de {n} resgates (somando {total}) viraram transação de receita" + (
        " e hoje somam como receita nos relatórios." if receita else "."
    )

    if fortes * 2 >= n:
        return "SUSTENTA-SE", [
            f"{fortes} de {n} resgates têm saída de mesmo valor ou soma próxima no mesmo dia, "
            "na mesma conta: é o saldo aplicado voltando para cobrir o pagamento.",
            nota_receita,
            "Proposta: não contar resgate (nem aplicação) como receita ou despesa. Tratar como "
            "movimento interno — tipo transferência entre a conta e uma conta de aplicação "
            "automática, ou rejeitar na revisão como o lado do cartão no pagamento de fatura "
            "(D-05). O rendimento de fato, se a Pluggy mandar separado, fica como receita.",
        ]
    if pequenos * 2 >= n:
        return "NÃO SE SUSTENTA COMO DESCRITA", [
            f"{pequenos} de {n} resgates são de centavos e sem saída que os explique: "
            "o padrão é de rendimento creditado na conta remunerada, não de resgate para "
            "cobrir pagamento.",
            nota_receita,
            "Proposta: é receita de verdade, mas rendimento — mapear para uma subcategoria de "
            "rendimentos em Receita, separada de salário, para não se misturar com o resto. "
            "Pelo valor, não distorce os relatórios.",
        ]
    if (fortes + cobre_parte) * 2 >= n:
        return "SUSTENTA-SE EM PARTE", [
            f"{fortes} de {n} resgates casam com saída do mesmo dia; outros "
            f"{cobre_parte} são menores que as saídas do dia (resgate só do que "
            "faltava, compatível com a hipótese, mas não prova).",
            nota_receita,
            "Proposta: tratar como movimento interno os que casam, e conferir os outros no "
            "app do banco antes de decidir a regra geral.",
        ]
    return "INCONCLUSIVA", [
        f"Contrapartes: {', '.join(f'{k} {conta[k]}' for k in CONTRAPARTES if conta[k])}.",
        nota_receita,
        "Proposta: conferir alguns no app do banco antes de decidir; até lá, nada muda.",
    ]


# --------------------------------------------------------------------------
# Banco
# --------------------------------------------------------------------------


def carregar(session: Session) -> tuple[list[Movimento], dict[str, Gravado], dict[str, str]]:
    """Movimentos de todos os comprovantes da Pluggy, o que foi gravado e as contas."""
    transacoes: dict[str, TransacaoPluggy] = {}
    tipos_de_conta: dict[str, str] = {}
    for importacao in session.scalars(
        select(Importacao)
        .where(Importacao.origem == "pluggy", Importacao.deleted_em.is_(None))
        .order_by(Importacao.id)
    ):
        comprovante = ler_comprovante(importacao.arquivo_conteudo)
        transacoes.update(comprovante.transacoes)  # a mais recente vence
        for conta in comprovante.contas.values():
            tipos_de_conta[conta.id] = conta.type
    movimentos = movimentos_de(transacoes.values())

    alvos = {m.id for m in movimentos if e_aplicacao(m.operacao)}
    gravados: dict[str, Gravado] = {}
    if alvos:
        linhas = session.execute(
            select(ImportacaoItem, Transacao)
            .outerjoin(
                Transacao,
                (Transacao.id == ImportacaoItem.transacao_id) & Transacao.deleted_em.is_(None),
            )
            .where(ImportacaoItem.id_externo.in_(alvos), ImportacaoItem.deleted_em.is_(None))
            .order_by(ImportacaoItem.id)
        ).all()
        for item, transacao in linhas:
            tipo = transacao.tipo if transacao is not None else item.tipo_sugerido
            gravados[item.id_externo or ""] = Gravado(
                tipo=tipo.value if tipo is not None else "sem tipo",
                status=item.status.value,
                virou_transacao=transacao is not None,
            )

    contas: dict[str, str] = {}
    for mapa in session.scalars(select(ContaPluggy).order_by(ContaPluggy.id)):
        if mapa.deleted_em is None or mapa.pluggy_account_id not in contas:
            tipo = tipos_de_conta.get(mapa.pluggy_account_id, "?")
            contas[mapa.pluggy_account_id] = f"{mapa.conta.nome} ({tipo})"
    return movimentos, gravados, contas


# --------------------------------------------------------------------------
# Saída
# --------------------------------------------------------------------------


def _brl(valor: Decimal) -> str:
    texto = f"{valor.quantize(CENTAVO):,.2f}"
    return "R$ " + texto.replace(",", "_").replace(".", ",").replace("_", ".")


def imprimir(analise: Analise) -> None:
    print("== Aplicações e resgates nos comprovantes da Pluggy (somente leitura) ==")
    if not analise.linhas:
        print("Nenhuma operação de aplicação ou resgate nos comprovantes.")
        return

    print("\npor operação e conta:")
    por_op: Counter[tuple[str, str, str]] = Counter()
    somas: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for linha in analise.linhas:
        sentido = "entrada" if linha.movimento.entrada else "saída"
        chave = (linha.movimento.operacao or "—", sentido, linha.conta)
        por_op[chave] += 1
        somas[chave] += linha.movimento.valor
    for (operacao, sentido, conta), n in por_op.most_common():
        total = _brl(somas[(operacao, sentido, conta)])
        print(f"   {n:>4}  {operacao} ({sentido})  {conta}  total {total}")

    print("\ntipo gravado aqui x virou transação:")
    gravados = Counter(
        (
            linha.movimento.operacao or "—",
            linha.gravado.tipo,
            linha.gravado.status,
            linha.gravado.virou_transacao,
        )
        for linha in analise.linhas
    )
    for (operacao, tipo, status, virou), n in gravados.most_common():
        if status == SEM_ITEM.status:
            print(f"   {n:>4}  {operacao}: sem item no staging")
            continue
        print(
            f"   {n:>4}  {operacao}: {tipo}, item {status}, "
            f"{'virou' if virou else 'não virou'} transação"
        )

    print("\ncategoria da Pluggy:")
    for categoria, n in Counter(
        linha.movimento.categoria or "(sem categoria)" for linha in analise.linhas
    ).most_common():
        print(f"   {n:>4}  {categoria}")

    print("\nfaixa de valor:")
    for _teto, rotulo in FAIXAS:
        n = sum(1 for linha in analise.linhas if faixa(linha.movimento.valor) == rotulo)
        if n:
            print(f"   {n:>4}  {rotulo}")

    print("\ntotal por mês:")
    mensal: dict[tuple[str, str, str], list[Decimal]] = defaultdict(list)
    for linha in analise.linhas:
        mes = linha.movimento.dia.strftime("%Y-%m")
        mensal[(linha.conta, linha.movimento.operacao or "—", mes)].append(linha.movimento.valor)
    for (conta, operacao, mes), valores in sorted(mensal.items()):
        print(
            f"   {mes}  {conta}  {operacao}: {len(valores)} "
            f"somando {_brl(sum(valores, Decimal(0)))}"
        )

    for rotulo, linhas in (
        ("resgates (entradas)", analise.resgates),
        ("aplicações (saídas)", analise.aplicacoes),
    ):
        if not linhas:
            print(f"\n{rotulo}: nenhum")
            continue
        oposto = "saída" if linhas[0].movimento.entrada else "entrada"
        print(f"\n{rotulo}: contraparte ({oposto}) na mesma conta e no mesmo dia")
        contagem = Counter(linha.contraparte for linha in linhas)
        textos = {
            "igual": f"{oposto} de mesmo valor",
            "soma_proxima": f"{oposto}s de soma próxima (1%, mín. R$ 0,10)",
            "cobre_parte": f"{oposto}s maiores que o movimento",
            "sem_relacao": f"{oposto}s menores que o movimento",
            "sem_contraparte": f"nenhuma {oposto} no dia",
        }
        for contraparte in CONTRAPARTES:
            if contagem[contraparte]:
                print(f"   {contagem[contraparte]:>4}  {textos[contraparte]}")

    veredito, texto = concluir(analise)
    print(f"\nconclusão: {veredito}")
    for paragrafo in texto:
        print(f"   {paragrafo}")
    print("\nNada foi gravado.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.parse_args(argv)

    from app.db import SessionLocal

    with SessionLocal() as session:
        movimentos, gravados, contas = carregar(session)
        session.rollback()
    imprimir(analisar(movimentos, gravados, contas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
