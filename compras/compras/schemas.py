"""Entrada e saída da API (docs/compras/api.md).

Quantidade é `Decimal` e sai como texto decimal no JSON, como o dinheiro de
finanças. Toda resposta de escrita traz a linha inteira, com `atualizado_em`
e `deleted_em`: o celular troca a cópia local pela resposta.
"""

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from compras.enums import (
    EstadoDespensa,
    MedidaBase,
    OrigemAssociacao,
    OrigemItem,
    SituacaoItem,
    StatusNota,
)
from compras.models import (
    Despensa,
    IdentidadeTailscale,
    ItemLista,
    Mercado,
    NotaFiscal,
    NotaItem,
    PassoFeito,
    Produto,
    Secao,
    Variante,
)
from compras.nfce.medida import sugerir_medida

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
    #: A categoria de finanças sugerida para os itens da seção (D-33); sem FK.
    categoria_id_financas: int | None = None

    @classmethod
    def de(cls, s: Secao) -> Self:
        return cls(
            id=s.id,
            nome=s.nome,
            ordem=s.ordem,
            categoria_id_financas=s.categoria_id_financas,
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
    medida_base: MedidaBase | None
    medida_por_unidade: Decimal | None

    @classmethod
    def de(cls, p: Produto) -> Self:
        return cls(
            id=p.id,
            nome=p.nome,
            secao_id=p.secao_id,
            secao_nome=p.secao.nome,
            unidade_padrao=p.unidade_padrao,
            id_cliente=p.id_cliente,
            medida_base=p.medida_base,
            medida_por_unidade=p.medida_por_unidade,
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


class PassoFeitoLeitura(Linha):
    """Um passo do roteiro marcado como feito; apagado, é o passo desfeito."""

    sessao_id: int
    receita_id: int
    feito_por: str
    feito_em: datetime
    id_cliente: uuid.UUID | None

    @classmethod
    def de(cls, p: PassoFeito) -> Self:
        return cls(
            id=p.id,
            sessao_id=p.sessao_id,
            receita_id=p.receita_id,
            feito_por=p.feito_por,
            feito_em=p.feito_em,
            id_cliente=p.id_cliente,
            criado_em=p.criado_em,
            atualizado_em=p.atualizado_em,
            deleted_em=p.deleted_em,
        )


class MudancasResposta(BaseModel):
    cursor: datetime
    #: Cursor ausente ou velho demais: busque `/lista` e `/despensa` inteiras.
    recarregar: bool
    itens: list[ItemLeitura]
    despensa: list[DespensaLeitura]
    produtos: list[ProdutoLeitura]
    secoes: list[SecaoLeitura]
    #: Passos do roteiro feitos ou desfeitos (o desfeito vem com `deleted_em`).
    passos_feitos: list[PassoFeitoLeitura]


class HistoricoPagina(BaseModel):
    items: list[ItemLeitura]
    total: int
    limit: int
    offset: int


# --- Escrita ----------------------------------------------------------------


class SecaoCriar(BaseModel):
    nome: Nome


class SecaoAtualizar(BaseModel):
    """Só o que veio muda. `categoria_id_financas: null` limpa a sugestão."""

    nome: Nome | None = None
    categoria_id_financas: int | None = None


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
    #: Conversão do cardápio (D-30). `null` limpa; `medida_por_unidade` exige `medida_base`.
    medida_base: MedidaBase | None = None
    medida_por_unidade: Quantidade | None = None


class ItemCriar(BaseModel):
    id_cliente: uuid.UUID
    #: Um dos dois. Com o nome de um produto que não existe, ele é criado.
    produto_id: int | None = None
    produto_nome: Nome | None = None
    quantidade: Quantidade | None = None
    unidade: TextoCurto | None = None
    observacao: Observacao | None = None
    #: "voz" para o que chega pelo assistente de voz (MCP do vault). "despensa"
    #: não: é do ciclo da despensa, que o service cria sozinho.
    origem: Literal[OrigemItem.MANUAL, OrigemItem.VOZ] = OrigemItem.MANUAL

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


# --- Nota fiscal e preços ---------------------------------------------------


class MercadoLeitura(Linha):
    nome: str
    razao_social: str | None
    cnpj: str | None
    endereco: str | None
    cidade: str | None

    @classmethod
    def de(cls, m: Mercado) -> Self:
        return cls(
            id=m.id,
            nome=m.nome,
            razao_social=m.razao_social,
            cnpj=m.cnpj,
            endereco=m.endereco,
            cidade=m.cidade,
            criado_em=m.criado_em,
            atualizado_em=m.atualizado_em,
            deleted_em=m.deleted_em,
        )


class MercadoAtualizar(BaseModel):
    nome: Nome | None = None
    cidade: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None


class Comparavel(BaseModel):
    """O preço por kg, L ou unidade, sempre com a unidade dele."""

    valor: Decimal
    por: Literal["kg", "l", "un"]


class SugestaoMedida(BaseModel):
    """Lida na descrição ("450G"); só vale depois de confirmada na variante."""

    medida_base: MedidaBase
    conteudo: Decimal


def _comparavel(valor: Decimal | None, por: str | None) -> Comparavel | None:
    if valor is None or por is None:
        return None
    return Comparavel(valor=valor, por=por)


class NotaItemLeitura(Linha):
    nota_fiscal_id: int
    linha_num: int
    codigo: str | None
    gtin: str | None
    descricao_original: str
    quantidade: Decimal
    unidade: str | None
    valor_unitario: Decimal | None
    valor_total: Decimal
    desconto: Decimal
    produto_id: int | None
    produto_nome: str | None
    origem_associacao: OrigemAssociacao | None
    variante_id: int | None
    variante_nome: str | None
    #: A linha como a nota mostra (quantidade x unitário); igual a `valor_total`.
    preco_cheio: Decimal
    #: Só com variante (a view de preço lê itens associados): a parte do
    #: desconto da nota inteira que coube ao item, o preço pago e o comparável.
    desconto_rateado: Decimal | None
    preco_pago: Decimal | None
    #: O item recebeu parte do desconto da nota: o preço pago é estimativa.
    preco_pago_estimado: bool | None
    comparavel: Comparavel | None
    #: Tamanho lido na descrição, enquanto a variante não tem medida.
    sugestao_medida: SugestaoMedida | None

    @classmethod
    def de(cls, i: NotaItem, preco: Mapping[str, Any] | None = None) -> Self:
        variante: Variante | None = i.variante
        sugestao = None
        if variante is None or variante.medida_base is None:
            achada = sugerir_medida(i.descricao_original)
            if achada is not None:
                sugestao = SugestaoMedida(medida_base=achada.medida_base, conteudo=achada.conteudo)
        preco = preco or {}
        return cls(
            id=i.id,
            nota_fiscal_id=i.nota_fiscal_id,
            linha_num=i.linha_num,
            codigo=i.codigo,
            gtin=i.gtin,
            descricao_original=i.descricao_original,
            quantidade=i.quantidade,
            unidade=i.unidade,
            valor_unitario=i.valor_unitario,
            valor_total=i.valor_total,
            desconto=i.desconto,
            produto_id=i.produto_id,
            produto_nome=i.produto.nome if i.produto is not None else None,
            origem_associacao=i.origem_associacao,
            variante_id=i.variante_id,
            variante_nome=variante.nome if variante is not None else None,
            preco_cheio=i.valor_total,
            desconto_rateado=preco.get("desconto_rateado"),
            preco_pago=preco.get("preco_pago"),
            preco_pago_estimado=preco.get("preco_pago_estimado"),
            comparavel=_comparavel(preco.get("preco_comparavel"), preco.get("por")),
            sugestao_medida=sugestao,
            criado_em=i.criado_em,
            atualizado_em=i.atualizado_em,
            deleted_em=i.deleted_em,
        )


class NotaResumo(Linha):
    """A nota sem o conteúdo bruto (que fica só no banco)."""

    chave_acesso: str
    mercado_id: int | None
    mercado_nome: str | None
    emitida_em: datetime | None
    valor_total: Decimal | None
    desconto_total: Decimal
    url_consulta: str
    conteudo_tipo: str | None
    leitor_versao: str | None
    status: StatusNota
    erro_mensagem: str | None
    transacao_id: int | None
    #: O id da Pluggy da compra pendente a que a nota está ligada (D-28); nunca
    #: junto com `transacao_id`.
    pendente_id_externo: str | None
    #: A transação ligada foi criada por "lançar despesa pela nota".
    despesa_lancada_pela_nota: bool
    lida_por: str
    forma_pagamento_nota: str | None

    @classmethod
    def de(cls, n: NotaFiscal) -> Self:
        return cls(
            id=n.id,
            chave_acesso=n.chave_acesso,
            mercado_id=n.mercado_id,
            mercado_nome=n.mercado.nome if n.mercado is not None else None,
            emitida_em=n.emitida_em,
            valor_total=n.valor_total,
            desconto_total=n.desconto_total,
            url_consulta=n.url_consulta,
            conteudo_tipo=n.conteudo_tipo,
            leitor_versao=n.leitor_versao,
            status=n.status,
            erro_mensagem=n.erro_mensagem,
            transacao_id=n.transacao_id,
            pendente_id_externo=n.pendente_id_externo,
            despesa_lancada_pela_nota=n.despesa_lancada_pela_nota,
            lida_por=n.lida_por,
            forma_pagamento_nota=n.forma_pagamento_nota,
            criado_em=n.criado_em,
            atualizado_em=n.atualizado_em,
            deleted_em=n.deleted_em,
        )


class NotaDetalhe(NotaResumo):
    itens: list[NotaItemLeitura]
    #: Soma dos itens menos o desconto de cada um, pelo banco.
    soma_itens: Decimal
    #: `valor_total - soma_itens`: aparece, não bloqueia (desconto na nota).
    diferenca: Decimal | None
    sem_produto: int


class NotaEntrada(BaseModel):
    #: A URL do QR code ou a chave de acesso (44 dígitos, com ou sem espaços).
    entrada: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AssociarItem(BaseModel):
    produto_id: int


class NovaVariante(BaseModel):
    """O que se confirma ao criar a variante pela nota. Sem nada: o nome da
    nota, o GTIN do item e `pesada` pela unidade `KG`."""

    nome: Nome | None = None
    marca: Nome | None = None
    medida_base: MedidaBase | None = None
    conteudo: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)] | None = None
    pesada: bool | None = None


