"""Tools SQL determinísticas do agente de insights (D-10).

Cada função aqui roda uma agregação no Postgres e devolve um schema Pydantic.
Nenhuma soma acontece em Python, e nenhuma acontece no modelo (regra 7): o
LLM recebe estes objetos prontos e escreve texto sobre eles.

São escritas como funções isoladas, e não como métodos de um serviço, porque
o relatório mensal chama todas de uma vez enquanto o chat sob demanda vai
expor cada uma como tool separada. As duas formas de uso precisam da mesma
assinatura.

**SQL cru em vez de `select()` do Core** — ao contrário do resto do projeto.
Estas queries vivem de CTE, window function e percentil; montadas em Core
ficariam ilegíveis, e ilegível é onde erro de agregação se esconde. Todo
parâmetro vai por bind — nada é concatenado.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.insights import (
    Cobertura,
    ComparacaoCategoria,
    CompararPeriodos,
    DivisaoPessoas,
    Dossie,
    GastoPorCategoria,
    LinhaCategoria,
    LinhaOrcamento,
    LinhaPessoa,
    Reajuste,
    Reajustes,
    ResumoMensal,
    StatusOrcamento,
    TransacaoAtipica,
    TransacoesAtipicas,
)

ZERO = Decimal("0.00")

#: Rótulo único para transação sem categoria. Some do texto se virar string
#: vazia, e o relatório passaria a falar de um gasto anônimo sem dizer que é
#: anônimo.
SEM_CATEGORIA = "Sem categoria"

#: Janela padrão de comparação. Doze meses cobre sazonalidade (IPTU, material
#: escolar, seguro) sem virar arqueologia.
JANELA_PADRAO = 12

#: Acima disso a categoria acende amarelo no orçamento; acima de 100, vermelho.
#: Mesmo limiar da tela de analytics — dois números diferentes para "atenção"
#: fariam o relatório contradizer o painel.
LIMIAR_ATENCAO = Decimal("80")

#: Quantos desvios absolutos medianos acima da mediana tornam um gasto
#: atípico. Três é conservador de propósito: relatório que grita todo mês
#: deixa de ser lido.
DESVIOS_PARA_ATIPICO = Decimal("3")

#: Abaixo disso a categoria não tem histórico para sustentar uma mediana.
MINIMO_DE_AMOSTRAS = 5

#: E abaixo disto o histórico não tem *extensão*, só volume. Trinta compras
#: de um único mês descrevem aquele mês, não o padrão da casa: a mediana sai
#: apertada, o MAD sai minúsculo e metade da fatura vira "gasto atípico".
#: Testado com dados reais — 1 mês de base acusou 10 anomalias em 33 linhas.
MINIMO_MESES_BASE = 3

#: Uma cobrança precisa aparecer em pelo menos tantos meses para ser tratada
#: como recorrente. Com dois, qualquer coincidência de nome vira "assinatura".
MINIMO_MESES_RECORRENTE = 3

#: Variação abaixo disso não é reajuste, é arredondamento ou variação de uso.
LIMIAR_REAJUSTE = Decimal("0.02")


def somar_meses(competencia: date, meses: int) -> date:
    total = competencia.month - 1 + meses
    return date(competencia.year + total // 12, total % 12 + 1, 1)


def _pct(parte: Decimal, todo: Decimal) -> Decimal:
    if todo == 0:
        return ZERO
    return (parte / todo * 100).quantize(Decimal("0.1"))


def _variacao(atual: Decimal, anterior: Decimal) -> Decimal | None:
    """Variação percentual, ou nada quando não há base.

    Devolver zero quando o mês anterior foi zero seria mentira aritmética
    conveniente: "aumentou 0%" e "não havia com o que comparar" levam a
    conclusões opostas.
    """
    if anterior == 0:
        return None
    return ((atual - anterior) / anterior * 100).quantize(Decimal("0.1"))


def _dec(valor: object) -> Decimal:
    return Decimal(str(valor)) if valor is not None else ZERO


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


def resumo_mensal(sessao: Session, competencia: date, hoje: date | None = None) -> ResumoMensal:
    """Receita, despesa e saldo do mês."""
    hoje = hoje or date.today()
    linhas = sessao.execute(
        text("""
            SELECT tipo::text AS tipo, sum(valor) AS total, count(*) AS quantidade
            FROM vw_transacoes_completa
            WHERE competencia = :competencia
              AND tipo IN ('despesa', 'receita')
            GROUP BY tipo
        """),
        {"competencia": competencia},
    ).all()

    por_tipo = {linha.tipo: (_dec(linha.total), linha.quantidade) for linha in linhas}
    receitas = por_tipo.get("receita", (ZERO, 0))[0]
    despesas = por_tipo.get("despesa", (ZERO, 0))[0]

    return ResumoMensal(
        competencia=competencia,
        receitas=receitas,
        despesas=despesas,
        saldo=receitas - despesas,
        transacoes=sum(quantidade for _, quantidade in por_tipo.values()),
        em_curso=competencia == hoje.replace(day=1),
    )


def cobertura_categorias(sessao: Session, competencia: date) -> Cobertura:
    """Quanto do gasto do mês tem categoria atribuída.

    Roda antes de qualquer análise por categoria porque define se essa
    análise significa alguma coisa. Com cobertura baixa, o conselho útil não
    é sobre alimentação ou transporte — é "categorize o mês".
    """
    linha = sessao.execute(
        text("""
            SELECT
              coalesce(sum(valor), 0) AS total,
              coalesce(sum(valor) FILTER (WHERE categoria_id IS NOT NULL), 0) AS categorizado,
              count(*) FILTER (WHERE categoria_id IS NULL) AS sem_categoria
            FROM vw_transacoes_completa
            WHERE competencia = :competencia AND tipo = 'despesa'
        """),
        {"competencia": competencia},
    ).one()

    total = _dec(linha.total)
    categorizado = _dec(linha.categorizado)
    return Cobertura(
        competencia=competencia,
        total=total,
        categorizado=categorizado,
        sem_categoria=total - categorizado,
        percentual=_pct(categorizado, total),
        transacoes_sem_categoria=linha.sem_categoria,
    )


def gasto_por_categoria(sessao: Session, competencia: date) -> GastoPorCategoria:
    """Despesa do mês por categoria raiz.

    Agrupa na raiz, não na folha: "Alimentação 1.200" é uma frase útil num
    relatório; "Mercado 800, Restaurante 400" espalhados entre quinze linhas
    não é.
    """
    linhas = sessao.execute(
        text("""
            SELECT
              categoria_raiz_id AS categoria_id,
              coalesce(categoria_pai_nome, categoria_nome, :sem_categoria) AS categoria,
              sum(valor) AS total,
              count(*) AS quantidade
            FROM vw_transacoes_completa
            WHERE competencia = :competencia AND tipo = 'despesa'
            GROUP BY 1, 2
            ORDER BY 3 DESC
        """),
        {"competencia": competencia, "sem_categoria": SEM_CATEGORIA},
    ).all()

    total = sum((_dec(linha.total) for linha in linhas), ZERO)
    return GastoPorCategoria(
        competencia=competencia,
        total=total,
        linhas=[
            LinhaCategoria(
                categoria_id=linha.categoria_id,
                categoria=linha.categoria,
                total=_dec(linha.total),
                participacao=_pct(_dec(linha.total), total),
                transacoes=linha.quantidade,
            )
            for linha in linhas
        ],
    )


def divisao_pessoas(sessao: Session, competencia: date) -> DivisaoPessoas:
    """Quanto cada balde gastou. `pessoa_id` nulo vira "Conjunto" (D-03)."""
    linhas = sessao.execute(
        text("""
            SELECT pessoa_nome AS pessoa, sum(valor) AS total
            FROM vw_transacoes_completa
            WHERE competencia = :competencia AND tipo = 'despesa'
            GROUP BY 1
            ORDER BY 2 DESC
        """),
        {"competencia": competencia},
    ).all()

    total = sum((_dec(linha.total) for linha in linhas), ZERO)
    return DivisaoPessoas(
        competencia=competencia,
        total=total,
        linhas=[
            LinhaPessoa(
                pessoa=linha.pessoa,
                total=_dec(linha.total),
                participacao=_pct(_dec(linha.total), total),
            )
            for linha in linhas
        ],
    )


def comparar_periodos(
    sessao: Session, competencia: date, meses: int = JANELA_PADRAO, top: int = 5
) -> CompararPeriodos:
    """Mês contra mês anterior, e mês contra a média da janela."""
    anterior = somar_meses(competencia, -1)
    inicio = somar_meses(competencia, -meses)

    # Totais mensais da janela, incluindo o mês corrente.
    mensais = sessao.execute(
        text("""
            SELECT competencia, sum(valor) AS total
            FROM vw_transacoes_completa
            WHERE tipo = 'despesa'
              AND competencia >= :inicio AND competencia <= :competencia
            GROUP BY 1
        """),
        {"inicio": inicio, "competencia": competencia},
    ).all()
    por_mes = {linha.competencia: _dec(linha.total) for linha in mensais}

    total_atual = por_mes.get(competencia, ZERO)
    total_anterior = por_mes.get(anterior, ZERO)

    # Média só dos meses anteriores com lançamento: incluir o mês corrente
    # compararia o mês com ele mesmo, e incluir meses vazios mediria o quanto
    # ainda não foi importado. Mesma lógica do card de analytics — os dois
    # números aparecem lado a lado para o usuário e precisam bater.
    base_media = [total for mes, total in por_mes.items() if mes != competencia and total > 0]
    media = (
        (sum(base_media, ZERO) / len(base_media)).quantize(Decimal("0.01")) if base_media else ZERO
    )

    categorias = sessao.execute(
        text("""
            SELECT
              coalesce(categoria_pai_nome, categoria_nome, :sem_categoria) AS categoria,
              sum(valor) FILTER (WHERE competencia = :competencia) AS atual,
              sum(valor) FILTER (WHERE competencia = :anterior) AS anterior
            FROM vw_transacoes_completa
            WHERE tipo = 'despesa' AND competencia IN (:competencia, :anterior)
            GROUP BY 1
        """),
        {
            "competencia": competencia,
            "anterior": anterior,
            "sem_categoria": SEM_CATEGORIA,
        },
    ).all()

    comparacoes = [
        ComparacaoCategoria(
            categoria=linha.categoria,
            atual=_dec(linha.atual),
            anterior=_dec(linha.anterior),
            diferenca=_dec(linha.atual) - _dec(linha.anterior),
            variacao_pct=_variacao(_dec(linha.atual), _dec(linha.anterior)),
        )
        for linha in categorias
    ]
    por_diferenca = sorted(comparacoes, key=lambda c: c.diferenca, reverse=True)

    return CompararPeriodos(
        competencia=competencia,
        competencia_anterior=anterior,
        total_atual=total_atual,
        total_anterior=total_anterior,
        diferenca=total_atual - total_anterior,
        variacao_pct=_variacao(total_atual, total_anterior),
        media_janela=media,
        meses_na_media=len(base_media),
        maiores_altas=[c for c in por_diferenca if c.diferenca > 0][:top],
        maiores_quedas=[c for c in reversed(por_diferenca) if c.diferenca < 0][:top],
    )


def status_orcamento(sessao: Session, competencia: date) -> StatusOrcamento:
    """Metas do mês contra o realizado, direto da view."""
    linhas = sessao.execute(
        text("""
            SELECT categoria_nome, valor_meta, realizado, percentual
            FROM vw_orcamento_mes
            WHERE competencia = :competencia
            ORDER BY percentual DESC
        """),
        {"competencia": competencia},
    ).all()

    def situacao(percentual: Decimal) -> str:
        if percentual > 100:
            return "estourado"
        if percentual >= LIMIAR_ATENCAO:
            return "atencao"
        return "ok"

    montadas = [
        LinhaOrcamento(
            categoria=linha.categoria_nome,
            meta=_dec(linha.valor_meta),
            realizado=_dec(linha.realizado),
            percentual=_dec(linha.percentual),
            situacao=situacao(_dec(linha.percentual)),
        )
        for linha in linhas
    ]

    return StatusOrcamento(
        competencia=competencia,
        linhas=montadas,
        estourados=sum(1 for linha in montadas if linha.situacao == "estourado"),
        tem_orcamento=bool(montadas),
    )


def transacoes_atipicas(
    sessao: Session,
    competencia: date,
    meses_base: int = JANELA_PADRAO,
    desvios: Decimal = DESVIOS_PARA_ATIPICO,
) -> TransacoesAtipicas:
    """Gastos do mês muito acima do normal da própria categoria.

    Mediana e desvio absoluto mediano (MAD), não média e desvio padrão: uma
    única compra grande contamina a média e o desvio padrão ao mesmo tempo, o
    que faz o método esconder justamente o tipo de gasto que ele deveria
    achar. Com mediana, o outlier não move a régua que o mede.

    `percentile_disc` em vez de `percentile_cont`: o discreto devolve um valor
    realmente observado, no mesmo `numeric` da coluna. O contínuo interpola e
    devolve float — e dinheiro neste projeto nunca é float.

    Devolve lista vazia quando falta base. Não é falha: sem histórico não
    existe "fora do padrão", porque não existe padrão. Um relatório que
    inventa anomalias no primeiro mês perde a confiança de quem lê antes de
    ter chance de acertar. `meses_de_base` vai junto para o texto poder dizer
    por que não há achados.
    """
    inicio = somar_meses(competencia, -meses_base)

    meses_com_dados = int(
        sessao.execute(
            text("""
                SELECT count(DISTINCT competencia)
                FROM vw_transacoes_completa
                WHERE tipo = 'despesa'
                  AND categoria_raiz_id IS NOT NULL
                  AND competencia >= :inicio AND competencia < :competencia
            """),
            {"inicio": inicio, "competencia": competencia},
        ).scalar_one()
    )
    if meses_com_dados < MINIMO_MESES_BASE:
        return TransacoesAtipicas(competencia=competencia, meses_de_base=meses_com_dados, linhas=[])

    linhas = sessao.execute(
        text("""
            WITH base AS (
              SELECT
                categoria_raiz_id AS grupo,
                valor
              FROM vw_transacoes_completa
              WHERE tipo = 'despesa'
                -- Sem categoria fica de fora em vez de virar um grupo só:
                -- jogar cinema e supermercado no mesmo balde produz uma
                -- mediana que não descreve nem um nem outro, e o resultado é
                -- anomalia inventada com aparência de estatística.
                AND categoria_raiz_id IS NOT NULL
                AND competencia >= :inicio AND competencia < :competencia
            ),
            mediana AS (
              SELECT
                grupo,
                percentile_disc(0.5) WITHIN GROUP (ORDER BY valor) AS mediana,
                count(*) AS amostras
              FROM base
              GROUP BY grupo
              HAVING count(*) >= :minimo_amostras
            ),
            mad AS (
              SELECT
                b.grupo,
                percentile_disc(0.5) WITHIN GROUP (ORDER BY abs(b.valor - m.mediana)) AS mad
              FROM base b
              JOIN mediana m ON m.grupo = b.grupo
              GROUP BY b.grupo
            )
            SELECT
              t.data,
              coalesce(t.descricao, t.descricao_original, '(sem descrição)') AS descricao,
              coalesce(t.categoria_caminho, :sem_categoria) AS categoria,
              t.valor,
              m.mediana,
              round((t.valor - m.mediana) / d.mad, 1) AS desvios
            FROM vw_transacoes_completa t
            JOIN mediana m ON m.grupo = t.categoria_raiz_id
            JOIN mad d ON d.grupo = m.grupo
            WHERE t.competencia = :competencia
              AND t.tipo = 'despesa'
              -- MAD zero acontece quando quase todo lançamento da categoria
              -- tem o mesmo valor (assinatura). Dividir por ele apontaria
              -- qualquer centavo de diferença como anomalia.
              AND d.mad > 0
              AND t.valor > m.mediana + :desvios * d.mad
            ORDER BY t.valor DESC
            LIMIT 10
        """),
        {
            "competencia": competencia,
            "inicio": inicio,
            "minimo_amostras": MINIMO_DE_AMOSTRAS,
            "desvios": desvios,
            "sem_categoria": SEM_CATEGORIA,
        },
    ).all()

    return TransacoesAtipicas(
        competencia=competencia,
        meses_de_base=meses_com_dados,
        linhas=[
            TransacaoAtipica(
                data=linha.data,
                descricao=linha.descricao,
                categoria=linha.categoria,
                valor=_dec(linha.valor),
                mediana_categoria=_dec(linha.mediana),
                desvios=_dec(linha.desvios),
            )
            for linha in linhas
        ],
    )


def recorrencias_com_reajuste(
    sessao: Session,
    competencia: date,
    meses: int = JANELA_PADRAO,
    limiar: Decimal = LIMIAR_REAJUSTE,
) -> Reajustes:
    """Cobranças que se repetem todo mês e subiram de valor.

    O caso que isto pega é a assinatura que reajusta em silêncio: ninguém
    percebe R$ 19,90 virar R$ 27,90, porque o débito continua acontecendo.

    Parcelamento fica de fora (`parcela_total IS NULL`) — parcela repete por
    construção e o valor sobe quando muda de compra, não por reajuste.
    """
    inicio = somar_meses(competencia, -meses)

    linhas = sessao.execute(
        text("""
            WITH base AS (
              SELECT
                lower(btrim(coalesce(descricao, descricao_original))) AS chave,
                max(coalesce(descricao, descricao_original)) AS rotulo,
                competencia,
                sum(valor) AS valor
              FROM vw_transacoes_completa
              WHERE tipo = 'despesa'
                AND parcela_total IS NULL
                AND coalesce(descricao, descricao_original) IS NOT NULL
                AND competencia >= :inicio AND competencia <= :competencia
              GROUP BY 1, 3
            ),
            recorrentes AS (
              SELECT
                chave,
                max(rotulo) AS rotulo,
                count(*) AS meses,
                min(competencia) AS primeira,
                max(competencia) AS ultima
              FROM base
              GROUP BY chave
              HAVING count(*) >= :minimo_meses
            )
            SELECT
              r.rotulo AS descricao,
              r.meses,
              r.primeira,
              r.ultima,
              p.valor AS valor_anterior,
              u.valor AS valor_atual,
              (
                SELECT max(coalesce(t.categoria_caminho, :sem_categoria))
                FROM vw_transacoes_completa t
                WHERE lower(btrim(coalesce(t.descricao, t.descricao_original))) = r.chave
                  AND t.competencia = r.ultima
              ) AS categoria
            FROM recorrentes r
            JOIN base p ON p.chave = r.chave AND p.competencia = r.primeira
            JOIN base u ON u.chave = r.chave AND u.competencia = r.ultima
            WHERE u.valor > p.valor * (1 + :limiar)
            ORDER BY (u.valor - p.valor) DESC
            LIMIT 10
        """),
        {
            "competencia": competencia,
            "inicio": inicio,
            "minimo_meses": MINIMO_MESES_RECORRENTE,
            "limiar": limiar,
            "sem_categoria": SEM_CATEGORIA,
        },
    ).all()

    return Reajustes(
        linhas=[
            Reajuste(
                descricao=linha.descricao,
                categoria=linha.categoria,
                valor_anterior=_dec(linha.valor_anterior),
                valor_atual=_dec(linha.valor_atual),
                diferenca=_dec(linha.valor_atual) - _dec(linha.valor_anterior),
                variacao_pct=_variacao(_dec(linha.valor_atual), _dec(linha.valor_anterior)) or ZERO,
                meses_observados=linha.meses,
                primeira_competencia=linha.primeira,
                ultima_competencia=linha.ultima,
            )
            for linha in linhas
        ]
    )


def montar_dossie(
    sessao: Session,
    competencia: date,
    meses: int = JANELA_PADRAO,
    hoje: date | None = None,
) -> Dossie:
    """Roda todas as tools e devolve a pasta fechada que vai para o modelo.

    O relatório mensal chama tudo de uma vez em vez de deixar o modelo
    escolher tools. Parece menos elegante que um loop de tool-calling e é
    mais defensável: o conjunto de números fica idêntico entre execuções, o
    dossiê inteiro é gravado junto do texto, e o modelo não pode alegar ter
    considerado algo que não recebeu. O tool-calling volta a fazer sentido no
    chat sob demanda, onde a pergunta é imprevisível.
    """
    return Dossie(
        competencia=competencia,
        gerado_em=hoje or date.today(),
        resumo=resumo_mensal(sessao, competencia, hoje),
        cobertura=cobertura_categorias(sessao, competencia),
        gasto_por_categoria=gasto_por_categoria(sessao, competencia),
        divisao_pessoas=divisao_pessoas(sessao, competencia),
        comparacao=comparar_periodos(sessao, competencia, meses),
        orcamento=status_orcamento(sessao, competencia),
        atipicas=transacoes_atipicas(sessao, competencia, meses),
        reajustes=recorrencias_com_reajuste(sessao, competencia, meses),
    )
