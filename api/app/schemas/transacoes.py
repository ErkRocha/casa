"""Schemas de transação.

`TransacaoRead` espelha `vw_transacoes_completa`: nome de categoria, pessoa,
local e forma de pagamento já resolvidos por join, para o front desenhar sem
uma segunda volta ao servidor.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.enums import TipoPagamento, TipoTransacao

Dinheiro = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]

#: Balde de pessoa como o front manda: id numérico ou a string `conjunto`.
#: Nulo no banco significa conjunto (D-03) e URL não carrega NULL.
BaldePessoa = Literal["conjunto"] | int


class TransacaoCreate(BaseModel):
    data: date
    #: Opcional: sem ela, o service usa o mês de `data`. Compra de 28/07 que
    #: cai na fatura de agosto manda `competencia=2026-08-01` (D-02).
    competencia: date | None = None
    #: Sempre positivo; o sinal vem de `tipo`.
    valor: Annotated[Dinheiro, Field(gt=0)]
    tipo: TipoTransacao = TipoTransacao.DESPESA
    descricao: Annotated[str, Field(min_length=1, max_length=500)]
    #: Texto cru do extrato. Uma vez gravado, o banco recusa alteração.
    descricao_original: str | None = None

    #: **Nulo = gasto conjunto**, e não "esqueci de preencher".
    pessoa_id: int | None = None
    categoria_id: int | None = None
    forma_pagamento_id: int | None = None
    conta_id: int | None = None
    local_id: int | None = None

    conta_origem_id: int | None = None
    conta_destino_id: int | None = None

    parcela_num: Annotated[int, Field(ge=1)] | None = None
    parcela_total: Annotated[int, Field(ge=1)] | None = None
    grupo_parcelamento_id: UUID | None = None

    desconto_total: Annotated[Dinheiro, Field(ge=0)] = Decimal("0")
    observacao: str | None = None

    @model_validator(mode="after")
    def _valida_transferencia(self) -> "TransacaoCreate":
        """Mesma regra do check do banco, adiantada para virar 422 legível.

        O banco continua sendo a autoridade — isto aqui é só a mensagem de
        erro decente.
        """
        if self.tipo is TipoTransacao.TRANSFERENCIA:
            if self.conta_origem_id is None or self.conta_destino_id is None:
                raise ValueError("transferência exige conta de origem e destino")
            if self.conta_origem_id == self.conta_destino_id:
                raise ValueError("origem e destino da transferência não podem ser a mesma conta")
            if self.categoria_id is not None:
                raise ValueError("transferência não tem categoria")
        elif self.conta_origem_id is not None or self.conta_destino_id is not None:
            raise ValueError("origem e destino só valem para transferência")

        if (self.parcela_num is None) != (self.parcela_total is None):
            raise ValueError("parcela_num e parcela_total andam juntos")
        if (
            self.parcela_num is not None
            and self.parcela_total is not None
            and self.parcela_num > self.parcela_total
        ):
            raise ValueError("parcela_num não pode passar de parcela_total")

        return self


class TransacaoUpdate(BaseModel):
    """Patch parcial.

    `descricao_original` não está aqui de propósito: é imutável (regra 11), e
    o banco recusa a alteração com trigger. Edição do usuário vai em
    `descricao`.
    """

    data: date | None = None
    competencia: date | None = None
    valor: Annotated[Dinheiro, Field(gt=0)] | None = None
    descricao: Annotated[str, Field(min_length=1, max_length=500)] | None = None

    #: Sentinela: para mandar "vira conjunto" é preciso distinguir `null`
    #: explícito de campo ausente. Ver `TransacaoUpdate.model_fields_set`.
    pessoa_id: int | None = None
    categoria_id: int | None = None
    forma_pagamento_id: int | None = None
    conta_id: int | None = None
    local_id: int | None = None

    desconto_total: Annotated[Dinheiro, Field(ge=0)] | None = None
    observacao: str | None = None


class TransacaoRead(BaseModel):
    """Uma linha de `vw_transacoes_completa`."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    data: date
    competencia: date
    valor: Decimal
    tipo: TipoTransacao
    descricao: str
    descricao_original: str | None
    observacao: str | None
    parcela_num: int | None
    parcela_total: int | None
    desconto_total: Decimal
    criado_em: datetime
    atualizado_em: datetime | None

    #: Nulo = conjunto. `pessoa_nome` já vem com o rótulo "Conjunto".
    pessoa_id: int | None
    pessoa_nome: str

    categoria_id: int | None
    categoria_nome: str | None
    categoria_pai_id: int | None
    categoria_pai_nome: str | None
    #: "Alimentação › Mercado", pronto para a tabela.
    categoria_caminho: str | None
    #: Raiz da categoria — é por ela que o gráfico agrupa e colore.
    categoria_raiz_id: int | None

    forma_pagamento_id: int | None
    forma_pagamento_apelido: str | None
    forma_pagamento_tipo: TipoPagamento | None

    local_id: int | None
    local_nome: str | None

    conta_id: int | None
    conta_origem_id: int | None
    conta_destino_id: int | None

    # -- origem ------------------------------------------------------------
    #
    # De qual arquivo importado esta linha nasceu. Nulo em lançamento
    # digitado à mão, que é informação e não ausência: distingue "eu digitei
    # isto" de "isto veio da fatura", e é a diferença entre poder e não poder
    # conferir contra um comprovante.

    importacao_id: int | None = None
    importacao_arquivo: str | None = None
    importacao_em: datetime | None = None
    #: Há PDF para abrir. Falso em dois casos que só `importacao_id` separa:
    #: lançamento digitado à mão (nunca houve arquivo) e importação anterior à
    #: migration 0004 (houve, mas não foi guardado). Quem lê deve checar
    #: `importacao_id` primeiro — é o que a tela faz para não oferecer um link
    #: que daria 404.
    importacao_tem_arquivo: bool | None = None