class AssociarVariante(BaseModel):
    """Uma variante que já existe, ou o produto para o qual criar uma."""

    variante_id: int | None = None
    produto_id: int | None = None
    nova: NovaVariante | None = None

    @model_validator(mode="after")
    def _um_dos_dois(self) -> Self:
        if (self.variante_id is None) == (self.produto_id is None):
            raise ValueError("Informe `variante_id` ou `produto_id`, um dos dois.")
        if self.variante_id is not None and self.nova is not None:
            raise ValueError("`nova` só vale com `produto_id`.")
        return self


class VincularTransacao(BaseModel):
    """Um dos dois confirma a ligação; os dois nulos (ou ausentes) a desfazem."""

    transacao_id: int | None = None
    pendente_id_externo: Annotated[
        str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ] = None

    @model_validator(mode="after")
    def _um_so(self) -> Self:
        if self.transacao_id is not None and self.pendente_id_externo is not None:
            raise ValueError("Informe transacao_id ou pendente_id_externo, não os dois.")
        return self


class SugestaoLigacao(BaseModel):
    """Uma candidata a despesa da nota: transação, ou compra pendente do cartão."""

    tipo: Literal["transacao", "pendente"]
    #: Preenchido quando `tipo = transacao`.
    transacao_id: int | None = None
    #: O id da Pluggy, quando `tipo = pendente`.
    id_externo: str | None = None
    data: date
    valor: Decimal
    descricao: str
    #: A forma de pagamento (o cartão) como finanças a chama.
    cartao: str | None
    forma_tipo: str | None
    #: A forma é do mesmo tipo que a da página da nota (ordena, não filtra).
    forma_combina: bool
    lancada_pela_nota: bool = False


