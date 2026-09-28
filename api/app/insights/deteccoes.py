"""Alertas que não passam por modelo nenhum.

Boa parte do que um relatório precisa dizer é decisão de limiar, não de
linguagem: orçamento estourado, assinatura reajustada, gasto fora do padrão.
Tudo isso já veio pronto do SQL (D-10) — mandar para o LLM decidir seria
trocar uma comparação exata por uma opinião.

O valor prático: `--sem-ia` gera um relatório inteiro por aqui. Se o CLI do
Claude não estiver instalado, se a chave faltar, se a rede cair, o fechamento
do mês continua saindo — mais seco, e com os mesmos números.

Função pura sobre o dossiê: sem sessão, sem I/O, sem relógio.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from app.schemas.insights import Dossie

#: Abaixo desta cobertura, análise por categoria não descreve o mês.
COBERTURA_MINIMA = Decimal("70")

#: Variação mês a mês que merece menção. Abaixo disso é ruído de calendário —
#: mês com cinco fins de semana gasta mais que um com quatro.
VARIACAO_RELEVANTE = Decimal("15")

#: Quanto acima da média da janela conta como mês caro.
ACIMA_DA_MEDIA = Decimal("20")


class Alerta(BaseModel):
    #: "orcamento" | "reajuste" | "atipico" | "cobertura" | "variacao" | "saldo".
    tipo: str
    #: "alta" | "media" | "baixa" — ordem de leitura, não de gravidade moral.
    prioridade: str
    texto: str


_ORDEM = {"alta": 0, "media": 1, "baixa": 2}


def reais(valor: Decimal) -> str:
    """Formata dinheiro em pt-BR: `R$ 1.874,77`.

    Escrito à mão em vez de `locale.currency`: o `locale` depende de o sistema
    ter `pt_BR` instalado, o que é falso no container e no Windows do usuário.
    O relatório sairia com ponto decimal em um lugar e vírgula em outro,
    dependendo da máquina que rodou.
    """
    negativo = valor < 0
    inteiro, _, centavos = f"{abs(valor):.2f}".partition(".")

    grupos: list[str] = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)

    sinal = "-" if negativo else ""
    return f"{sinal}R$ {'.'.join(grupos)},{centavos}"


def alertas_deterministicos(dossie: Dossie) -> list[Alerta]:
    """Tudo que dá para afirmar sem interpretar nada."""
    achados: list[Alerta] = []

    # --- qualidade do dado vem primeiro ------------------------------------
    # Se o mês está sem categoria, os alertas por categoria abaixo são
    # calculados sobre uma fração do gasto. Dizer isso antes evita que o
    # relatório soe completo quando não é.
    cobertura = dossie.cobertura
    if cobertura.total > 0 and cobertura.percentual < COBERTURA_MINIMA:
        achados.append(
            Alerta(
                tipo="cobertura",
                prioridade="alta",
                texto=(
                    f"{cobertura.percentual}% do gasto do mês está categorizado "
                    f"({cobertura.transacoes_sem_categoria} lançamento(s) sem categoria, "
                    f"{reais(cobertura.sem_categoria)}). A análise por categoria abaixo cobre "
                    "apenas a parte já classificada."
                ),
            )
        )

    # --- orçamento ---------------------------------------------------------
    for linha in dossie.orcamento.linhas:
        if linha.situacao == "estourado":
            achados.append(
                Alerta(
                    tipo="orcamento",
                    prioridade="alta",
                    texto=(
                        f"{linha.categoria} estourou o orçamento: {reais(linha.realizado)} "
                        f"de {reais(linha.meta)} ({linha.percentual}%)."
                    ),
                )
            )
        elif linha.situacao == "atencao":
            achados.append(
                Alerta(
                    tipo="orcamento",
                    prioridade="media",
                    texto=(
                        f"{linha.categoria} chegou a {linha.percentual}% da meta "
                        f"({reais(linha.realizado)} de {reais(linha.meta)})."
                    ),
                )
            )

    # --- reajustes ---------------------------------------------------------
    for reajuste in dossie.reajustes.linhas:
        achados.append(
            Alerta(
                tipo="reajuste",
                prioridade="alta",
                texto=(
                    f"{reajuste.descricao} subiu de {reais(reajuste.valor_anterior)} para "
                    f"{reais(reajuste.valor_atual)} (+{reajuste.variacao_pct}%) entre "
                    f"{reajuste.primeira_competencia:%m/%Y} e "
                    f"{reajuste.ultima_competencia:%m/%Y}, em "
                    f"{reajuste.meses_observados} meses observados."
                ),
            )
        )

    # --- gastos atípicos ---------------------------------------------------
    for atipica in dossie.atipicas.linhas:
        achados.append(
            Alerta(
                tipo="atipico",
                prioridade="media",
                texto=(
                    f"{atipica.descricao} ({atipica.categoria}) em "
                    f"{atipica.data:%d/%m}: {reais(atipica.valor)}, contra mediana de "
                    f"{reais(atipica.mediana_categoria)} na categoria "
                    f"({atipica.desvios} desvios)."
                ),
            )
        )

    # --- variação e saldo --------------------------------------------------
    comparacao = dossie.comparacao
    if comparacao.variacao_pct is not None and abs(comparacao.variacao_pct) >= VARIACAO_RELEVANTE:
        direcao = "acima" if comparacao.variacao_pct > 0 else "abaixo"
        achados.append(
            Alerta(
                tipo="variacao",
                prioridade="media",
                texto=(
                    f"Gasto {abs(comparacao.variacao_pct)}% {direcao} de "
                    f"{comparacao.competencia_anterior:%m/%Y}: {reais(comparacao.total_atual)} "
                    f"contra {reais(comparacao.total_anterior)}."
                ),
            )
        )

    # A média só vale como referência se houver meses suficientes por trás
    # dela. Com um mês na base, "20% acima da média" é só o mês anterior
    # repetido com outro nome.
    if comparacao.meses_na_media >= 3 and comparacao.media_janela > 0:
        distancia = (
            (comparacao.total_atual - comparacao.media_janela) / comparacao.media_janela * 100
        ).quantize(Decimal("0.1"))
        if distancia >= ACIMA_DA_MEDIA:
            achados.append(
                Alerta(
                    tipo="variacao",
                    prioridade="media",
                    texto=(
                        f"Mês {distancia}% acima da média dos últimos "
                        f"{comparacao.meses_na_media} meses "
                        f"({reais(comparacao.media_janela)})."
                    ),
                )
            )

    resumo = dossie.resumo
    if resumo.receitas > 0 and resumo.saldo < 0:
        achados.append(
            Alerta(
                tipo="saldo",
                prioridade="alta",
                texto=(
                    f"Saldo negativo em {resumo.competencia:%m/%Y}: despesas de "
                    f"{reais(resumo.despesas)} contra receitas de {reais(resumo.receitas)}."
                ),
            )
        )

    return sorted(achados, key=lambda a: _ORDEM[a.prioridade])


def relatorio_sem_ia(dossie: Dossie) -> str:
    """Markdown gerado só com os números. Nenhuma chamada de modelo.

    É o piso do fechamento do mês: seco, sem interpretação, e sempre
    disponível.
    """
    resumo = dossie.resumo
    linhas = [
        f"# Fechamento de {dossie.competencia:%m/%Y}",
        "",
        f"Despesas: **{reais(resumo.despesas)}** · Receitas: {reais(resumo.receitas)} · "
        f"Saldo: {reais(resumo.saldo)} · {resumo.transacoes} lançamentos.",
    ]
    if resumo.em_curso:
        linhas.append("")
        linhas.append("> Mês ainda em curso — os números são parciais.")

    comparacao = dossie.comparacao
    linhas += [
        "",
        "## Comparação",
        "",
        f"- Mês anterior ({comparacao.competencia_anterior:%m/%Y}): "
        f"{reais(comparacao.total_anterior)} "
        + (
            f"({comparacao.variacao_pct:+}%)"
            if comparacao.variacao_pct is not None
            else "(sem base para comparar)"
        ),
        f"- Média de {comparacao.meses_na_media} mês(es) com lançamento: "
        f"{reais(comparacao.media_janela)}",
    ]

    if dossie.gasto_por_categoria.linhas:
        linhas += ["", "## Por categoria", ""]
        linhas += [
            f"- {linha.categoria}: {reais(linha.total)} ({linha.participacao}%, "
            f"{linha.transacoes} lançamentos)"
            for linha in dossie.gasto_por_categoria.linhas
        ]

    if dossie.divisao_pessoas.linhas:
        linhas += ["", "## Por pessoa", ""]
        linhas += [
            f"- {linha.pessoa}: {reais(linha.total)} ({linha.participacao}%)"
            for linha in dossie.divisao_pessoas.linhas
        ]

    achados = alertas_deterministicos(dossie)
    if achados:
        linhas += ["", "## Pontos de atenção", ""]
        linhas += [f"- {alerta.texto}" for alerta in achados]

    linhas += ["", "---", "", "_Gerado sem modelo de linguagem — apenas SQL agregado._"]
    return "\n".join(linhas)
