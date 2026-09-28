"""Schemas do dossiê que alimenta o relatório mensal (fase 6).

Todo número aqui saiu de SQL agregado. É essa a fronteira da regra 7: o
modelo recebe este objeto pronto, serializado em JSON, e só escreve texto
sobre ele. Nada que o modelo devolva volta para cá.

Transferência fica de fora de qualquer soma de gasto — pagar fatura não é
despesa nova (D-05).
"""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class LinhaCategoria(BaseModel):
    categoria_id: int | None
    #: Categoria raiz — é o nível em que a conversa sobre orçamento acontece.
    categoria: str
    total: Decimal
    #: Fatia do gasto do mês, em pontos percentuais.
    participacao: Decimal
    transacoes: int


class GastoPorCategoria(BaseModel):
    competencia: date
    total: Decimal
    linhas: list[LinhaCategoria]


class LinhaPessoa(BaseModel):
    pessoa: str
    total: Decimal
    participacao: Decimal


class DivisaoPessoas(BaseModel):
    competencia: date
    total: Decimal
    #: `pessoa_id` nulo aparece como "Conjunto" — nunca como pessoa faltante (D-03).
    linhas: list[LinhaPessoa]


class ComparacaoCategoria(BaseModel):
    categoria: str
    atual: Decimal
    anterior: Decimal
    diferenca: Decimal
    #: Nulo quando não havia base no mês anterior — variação percentual sobre
    #: zero não é "infinito", é "não dá para comparar".
    variacao_pct: Decimal | None


class CompararPeriodos(BaseModel):
    competencia: date
    competencia_anterior: date
    total_atual: Decimal
    total_anterior: Decimal
    diferenca: Decimal
    variacao_pct: Decimal | None
    #: Média dos meses com lançamento na janela, não da janela inteira: mês
    #: zerado quase sempre significa "não importei", não "não gastei".
    media_janela: Decimal
    meses_na_media: int
    #: As maiores variações, para cima e para baixo.
    maiores_altas: list[ComparacaoCategoria]
    maiores_quedas: list[ComparacaoCategoria]


class LinhaOrcamento(BaseModel):
    categoria: str
    meta: Decimal
    realizado: Decimal
    percentual: Decimal
    #: "ok" | "atencao" | "estourado".
    situacao: str


class StatusOrcamento(BaseModel):
    competencia: date
    linhas: list[LinhaOrcamento]
    estourados: int
    #: Nenhum orçamento cadastrado é diferente de todos dentro da meta. O
    #: relatório precisa saber a diferença para não elogiar o silêncio.
    tem_orcamento: bool


class TransacaoAtipica(BaseModel):
    data: date
    descricao: str
    categoria: str
    valor: Decimal
    #: Mediana histórica da categoria, base da comparação.
    mediana_categoria: Decimal
    #: Quantos desvios absolutos medianos acima da mediana.
    desvios: Decimal


class TransacoesAtipicas(BaseModel):
    competencia: date
    linhas: list[TransacaoAtipica]
    #: Meses de histórico que sustentaram a mediana. Com poucos, o achado é
    #: fraco, e o texto tem que dizer isso.
    meses_de_base: int


class Reajuste(BaseModel):
    descricao: str
    categoria: str | None
    valor_anterior: Decimal
    valor_atual: Decimal
    diferenca: Decimal
    variacao_pct: Decimal
    meses_observados: int
    primeira_competencia: date
    ultima_competencia: date


class Reajustes(BaseModel):
    linhas: list[Reajuste]


class ResumoMensal(BaseModel):
    competencia: date
    receitas: Decimal
    despesas: Decimal
    saldo: Decimal
    transacoes: int
    #: Mês ainda em curso: os números são parciais e o texto não pode tratar
    #: o mês como fechado.
    em_curso: bool


class Cobertura(BaseModel):
    """Quanto do mês está categorizado.

    Métrica de qualidade do dado, não de finança — e mesmo assim é a primeira
    coisa que o relatório precisa saber. Análise por categoria sobre um mês
    80% sem categoria descreve os 20% e cala sobre o resto, o que é pior do
    que não analisar: parece completa.
    """

    competencia: date
    total: Decimal
    categorizado: Decimal
    sem_categoria: Decimal
    #: Percentual do valor com categoria atribuída.
    percentual: Decimal
    transacoes_sem_categoria: int


class Dossie(BaseModel):
    """Tudo que o modelo recebe. Nada além disto entra no prompt.

    O nome é literal: é uma pasta de números fechada antes de qualquer
    chamada de modelo. Se um número não está aqui, ele não pode aparecer no
    relatório — e é isso que torna cada afirmação do texto conferível.
    """

    competencia: date
    gerado_em: date
    resumo: ResumoMensal
    cobertura: Cobertura
    gasto_por_categoria: GastoPorCategoria
    divisao_pessoas: DivisaoPessoas
    comparacao: CompararPeriodos
    orcamento: StatusOrcamento
    atipicas: TransacoesAtipicas
    reajustes: Reajustes


# ---------------------------------------------------------------------------
# Saída do modelo
# ---------------------------------------------------------------------------


class RelatorioGerado(BaseModel):
    """A resposta do modelo, validada antes de virar linha no banco (regra 8).

    Structured output em vez de markdown solto porque `titulo` e `alertas`
    vão para lugares diferentes da tela, e separar isso com regex depois é
    exatamente o parse de texto livre que a regra 8 proíbe.
    """

    titulo: str = Field(min_length=3, max_length=120)
    #: Duas ou três frases: o que aconteceu no mês.
    resumo: str = Field(min_length=20)
    #: Corpo em markdown.
    analise: str = Field(min_length=50)
    #: Pontos que merecem ação, já em ordem de importância.
    alertas: list[str] = Field(default_factory=list, max_length=8)

    def como_markdown(self, competencia: date) -> str:
        partes = [f"# {self.titulo}", "", self.resumo, "", self.analise]
        if self.alertas:
            partes += ["", "## Pontos de atenção", ""]
            partes += [f"- {alerta}" for alerta in self.alertas]
        partes += ["", "---", "", f"_Competência {competencia:%m/%Y}._"]
        return "\n".join(partes)