class FormaPagamentoOpcao(BaseModel):
    id: int
    apelido: str
    tipo: str


class PreviaLancamento(BaseModel):
    """O que "lançar despesa pela nota" vai propor, para o usuário confirmar."""

    valor: Decimal
    data: date
    descricao: str
    forma_pagamento_nota: str | None
    #: A forma de finanças do mesmo tipo que a da nota, quando só há uma.
    forma_pagamento_id_sugerida: int | None
    categoria_id_sugerida: int | None
    #: `itens` (seções dos itens) ou `ultima_do_mercado`; nulo sem sugestão.
    categoria_origem: Literal["itens", "ultima_do_mercado"] | None
    formas_pagamento: list[FormaPagamentoOpcao]


class LancarDespesa(BaseModel):
    data: date
    valor: Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
    descricao: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    #: Nulo = gasto conjunto.
    pessoa_id: int | None = None
    forma_pagamento_id: int
    categoria_id: int | None = None


class ConsolidacaoResultado(BaseModel):
    verificadas: int
    #: Pendente que virou transação: `transacao_id` preenchido.
    consolidadas: int
    #: Pendente que sumiu sem virar transação: a nota voltou a "sem despesa".
    desfeitas: int
    #: Transação juntada pela revisão: a nota passou para a substituta.
    movidas: int


