"""Schemas dos cadastros do v1.

Padrão por recurso: `XCreate` (entrada), `XUpdate` (patch parcial) e `XRead`
(saída). Nenhum deles aceita `id`, `criado_em` ou `deleted_em` na entrada —
esses são do banco.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.enums import TipoConta, TipoPagamento, TipoPessoa, TipoTransacao

Nome = Annotated[str, Field(min_length=1, max_length=200)]
#: Dinheiro sempre com 2 casas. Decimal, nunca float.
Dinheiro = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    criado_em: datetime
    atualizado_em: datetime | None = None


# --------------------------------------------------------------------------
# Pessoas
# --------------------------------------------------------------------------


class PessoaCreate(BaseModel):
    nome: Nome
    tipo: TipoPessoa = TipoPessoa.INDIVIDUAL
    ativo: bool = True


class PessoaUpdate(BaseModel):
    nome: Nome | None = None
    tipo: TipoPessoa | None = None
    ativo: bool | None = None


class PessoaRead(_Read):
    nome: str
    tipo: TipoPessoa
    ativo: bool


# --------------------------------------------------------------------------
# Contas
# --------------------------------------------------------------------------


class ContaCreate(BaseModel):
    nome: Nome
    tipo: TipoConta
    #: Nulo = conta conjunta.
    titular_id: int | None = None
    saldo_inicial: Dinheiro = Decimal("0")
    ativo: bool = True


class ContaUpdate(BaseModel):
    nome: Nome | None = None
    tipo: TipoConta | None = None
    titular_id: int | None = None
    saldo_inicial: Dinheiro | None = None
    ativo: bool | None = None


class ContaRead(_Read):
    nome: str
    tipo: TipoConta
    titular_id: int | None
    saldo_inicial: Decimal
    ativo: bool


# --------------------------------------------------------------------------
# Categorias
# --------------------------------------------------------------------------


class CategoriaCreate(BaseModel):
    nome: Nome
    tipo: TipoTransacao
    #: Nulo = categoria raiz. O banco recusa mais de 2 níveis.
    categoria_pai_id: int | None = None
    cor: str | None = Field(default=None, max_length=32)
    ativo: bool = True


class CategoriaUpdate(BaseModel):
    nome: Nome | None = None
    tipo: TipoTransacao | None = None
    categoria_pai_id: int | None = None
    cor: str | None = Field(default=None, max_length=32)
    ativo: bool | None = None


class CategoriaRead(_Read):
    nome: str
    tipo: TipoTransacao
    categoria_pai_id: int | None
    cor: str | None
    ativo: bool


class CategoriaArvore(CategoriaRead):
    """Categoria raiz com as filhas embutidas — é o que a tela de filtro usa."""

    subcategorias: list[CategoriaRead] = []


# --------------------------------------------------------------------------
# Formas de pagamento
# --------------------------------------------------------------------------


class FormaPagamentoCreate(BaseModel):
    apelido: Nome
    tipo: TipoPagamento
    conta_id: int | None = None
    titular_id: int | None = None
    dia_fechamento: Annotated[int, Field(ge=1, le=31)] | None = None
    dia_vencimento: Annotated[int, Field(ge=1, le=31)] | None = None
    ativo: bool = True


class FormaPagamentoUpdate(BaseModel):
    apelido: Nome | None = None
    tipo: TipoPagamento | None = None
    conta_id: int | None = None
    titular_id: int | None = None
    dia_fechamento: Annotated[int, Field(ge=1, le=31)] | None = None
    dia_vencimento: Annotated[int, Field(ge=1, le=31)] | None = None
    ativo: bool | None = None


class FormaPagamentoRead(_Read):
    apelido: str
    tipo: TipoPagamento
    conta_id: int | None
    titular_id: int | None
    dia_fechamento: int | None
    dia_vencimento: int | None
    ativo: bool


# --------------------------------------------------------------------------
# Locais
# --------------------------------------------------------------------------


class LocalCreate(BaseModel):
    nome: Nome
    cidade: str | None = None
    cnpj: str | None = Field(default=None, max_length=18)
    categoria_padrao_id: int | None = None


class LocalUpdate(BaseModel):
    nome: Nome | None = None
    cidade: str | None = None
    cnpj: str | None = Field(default=None, max_length=18)
    categoria_padrao_id: int | None = None


class LocalRead(_Read):
    nome: str
    #: Derivado de `nome` pelo service — upper sem acento, para matching.
    nome_normalizado: str
    cidade: str | None
    cnpj: str | None
    categoria_padrao_id: int | None


# --------------------------------------------------------------------------
# Orçamentos
# --------------------------------------------------------------------------


class OrcamentoCreate(BaseModel):
    categoria_id: int
    #: Qualquer dia do mês; o service normaliza para o dia 1º.
    competencia: date
    valor_meta: Annotated[Dinheiro, Field(gt=0)]


class OrcamentoUpdate(BaseModel):
    valor_meta: Annotated[Dinheiro, Field(gt=0)] | None = None


class OrcamentoRead(_Read):
    categoria_id: int
    competencia: date
    valor_meta: Decimal
