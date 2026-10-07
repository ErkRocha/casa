"""O servidor MCP do chat sob demanda (D-20).

Cada tool abre a sessão **read-only** da D-11 (`sessao_leitura`) e nada mais:
não existe tool de escrita, e mesmo que existisse o Postgres recusaria. As
tools são funções parametrizadas — as de agregação de `app/insights/tools.py`
(D-10) e as consultas de `app/mcp/consultas.py` —, sem SQL livre.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.insights import tools as insights
from app.insights.db import sessao_leitura
from app.mcp import consultas
from app.schemas import insights as esquemas

INSTRUCOES = """\
Você conversa com o banco de dados financeiro de uma casa (um casal), em \
português do Brasil. As tools só leem: não existe como lançar, editar ou \
apagar nada por aqui — para isso o usuário usa o painel.

Regras:
- NÃO some, subtraia ou calcule médias por conta própria. Para totais, use \
`totalizar_transacoes` (qualquer filtro) ou as tools de agregação do mês \
(`resumo_do_mes`, `gasto_por_categoria`, `gasto_por_pessoa`, \
`comparar_com_meses_anteriores`). Os números saem do banco; você interpreta.
- Dinheiro vem como texto decimal ("1234.56"). Mostre em reais (R$ 1.234,56) \
sem arredondar.
- Mês é sempre AAAA-MM. A competência de compra no cartão é o mês da fatura, \
não o da compra.
- Para filtrar por pessoa, categoria ou conta, chame `listar_cadastros` antes \
e use os ids. Categoria raiz inclui as subcategorias.
- Transferência (pagamento de fatura, dinheiro entre contas próprias) não é \
gasto: as somas a deixam de fora.
- `buscar_transacoes` devolve no máximo 200 linhas por vez; se `ha_mais` vier \
verdadeiro, avise que a lista está incompleta em vez de concluir sobre ela.
- "Conjunto" é o gasto sem pessoa atribuída: dos dois, não de um só.
"""

_LEITURA = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

Competencia = Annotated[str, Field(description="Mês no formato AAAA-MM, por exemplo 2026-07.")]
Meses = Annotated[
    int, Field(ge=1, le=24, description="Quantos meses para trás entram na comparação (1 a 24).")
]

# Filtros de `buscar_transacoes` e `totalizar_transacoes`. No módulo, e não
# dentro da função: o SDK resolve as anotações pelos nomes globais.
DataInicio = Annotated[
    date | None, Field(description="Primeiro dia, AAAA-MM-DD (data da transação).")
]
DataFim = Annotated[date | None, Field(description="Último dia, AAAA-MM-DD, inclusive.")]
CompetenciaFiltro = Annotated[str | None, Field(description="Só este mês de competência, AAAA-MM.")]
CategoriaId = Annotated[
    int | None,
    Field(description="Id da categoria (de listar_cadastros); raiz inclui as filhas."),
]
PessoaId = Annotated[int | None, Field(description="Id da pessoa (de listar_cadastros).")]
SoConjunto = Annotated[bool, Field(description="Só o gasto conjunto, sem pessoa atribuída.")]
ContaId = Annotated[int | None, Field(description="Id da conta (de listar_cadastros).")]
Texto = Annotated[str | None, Field(description="Trecho da descrição, sem diferenciar maiúsculas.")]
ValorMin = Annotated[
    Decimal | None, Field(description="Valor mínimo, inclusive (sempre positivo).")
]
ValorMax = Annotated[Decimal | None, Field(description="Valor máximo, inclusive.")]
Tipo = Annotated[
    Literal["despesa", "receita", "transferencia"] | None,
    Field(description="despesa, receita ou transferencia."),
]

M = TypeVar("M")


def criar_servidor(
    sessao: Callable[[], AbstractContextManager[Session]] = sessao_leitura,
) -> MCPServer:
    """O servidor com todas as tools. `sessao` é a fábrica read-only (D-11)."""
    servidor = MCPServer(
        "controle-casa",
        title="Controle de Casa — finanças (somente leitura)",
        instructions=INSTRUCOES,
    )

    def ler(consulta: Callable[[Session], M]) -> M:
        """Roda a consulta na sessão read-only; erro de entrada vira ToolError."""
        try:
            with sessao() as s:
                return consulta(s)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    def mes(texto: str) -> date:
        try:
            return consultas.competencia_de(texto)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    tool = servidor.tool

    # --- agregações do mês (D-10, app/insights/tools.py) ---------------------

    @tool(annotations=_LEITURA)
    def resumo_do_mes(competencia: Competencia) -> esquemas.ResumoMensal:
        """Receitas, despesas, saldo e número de lançamentos do mês."""
        return ler(lambda s: insights.resumo_mensal(s, mes(competencia)))

    @tool(annotations=_LEITURA)
    def cobertura_de_categorias(competencia: Competencia) -> esquemas.Cobertura:
        """Quanto do gasto do mês tem categoria. Consulte antes de analisar por
        categoria: com cobertura baixa, a análise descreve só uma parte do mês."""
        return ler(lambda s: insights.cobertura_categorias(s, mes(competencia)))

    @tool(annotations=_LEITURA)
    def gasto_por_categoria(competencia: Competencia) -> esquemas.GastoPorCategoria:
        """Despesa do mês por categoria raiz, com total e participação (%)."""
        return ler(lambda s: insights.gasto_por_categoria(s, mes(competencia)))

    @tool(annotations=_LEITURA)
    def gasto_por_pessoa(competencia: Competencia) -> esquemas.DivisaoPessoas:
        """Despesa do mês por pessoa e o gasto conjunto (sem pessoa atribuída)."""
        return ler(lambda s: insights.divisao_pessoas(s, mes(competencia)))

    @tool(annotations=_LEITURA)
    def comparar_com_meses_anteriores(
        competencia: Competencia, meses: Meses = insights.JANELA_PADRAO
    ) -> esquemas.CompararPeriodos:
        """O mês contra o mês anterior e contra a média dos últimos meses, com as
        categorias que mais subiram e mais caíram."""
        return ler(lambda s: insights.comparar_periodos(s, mes(competencia), meses))

    @tool(annotations=_LEITURA)
    def status_do_orcamento(competencia: Competencia) -> esquemas.StatusOrcamento:
        """Metas de orçamento do mês contra o realizado, com as estouradas."""
        return ler(lambda s: insights.status_orcamento(s, mes(competencia)))

    @tool(annotations=_LEITURA)
    def gastos_fora_do_padrao(
        competencia: Competencia, meses_base: Meses = insights.JANELA_PADRAO
    ) -> esquemas.TransacoesAtipicas:
        """Lançamentos do mês muito acima do normal da própria categoria, com a
        mediana dela nos meses de base."""
        return ler(lambda s: insights.transacoes_atipicas(s, mes(competencia), meses_base))

    @tool(annotations=_LEITURA)
    def assinaturas_reajustadas(
        competencia: Competencia, meses: Meses = insights.JANELA_PADRAO
    ) -> esquemas.Reajustes:
        """Cobranças que se repetem todo mês e subiram de valor (assinatura
        reajustada em silêncio), com o valor anterior e o atual."""
        return ler(lambda s: insights.recorrencias_com_reajuste(s, mes(competencia), meses))

    # --- consultas (app/mcp/consultas.py) ------------------------------------------

    @tool(annotations=_LEITURA)
    def listar_cadastros() -> consultas.Cadastros:
        """Pessoas, contas, formas de pagamento e categorias, com os ids. Use para
        saber os nomes válidos e montar os filtros das outras tools."""
        return ler(consultas.listar_cadastros)

    def montar_filtro(
        data_inicio: date | None,
        data_fim: date | None,
        competencia: str | None,
        categoria_id: int | None,
        pessoa_id: int | None,
        so_conjunto: bool,
        conta_id: int | None,
        texto: str | None,
        valor_min: Decimal | None,
        valor_max: Decimal | None,
        tipo: str | None,
    ) -> consultas.FiltroTransacoes:
        return consultas.FiltroTransacoes(
            data_inicio=data_inicio,
            data_fim=data_fim,
            competencia=mes(competencia) if competencia else None,
            categoria_id=categoria_id,
            pessoa_id=pessoa_id,
            so_conjunto=so_conjunto,
            conta_id=conta_id,
            texto=texto or None,
            valor_min=valor_min,
            valor_max=valor_max,
            tipo=TipoTransacao(tipo) if tipo else None,
        )

    @tool(annotations=_LEITURA)
    def buscar_transacoes(
        data_inicio: DataInicio = None,
        data_fim: DataFim = None,
        competencia: CompetenciaFiltro = None,
        categoria_id: CategoriaId = None,
        pessoa_id: PessoaId = None,
        so_conjunto: SoConjunto = False,
        conta_id: ContaId = None,
        texto: Texto = None,
        valor_min: ValorMin = None,
        valor_max: ValorMax = None,
        tipo: Tipo = None,
        limite: Annotated[
            int,
            Field(ge=1, le=consultas.LIMITE_MAXIMO, description="Linhas por página (até 200)."),
        ] = consultas.LIMITE_PADRAO,
        offset: Annotated[int, Field(ge=0, description="Para a próxima página.")] = 0,
    ) -> consultas.ResultadoBusca:
        """Lista lançamentos com filtros combinados, mais recentes primeiro.
        Devolve no máximo 200 por chamada e diz se há mais. Para TOTAIS, use
        `totalizar_transacoes` com os mesmos filtros: não some a lista."""
        filtro = montar_filtro(
            data_inicio, data_fim, competencia, categoria_id, pessoa_id, so_conjunto,
            conta_id, texto, valor_min, valor_max, tipo,
        )  # fmt: skip
        return ler(lambda s: consultas.buscar_transacoes(s, filtro, limite, offset))

    @tool(annotations=_LEITURA)
    def totalizar_transacoes(
        data_inicio: DataInicio = None,
        data_fim: DataFim = None,
        competencia: CompetenciaFiltro = None,
        categoria_id: CategoriaId = None,
        pessoa_id: PessoaId = None,
        so_conjunto: SoConjunto = False,
        conta_id: ContaId = None,
        texto: Texto = None,
        valor_min: ValorMin = None,
        valor_max: ValorMax = None,
        tipo: Tipo = None,
    ) -> consultas.Totais:
        """Soma no banco as despesas e receitas que casam com os filtros (os mesmos
        de `buscar_transacoes`), com as quantidades. Transferências aparecem à
        parte e não contam como gasto. É a forma certa de responder "quanto"."""
        filtro = montar_filtro(
            data_inicio, data_fim, competencia, categoria_id, pessoa_id, so_conjunto,
            conta_id, texto, valor_min, valor_max, tipo,
        )  # fmt: skip
        return ler(lambda s: consultas.totalizar_transacoes(s, filtro))

    @tool(annotations=_LEITURA)
    def ler_relatorio_do_mes(competencia: Competencia) -> RelatorioDoMes:
        """O relatório mensal já gerado (texto em Markdown), se existir. Ele é
        gerado pelo usuário com `make relatorio`; aqui só se lê."""
        lido = ler(lambda s: consultas.ler_relatorio(s, mes(competencia)))
        if lido is None:
            return RelatorioDoMes(
                encontrado=False,
                relatorio=None,
                aviso=(
                    f"Não há relatório de {competencia}. Gere com: make relatorio m={competencia}"
                ),
            )
        return RelatorioDoMes(encontrado=True, relatorio=lido, aviso=None)

    return servidor


class RelatorioDoMes(BaseModel):
    encontrado: bool
    relatorio: consultas.RelatorioLido | None
    aviso: str | None
