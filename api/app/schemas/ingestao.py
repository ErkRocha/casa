"""Schemas da ingestão (fase 5)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from app.enums import StatusImportacao, StatusItem, TipoTransacao


class ImportacaoRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    arquivo_nome: str
    origem: str | None
    parser_usado: str | None
    #: `application/pdf` ou `application/json` (sync da Pluggy). A tela usa
    #: para decidir se oferece reabrir o PDF.
    arquivo_tipo: str | None = None
    periodo_inicio: date | None
    periodo_fim: date | None
    status: StatusImportacao
    total_itens: int
    itens_aprovados: int
    #: Total que o documento declara. É o gabarito da extração.
    total_declarado: Decimal | None
    #: Preenchido quando a soma não fechou ou houve linha não reconhecida.
    erro_mensagem: str | None
    criado_em: datetime
    #: Itens ainda pendentes de revisão. Só a listagem preenche.
    itens_pendentes: int = 0


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    importacao_id: int
    linha_bruta: str
    linha_num: int | None
    data: date | None
    valor: Decimal | None
    tipo_sugerido: TipoTransacao | None
    competencia_sugerida: date | None
    categoria_sugerida_id: int | None
    local_sugerido_id: int | None
    pessoa_sugerida_id: int | None
    forma_pagamento_sugerida_id: int | None
    confianca: Decimal | None
    origem_sugestao: str | None
    status: StatusItem
    transacao_id: int | None
    motivo_rejeicao: str | None
    #: Nota do parser ou da sync: possível duplicata, encargo, competência
    #: estimada. A revisão mostra junto do item.
    observacao: str | None = None
    #: Id na Pluggy; nulo para PDF.
    id_externo: str | None = None


class ContagensRevisao(BaseModel):
    """Quantos itens há em cada filtro, na importação inteira."""

    #: Status -> itens (`pendente`, `aprovado`, `rejeitado`, `duplicado`).
    por_status: dict[str, int]
    #: Entre os pendentes: `sem_categoria`, `observacao`, `transferencia`, `pronto`.
    pendentes_por_falta: dict[str, int]


class ImportacaoDetalhe(BaseModel):
    importacao: ImportacaoRead
    #: Só os itens do filtro pedido.
    itens: list[ItemRead]
    #: Soma dos itens pendentes de despesa — o que entra se aprovar tudo.
    #: Da importação inteira, não do filtro.
    total_pendente: Decimal
    #: Despesa pendente + aprovada: o que se confere contra o total declarado
    #: do documento. Da importação inteira.
    soma_lida: Decimal = Decimal("0")
    contagens: ContagensRevisao | None = None


class ItemAjuste(BaseModel):
    """Correção do usuário antes de aprovar.

    Ajustar categoria grava ou reforça uma regra, então a próxima importação
    já vem certa (D-09).
    """

    tipo_sugerido: TipoTransacao | None = None
    competencia_sugerida: date | None = None
    categoria_sugerida_id: int | None = None
    local_sugerido_id: int | None = None
    pessoa_sugerida_id: int | None = None
    forma_pagamento_sugerida_id: int | None = None


class LoteItens(BaseModel):
    ids: Annotated[list[int], Field(min_length=1, max_length=1000)]


class LoteRejeitar(LoteItens):
    motivo: str | None = None


class ResultadoAprovacao(BaseModel):
    """Duplicata não derruba o lote — vira status `duplicado` e segue."""

    promovidos: int
    duplicados: int
    erros: list[dict[str, Any]]


class ResultadoDesfazer(BaseModel):
    """Quanto o desfazer apagou (soft delete) — D-21."""

    transacoes: int
    itens: int