class PrecoLinha(BaseModel):
    """`vw_preco_produto`: por produto, mercado e medida da variante."""

    produto_id: int
    produto_nome: str
    mercado_id: int
    mercado_nome: str
    medida_base: MedidaBase | None
    por: Literal["kg", "l", "un"] | None
    ultimo_comparavel: Decimal | None
    ultima_variante_id: int | None
    ultima_compra_em: datetime | None
    preco_min: Decimal | None
    preco_max: Decimal | None
    preco_medio: Decimal | None
    compras: int
    #: Compras sem quantidade comparável: fora das estatísticas.
    sem_comparavel: int


# --- Variantes (D-33) -----------------------------------------------------------


class VarianteCodigoLeitura(BaseModel):
    mercado_id: int
    mercado_nome: str
    codigo: str


class VarianteLeitura(Linha):
    produto_id: int
    produto_nome: str
    nome: str
    marca: str | None
    gtin: str | None
    medida_base: MedidaBase | None
    conteudo: Decimal | None
    pesada: bool
    criado_por: str
    #: O código interno dela em cada mercado.
    codigos: list[VarianteCodigoLeitura]

    @classmethod
    def de(cls, v: Variante, codigos: list[VarianteCodigoLeitura]) -> Self:
        return cls(
            id=v.id,
            produto_id=v.produto_id,
            produto_nome=v.produto.nome,
            nome=v.nome,
            marca=v.marca,
            gtin=v.gtin,
            medida_base=v.medida_base,
            conteudo=v.conteudo,
            pesada=v.pesada,
            criado_por=v.criado_por,
            codigos=codigos,
            criado_em=v.criado_em,
            atualizado_em=v.atualizado_em,
            deleted_em=v.deleted_em,
        )


Gtin = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^([0-9]{8}|[0-9]{12,14})$")
]
Conteudo = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3)]


class VarianteCriar(BaseModel):
    produto_id: int
    nome: Nome
    marca: Nome | None = None
    gtin: Gtin | None = None
    medida_base: MedidaBase | None = None
    conteudo: Conteudo | None = None
    pesada: bool = False


class VarianteAtualizar(BaseModel):
    produto_id: int | None = None
    nome: Nome | None = None
    marca: Nome | None = None
    medida_base: MedidaBase | None = None
    conteudo: Conteudo | None = None
    pesada: bool | None = None


class VarianteJuntar(BaseModel):
    #: A que será absorvida: fica a da URL, a outra é apagada (soft delete).
    outra_id: int


# --- Preços (D-33) ---------------------------------------------------------------


