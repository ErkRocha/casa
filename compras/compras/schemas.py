"""Entrada e saída da API (docs/compras/api.md).

Quantidade é `Decimal` e sai como texto decimal no JSON, como o dinheiro de
finanças. Toda resposta de escrita traz a linha inteira, com `atualizado_em`
e `deleted_em`: o celular troca a cópia local pela resposta.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from compras.enums import EstadoDespensa, OrigemItem, SituacaoItem
from compras.models import Despensa, ItemLista, Produto, Secao

Nome = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
TextoCurto = Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
Observacao = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Quantidade = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


# --- Leitura ----------------------------------------------------------------


class Linha(BaseModel):
    id: int
    criado_em: datetime
    atualizado_em: datetime
    deleted_em: datetime | None


class SecaoLeitura(Linha):
    nome: str
    ordem: int

    @classmethod
    def de(cls, s: Secao) -> Self:
        return cls(
            id=s.id,
            nome=s.nome,
            ordem=s.ordem,
            criado_em=s.criado_em,
            atualizado_em=s.atualizado_em,
            deleted_em=s.deleted_em,
        )


class ProdutoLeitura(Linha):
    nome: str
    secao_id: int
    secao_nome: str
    unidade_padrao: str | None
    id_cliente: uuid.UUID | None

    @classmethod
    def de(cls, p: Produto) -> Self:
        return cls(
            id=p.id,
            nome=p.nome,
            secao_id=p.secao_id,
            secao_nome=p.secao.nome,
            unidade_padrao=p.unidade_padrao,
            id_cliente=p.id_cliente,
            criado_em=p.criado_em,
            atualizado_em=p.atualizado_em,
            deleted_em=p.deleted_em,
        )


class ItemLeitura(Linha):
    produto_id: int
    produto_nome: str
    secao_id: int
    secao_nome: str
    secao_ordem: int
    quantidade: Decimal | None
    unidade: str | None
    observacao: str | None
    situacao: SituacaoItem
    origem: OrigemItem
    adicionado_por: str
    comprado_por: str | None
    comprado_em: datetime | None
    id_cliente: uuid.UUID | None

    @classmethod
    def de(cls, i: ItemLista) -> Self:
        return cls(
            id=i.id,
            produto_id=i.produto_id,
            produto_nome=i.produto.nome,
            secao_id=i.produto.secao_id,
            secao_nome=i.produto.secao.nome,
            secao_ordem=i.produto.secao.ordem,
            quantidade=i.quantidade,
            unidade=i.unidade,
            observacao=i.observacao,
            situacao=i.situacao,
            origem=i.origem,
            adicionado_por=i.adicionado_por,
            comprado_por=i.comprado_por,
            comprado_em=i.comprado_em,
            id_cliente=i.id_cliente,
            criado_em=i.criado_em,
            atualizado_em=i.atualizado_em,
            deleted_em=i.deleted_em,
        )


class ItemResposta(ItemLeitura):
    """O item, e se ele já estava na lista quando o celular pediu."""

    #: Outro já tinha posto o mesmo produto: nada foi criado nem somado.
    ja_estava: bool = False


class DespensaLeitura(Linha):
    produto_id: int
    produto_nome: str
    secao_id: int
    secao_nome: str
    secao_ordem: int
    estado: EstadoDespensa
    estado_por: str
    estado_em: datetime

    @classmethod
    def de(cls, d: Despensa) -> Self:
        return cls(
            id=d.id,
            produto_id=d.produto_id,
            produto_nome=d.produto.nome,
            secao_id=d.produto.secao_id,
            secao_nome=d.produto.secao.nome,
            secao_ordem=d.produto.secao.ordem,
            estado=d.estado,
            estado_por=d.estado_por,
            estado_em=d.estado_em,
            criado_em=d.criado_em,
            atualizado_em=d.atualizado_em,
            deleted_em=d.deleted_em,
        )


class ListaResposta(BaseModel):
    #: Para o próximo `GET /mudancas?desde=`.
    cursor: datetime
    itens: list[ItemLeitura]
    #: "Acabando em casa" que ainda não está na lista (D-25: só sugestão).
    sugestoes: list[DespensaLeitura]


class DespensaResposta(BaseModel):
    despensa: DespensaLeitura
    #: O item que "acabou" pôs na lista; nulo se já havia um pendente.
    item_criado: ItemLeitura | None


class MudancasResposta(BaseModel):
    cursor: datetime
    #: Cursor ausente ou velho demais: busque `/lista` e `/despensa` inteiras.
    recarregar: bool
    itens: list[ItemLeitura]
    despensa: list[DespensaLeitura]
    produtos: list[ProdutoLeitura]
    secoes: list[SecaoLeitura]


class HistoricoPagina(BaseModel):
    items: list[ItemLeitura]
    total: int
    limit: int
    offset: int


# --- Escrita ----------------------------------------------------------------


class SecaoCriar(BaseModel):
    nome: Nome


class SecaoAtualizar(BaseModel):
    nome: Nome


class SecoesOrdem(BaseModel):
    #: Todos os ids das seções, na ordem nova do percurso.
    ids: list[int] = Field(min_length=1)


class ProdutoCriar(BaseModel):
    nome: Nome
    #: Sem seção informada, vai para "Sem seção".
    secao_id: int | None = None
    unidade_padrao: TextoCurto | None = None
    id_cliente: uuid.UUID


class ProdutoAtualizar(BaseModel):
    nome: Nome | None = None
    secao_id: int | None = None
    unidade_padrao: TextoCurto | None = None


class ItemCriar(BaseModel):
    id_cliente: uuid.UUID
    #: Um dos dois. Com o nome de um produto que não existe, ele é criado.
    produto_id: int | None = None
    produto_nome: Nome | None = None
    quantidade: Quantidade | None = None
    unidade: TextoCurto | None = None
    observacao: Observacao | None = None

    @model_validator(mode="after")
    def _um_produto(self) -> Self:
        if (self.produto_id is None) == (self.produto_nome is None):
            raise ValueError("informe produto_id ou produto_nome, um dos dois")
        return self


class ItemAtualizar(BaseModel):
    """Só o que vier é alterado; `null` limpa o campo."""

    quantidade: Quantidade | None = None
    unidade: TextoCurto | None = None
    observacao: Observacao | None = None


class DespensaDefinir(BaseModel):
    estado: EstadoDespensa
