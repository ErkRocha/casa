"""Agregações da tela de Analytics (fase 4).

Tudo soma no banco. O front recebe pronto e desenha (D-14) — nenhuma linha de
transação chega aqui em memória para ser somada em Python.

**Regra de ouro**: `tipo = 'transferencia'` fica fora de todo cálculo de
gasto. Pagar fatura não é despesa nova (D-05).
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Text, and_, cast, func, select
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.models import Categoria, Pessoa
from app.schemas.analytics import (
    AnalyticsResumo,
    CategoriaPai,
    Comparativo,
    ComposicaoCategoria,
    DivisaoPessoas,
    EvolucaoMensal,
    LinhaComparativo,
    LinhaComposicao,
    LinhaOrcamento,
    LinhaPessoa,
    PontoMensal,
    ProgressoOrcamento,
)
from app.schemas.transacoes import TransacaoFiltros
from app.services.base import RegraViolada
from app.services.cadastros import primeiro_dia_do_mes
from app.services.transacoes import BALDE_CONJUNTO, montar_filtros
from app.views import vw_orcamento_mes as VO
from app.views import vw_transacoes_completa as V

ZERO = Decimal("0.00")

#: Acima disso a categoria acende amarelo; acima de 100 acende vermelho.
LIMIAR_ATENCAO = Decimal("80")

#: Quantos meses a evolução mensal mostra quando o filtro não diz outra coisa.
JANELA_MESES = 12


def _so_despesa() -> ColumnElement[bool]:
    return V.c.tipo == TipoTransacao.DESPESA


def _mes_anterior(competencia: date) -> date:
    if competencia.month == 1:
        return date(competencia.year - 1, 12, 1)
    return date(competencia.year, competencia.month - 1, 1)


def _somar_meses(competencia: date, meses: int) -> date:
    total = competencia.month - 1 + meses
    return date(competencia.year + total // 12, total % 12 + 1, 1)


def _media_mensal(totais: Iterable[Decimal]) -> Decimal:
    """Média de um gasto mensal, ignorando meses sem lançamento.

    Existe uma função só para isto porque a linha tracejada do gráfico e o
    card "Média dos últimos N meses" precisam bater — e é fácil não baterem.
    Dividir pela janela inteira (12) num sistema com dois meses importados dá
    uma média sete vezes menor que a do card, e a tela passa a mostrar dois
    números diferentes para a mesma coisa.

    Mês zerado no gráfico quase sempre é "ainda não importei", não "não
    gastei" — daí ele ficar fora da conta.
    """
    com_gasto = [t for t in totais if t > 0]
    if not com_gasto:
        return ZERO
    return (sum(com_gasto, ZERO) / len(com_gasto)).quantize(Decimal("0.01"))


class AnalyticsService:
    def __init__(self, session: Session, hoje: date | None = None) -> None:
        self.session = session
        #: Injetável para o teste não depender do relógio.
        self.hoje = hoje or date.today()

    # ------------------------------------------------------------------
    # Baldes de pessoa
    # ------------------------------------------------------------------

    def _pessoas_do_casal(self) -> tuple[Pessoa, Pessoa]:
        """As duas pessoas individuais, na ordem de cadastro.

        O modelo é explicitamente doméstico, de um casal: dois baldes
        individuais mais o conjunto, que somam o total exato (D-03). Uma
        terceira pessoa não é um caso previsto — em vez de dissolver o gasto
        dela em silêncio, falhamos alto.
        """
        pessoas = list(
            self.session.scalars(
                select(Pessoa)
                .where(Pessoa.deleted_em.is_(None), Pessoa.ativo.is_(True))
                .order_by(Pessoa.id)
            )
        )
        if len(pessoas) < 2:
            raise RegraViolada(
                "O painel de Analytics precisa das duas pessoas cadastradas. "
                "Rode `make seed` ou cadastre-as em /pessoas."
            )
        if len(pessoas) > 2:
            nomes = ", ".join(p.nome for p in pessoas)
            raise RegraViolada(
                "O painel de Analytics assume duas pessoas mais o balde conjunto, "
                f"e há {len(pessoas)} pessoas ativas ({nomes}). Desative as extras "
                "ou reveja o modelo antes de seguir — somar três baldes individuais "
                "mudaria o significado dos gráficos."
            )
        return pessoas[0], pessoas[1]

    # ------------------------------------------------------------------
    # Evolução mensal
    # ------------------------------------------------------------------

    def evolucao_mensal(self, filtros: TransacaoFiltros) -> EvolucaoMensal:
        pessoa_a, pessoa_b = self._pessoas_do_casal()
        where = montar_filtros(filtros)

        linhas = self.session.execute(
            select(
                V.c.competencia,
                func.coalesce(func.sum(V.c.valor).filter(V.c.pessoa_id == pessoa_a.id), 0).label(
                    "pessoa_a"
                ),
                func.coalesce(func.sum(V.c.valor).filter(V.c.pessoa_id == pessoa_b.id), 0).label(
                    "pessoa_b"
                ),
                func.coalesce(func.sum(V.c.valor).filter(V.c.pessoa_id.is_(None)), 0).label(
                    "conjunto"
                ),
                func.coalesce(func.sum(V.c.valor), 0).label("total"),
            )
            .where(and_(True, *where, _so_despesa()))
            .group_by(V.c.competencia)
            .order_by(V.c.competencia)
        ).all()

        por_competencia = {linha.competencia: linha for linha in linhas}
        competencia_atual = primeiro_dia_do_mes(self.hoje)

        # Preenche mês vazio com zero para o eixo não pular buraco. Isso é
        # geometria do gráfico, não conta de dinheiro — os valores todos vêm
        # do SELECT acima.
        meses = self._janela_de_meses(filtros, list(por_competencia))

        pontos: list[PontoMensal] = []
        for mes in meses:
            linha = por_competencia.get(mes)
            pontos.append(
                PontoMensal(
                    competencia=mes,
                    pessoa_a=Decimal(linha.pessoa_a) if linha else ZERO,
                    pessoa_b=Decimal(linha.pessoa_b) if linha else ZERO,
                    conjunto=Decimal(linha.conjunto) if linha else ZERO,
                    total=Decimal(linha.total) if linha else ZERO,
                    em_curso=mes == competencia_atual,
                )
            )

        return EvolucaoMensal(
            pontos=pontos,
            media_total=_media_mensal(p.total for p in pontos),
            rotulo_a=pessoa_a.nome,
            rotulo_b=pessoa_b.nome,
        )

    def _janela_de_meses(self, filtros: TransacaoFiltros, presentes: Sequence[date]) -> list[date]:
        """Meses do eixo X.

        Com filtro de competência, respeita o intervalo pedido. Sem ele, mostra
        os últimos 12 meses terminando no mês corrente.
        """
        if filtros.competencia_inicio is not None and filtros.competencia_fim is not None:
            inicio = primeiro_dia_do_mes(filtros.competencia_inicio)
            fim = primeiro_dia_do_mes(filtros.competencia_fim)
        elif presentes:
            fim = max(max(presentes), primeiro_dia_do_mes(self.hoje))
            inicio = _somar_meses(fim, -(JANELA_MESES - 1))
        else:
            fim = primeiro_dia_do_mes(self.hoje)
            inicio = _somar_meses(fim, -(JANELA_MESES - 1))

        meses: list[date] = []
        atual = inicio
        # Trava de segurança: um filtro absurdo não vira 10 mil colunas.
        while atual <= fim and len(meses) < 120:
            meses.append(atual)
            atual = _somar_meses(atual, 1)
        return meses

    # ------------------------------------------------------------------
    # Composição por categoria
    # ------------------------------------------------------------------

    def composicao_categoria(
        self, filtros: TransacaoFiltros, categoria_pai_id: int | None = None
    ) -> ComposicaoCategoria:
        where = montar_filtros(filtros)

        chave_id: ColumnElement[Any]
        chave_nome: ColumnElement[Any]
        escopo: list[ColumnElement[bool]]

        if categoria_pai_id is None:
            # Nível raiz: agrupa pela raiz da hierarquia.
            chave_id = V.c.categoria_raiz_id
            chave_nome = func.coalesce(V.c.categoria_pai_nome, V.c.categoria_nome)
            escopo = [V.c.categoria_id.isnot(None)]
        else:
            # Drill-down: só as filhas do pai escolhido.
            chave_id = V.c.categoria_id
            chave_nome = V.c.categoria_nome
            escopo = [V.c.categoria_raiz_id == categoria_pai_id]

        linhas = self.session.execute(
            select(
                chave_id.label("categoria_id"),
                chave_nome.label("nome"),
                func.sum(V.c.valor).label("valor"),
            )
            .where(and_(True, *where, *escopo, _so_despesa()))
            .group_by(chave_id, chave_nome)
            .order_by(func.sum(V.c.valor).desc())
        ).all()

        total = sum((Decimal(linha.valor) for linha in linhas), ZERO)
        cores = self._cores_por_categoria([linha.categoria_id for linha in linhas])
        com_filhos = self._categorias_com_filhos([linha.categoria_id for linha in linhas])

        pai = None
        if categoria_pai_id is not None:
            categoria = self.session.get(Categoria, categoria_pai_id)
            if categoria is None:
                raise RegraViolada(f"Categoria {categoria_pai_id} não existe.")
            pai = CategoriaPai(categoria_id=categoria.id, nome=categoria.nome)

        return ComposicaoCategoria(
            categoria_pai=pai,
            total_nivel=total,
            linhas=[
                LinhaComposicao(
                    categoria_id=linha.categoria_id,
                    nome=linha.nome,
                    cor=cores.get(linha.categoria_id),
                    valor=Decimal(linha.valor),
                    percentual=(
                        (Decimal(linha.valor) / total * 100).quantize(Decimal("0.1"))
                        if total
                        else ZERO
                    ),
                    # No drill-down nunca há mais um nível: a hierarquia para em 2.
                    tem_filhos=categoria_pai_id is None and linha.categoria_id in com_filhos,
                )
                for linha in linhas
            ],
        )

    def _cores_por_categoria(self, ids: Sequence[int]) -> dict[int, str | None]:
        if not ids:
            return {}
        linhas = self.session.execute(
            select(Categoria.id, Categoria.cor).where(Categoria.id.in_(ids))
        ).all()
        return {linha.id: linha.cor for linha in linhas}

    def _categorias_com_filhos(self, ids: Sequence[int]) -> set[int]:
        if not ids:
            return set()
        return set(
            self.session.scalars(
                select(Categoria.categoria_pai_id)
                .where(
                    Categoria.categoria_pai_id.in_(ids),
                    Categoria.deleted_em.is_(None),
                )
                .distinct()
            )
        )

    # ------------------------------------------------------------------
    # Divisão entre pessoas
    # ------------------------------------------------------------------

    def divisao_pessoas(
        self, filtros: TransacaoFiltros, competencia: date | None = None
    ) -> DivisaoPessoas:
        pessoa_a, pessoa_b = self._pessoas_do_casal()
        mes = primeiro_dia_do_mes(competencia or self.hoje)
        anterior = _mes_anterior(mes)

        # O painel é sempre de um mês só: o recorte de competência do filtro
        # geral não se aplica aqui, mas categoria, pagamento e texto sim.
        base = filtros.model_copy(
            update={"competencia_inicio": None, "competencia_fim": None, "pessoa": None}
        )
        where = montar_filtros(base)

        balde = func.coalesce(cast(V.c.pessoa_id, Text), BALDE_CONJUNTO).label("balde")
        linhas = self.session.execute(
            select(
                balde,
                V.c.competencia,
                func.sum(V.c.valor).label("total"),
            )
            .where(and_(True, *where, _so_despesa(), V.c.competencia.in_([mes, anterior])))
            .group_by(balde, V.c.competencia)
        ).all()

        totais: dict[tuple[str, date], Decimal] = {
            (linha.balde, linha.competencia): Decimal(linha.total) for linha in linhas
        }

        baldes = [
            (str(pessoa_a.id), pessoa_a.nome),
            (str(pessoa_b.id), pessoa_b.nome),
            (BALDE_CONJUNTO, "Conjunto"),
        ]
        total_mes = sum((totais.get((chave, mes), ZERO) for chave, _ in baldes), ZERO)

        return DivisaoPessoas(
            competencia=mes,
            total=total_mes,
            linhas=[
                LinhaPessoa(
                    balde=chave,
                    nome=nome,
                    valor=totais.get((chave, mes), ZERO),
                    percentual=(
                        (totais.get((chave, mes), ZERO) / total_mes * 100).quantize(Decimal("0.1"))
                        if total_mes
                        else ZERO
                    ),
                    valor_anterior=totais.get((chave, anterior), ZERO),
                )
                for chave, nome in baldes
            ],
        )

    # ------------------------------------------------------------------
    # Orçamento do mês
    # ------------------------------------------------------------------

    def orcamento(self, competencia: date | None = None) -> ProgressoOrcamento:
        mes = primeiro_dia_do_mes(competencia or self.hoje)

        linhas = self.session.execute(
            select(VO).where(VO.c.competencia == mes).order_by(VO.c.percentual.desc())
        ).all()

        dias_no_mes = calendar.monthrange(mes.year, mes.month)[1]
        if mes == primeiro_dia_do_mes(self.hoje):
            fracao = Decimal(self.hoje.day) / Decimal(dias_no_mes)
        else:
            # Mês fechado: o ritmo esperado já é 100%.
            fracao = Decimal("1") if mes < primeiro_dia_do_mes(self.hoje) else ZERO

        return ProgressoOrcamento(
            competencia=mes,
            fracao_decorrida=fracao.quantize(Decimal("0.001")),
            linhas=[
                LinhaOrcamento(
                    categoria_id=linha.categoria_id,
                    nome=linha.categoria_nome,
                    realizado=Decimal(linha.realizado),
                    meta=Decimal(linha.valor_meta),
                    percentual=Decimal(linha.percentual),
                    status=self._status_orcamento(Decimal(linha.percentual)),
                )
                for linha in linhas
            ],
        )

    @staticmethod
    def _status_orcamento(percentual: Decimal) -> str:
        if percentual > 100:
            return "estourado"
        if percentual >= LIMIAR_ATENCAO:
            return "atencao"
        return "ok"

    # ------------------------------------------------------------------
    # Comparativo entre períodos
    # ------------------------------------------------------------------

    def comparativo(self, filtros: TransacaoFiltros) -> Comparativo:
        mes = primeiro_dia_do_mes(self.hoje)
        anterior = _mes_anterior(mes)
        inicio_janela = _somar_meses(mes, -(JANELA_MESES - 1))

        base = filtros.model_copy(update={"competencia_inicio": None, "competencia_fim": None})
        where = montar_filtros(base)

        total_mes = self._total_competencia(where, mes)
        total_anterior = self._total_competencia(where, anterior)

        # Média mensal da janela: soma por competência primeiro, média depois.
        # `avg(sum(...))` precisa da subquery — agregado sobre agregado não
        # existe num nível só.
        por_mes = (
            select(func.sum(V.c.valor).label("total"))
            .where(
                and_(
                    True,
                    *where,
                    _so_despesa(),
                    V.c.competencia >= inicio_janela,
                    V.c.competencia <= mes,
                )
            )
            .group_by(V.c.competencia)
            .subquery()
        )
        media_12m = self.session.scalar(
            select(func.coalesce(func.avg(por_mes.c.total), 0)).select_from(por_mes)
        )
        media = Decimal(media_12m or 0).quantize(Decimal("0.01"))

        return Comparativo(
            linhas=[
                LinhaComparativo(
                    chave="mes_atual",
                    label=f"Este mês ({_rotulo_mes(mes)})",
                    valor=total_mes,
                    valor_base=total_anterior or None,
                    base_label="vs. mês anterior" if total_anterior else None,
                ),
                LinhaComparativo(
                    chave="mes_anterior",
                    label=f"Mês anterior ({_rotulo_mes(anterior)})",
                    valor=total_anterior,
                    valor_base=media or None,
                    base_label=f"vs. média de {JANELA_MESES} meses" if media else None,
                ),
                LinhaComparativo(
                    chave="media_12m",
                    label=f"Média dos últimos {JANELA_MESES} meses",
                    valor=media,
                    valor_base=None,
                    base_label=None,
                ),
            ]
        )

    def _total_competencia(self, where: list[ColumnElement[bool]], competencia: date) -> Decimal:
        total = self.session.scalar(
            select(func.coalesce(func.sum(V.c.valor), 0)).where(
                and_(True, *where, _so_despesa(), V.c.competencia == competencia)
            )
        )
        return Decimal(total or 0)

    # ------------------------------------------------------------------
    # Resumo
    # ------------------------------------------------------------------

    def resumo(
        self, filtros: TransacaoFiltros, categoria_pai_id: int | None = None
    ) -> AnalyticsResumo:
        """Os cinco painéis numa chamada só."""
        return AnalyticsResumo(
            evolucao_mensal=self.evolucao_mensal(filtros),
            composicao_categoria=self.composicao_categoria(filtros, categoria_pai_id),
            divisao_pessoas=self.divisao_pessoas(filtros),
            orcamento=self.orcamento(),
            comparativo=self.comparativo(filtros),
        )


_MESES = [
    "",
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]


def _rotulo_mes(competencia: date) -> str:
    return f"{_MESES[competencia.month]}/{competencia.year}"