class PrecoItem(BaseModel):
    """Uma compra de uma variante, de `vw_preco_variante`."""

    nota_item_id: int
    nota_fiscal_id: int
    mercado_id: int | None
    mercado_nome: str | None
    data: datetime | None
    quantidade: Decimal
    unidade: str | None
    preco_cheio: Decimal
    #: Desconto de linha mais a parte do desconto da nota inteira.
    desconto: Decimal
    desconto_linha: Decimal
    desconto_rateado: Decimal
    preco_pago: Decimal
    preco_pago_estimado: bool
    #: Nulo quando a variante não tem medida (ou a unidade da nota não bate).
    comparavel: Comparavel | None


class HistoricoVariante(BaseModel):
    variante: VarianteLeitura
    total: int
    limite: int
    offset: int
    #: Compras sem comparável, no histórico inteiro.
    sem_comparavel: int
    itens: list[PrecoItem]


class PrecoEstatistica(BaseModel):
    por: Literal["kg", "l", "un"] | None
    ultimo_comparavel: Decimal | None
    ultima_compra_em: datetime | None
    minimo: Decimal | None
    maximo: Decimal | None
    media: Decimal | None
    compras: int
    sem_comparavel: int


class PrecoPorVariante(PrecoEstatistica):
    variante_id: int
    variante_nome: str
    ultimo_mercado_id: int | None
    ultimo_mercado_nome: str | None


class PrecoPorMercado(PrecoEstatistica):
    mercado_id: int
    mercado_nome: str
    ultima_variante_id: int | None
    ultima_variante_nome: str | None


class VarianteMaisBarata(BaseModel):
    por: Literal["kg", "l", "un"]
    variante_id: int
    variante_nome: str
    mercado_id: int | None
    mercado_nome: str | None
    ultimo_comparavel: Decimal
    ultima_compra_em: datetime | None


class PrecoProduto(BaseModel):
    produto_id: int
    produto_nome: str
    por_variante: list[PrecoPorVariante]
    por_mercado: list[PrecoPorMercado]
    #: A de menor último comparável, uma por unidade (kg, l, un).
    mais_barata: list[VarianteMaisBarata]
    sem_comparavel: int


class PrecoMercadoProduto(BaseModel):
    produto_id: int
    produto_nome: str
    por: Literal["kg", "l", "un"] | None
    ultimo_comparavel: Decimal | None
    ultima_compra_em: datetime | None
    #: Média dos comparáveis nos outros mercados, e a diferença deste em %.
    media_outros_mercados: Decimal | None
    diferenca_percentual: Decimal | None
    compras: int
    sem_comparavel: int


class PrecoMercado(BaseModel):
    mercado_id: int
    mercado_nome: str
    total: int
    limite: int
    offset: int
    itens: list[PrecoMercadoProduto]


class MercadoRanking(BaseModel):
    posicao: int
    por: Literal["kg", "l", "un"]
    mercado_id: int
    mercado_nome: str
    variante_id: int
    variante_nome: str
    comparavel: Decimal
    data: datetime
    dias_atras: int


class OndeMaisBarato(BaseModel):
    produto_id: int
    produto_nome: str
    dias: int
    #: Por unidade (kg, l, un), do mais barato ao mais caro: o último
    #: comparável de cada mercado dentro da janela.
    ranking: list[MercadoRanking]


# --- Identidade pelo Tailscale ----------------------------------------------


class Eu(BaseModel):
    """Quem o serviço vê nesta requisição."""

    quem: str | None
    #: "tailscale": o front não pergunta "quem é você?". Nulo: perguntar.
    origem: Literal["tailscale", "aparelho"] | None
    login: str | None
    cadastrado: bool


class IdentidadeLeitura(Linha):
    login: str
    nome: str

    @classmethod
    def de(cls, i: IdentidadeTailscale) -> Self:
        return cls(
            id=i.id,
            login=i.login,
            nome=i.nome,
            criado_em=i.criado_em,
            atualizado_em=i.atualizado_em,
            deleted_em=i.deleted_em,
        )


class IdentidadeCriar(BaseModel):
    #: O login da pessoa na tailnet, como aparece no painel do Tailscale.
    login: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


class IdentidadeAtualizar(BaseModel):
    nome: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