class TotaisPeriodo(BaseModel):
    """Rodapé da tabela: o total do período filtrado, quebrado por balde.

    Os três baldes somam o total exato, sem sobreposição (D-03).
    Transferências ficam fora.
    """

    total_despesa: Decimal
    total_receita: Decimal
    #: Receita menos despesa. Negativo quando se gastou mais do que entrou.
    resultado: Decimal
    por_balde: dict[str, Decimal]


class TransacaoListagem(BaseModel):
    items: list[TransacaoRead]
    total: int
    limit: int
    offset: int
    totais: TotaisPeriodo


class LoteAtribuir(BaseModel):
    """Ação em lote da tela de transações."""

    ids: Annotated[list[int], Field(min_length=1, max_length=500)]
    categoria_id: int | None = None
    #: `"conjunto"` limpa o dono; um id atribui a uma pessoa.
    pessoa: BaldePessoa | None = None

    @model_validator(mode="after")
    def _pelo_menos_um_campo(self) -> "LoteAtribuir":
        if self.categoria_id is None and self.pessoa is None:
            raise ValueError("informe categoria_id, pessoa, ou os dois")
        return self


class LoteExcluir(BaseModel):
    ids: Annotated[list[int], Field(min_length=1, max_length=500)]


class TransacaoFiltros(BaseModel):
    """Filtros combináveis da listagem.

    Compartilhados com a tela de Analytics (fase 4) — os dois lados mandam o
    mesmo conjunto de parâmetros, e a agregação acontece no banco (D-14).
    """

    data_inicio: date | None = None
    data_fim: date | None = None
    competencia_inicio: date | None = None
    competencia_fim: date | None = None
    #: Aceita id de raiz ou de folha; o filtro resolve a hierarquia.
    categoria_ids: list[int] = []
    pessoa: BaldePessoa | None = None
    forma_pagamento_ids: list[int] = []
    tipos: list[TipoTransacao] = []
    local: str | None = None
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    #: Busca em descrição, local e categoria.
    texto: str | None = None


def transacao_filtros(
    data_inicio: Annotated[date | None, Query()] = None,
    data_fim: Annotated[date | None, Query()] = None,
    competencia_inicio: Annotated[date | None, Query()] = None,
    competencia_fim: Annotated[date | None, Query()] = None,
    categoria_ids: Annotated[list[int] | None, Query()] = None,
    pessoa: Annotated[str | None, Query(description="id da pessoa ou 'conjunto'")] = None,
    forma_pagamento_ids: Annotated[list[int] | None, Query()] = None,
    tipos: Annotated[list[TipoTransacao] | None, Query()] = None,
    local: Annotated[str | None, Query()] = None,
    valor_min: Annotated[Decimal | None, Query(ge=0)] = None,
    valor_max: Annotated[Decimal | None, Query(ge=0)] = None,
    texto: Annotated[str | None, Query(max_length=200)] = None,
) -> TransacaoFiltros:
    """Dependência de filtro, compartilhada por transações e analytics."""
    balde: BaldePessoa | None = None
    if pessoa is not None and pessoa != "":
        balde = "conjunto" if pessoa == "conjunto" else int(pessoa)

    return TransacaoFiltros(
        data_inicio=data_inicio,
        data_fim=data_fim,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
        categoria_ids=categoria_ids or [],
        pessoa=balde,
        forma_pagamento_ids=forma_pagamento_ids or [],
        tipos=tipos or [],
        local=local,
        valor_min=valor_min,
        valor_max=valor_max,
        texto=texto,
    )
