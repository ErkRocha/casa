"""O pedido da semana: o que o cardápio pede de cada produto (D-30).

Regras 1 e 2 de "Geração da lista" (modelo-cardapio.md): para cada refeição
viva com receita, cada ingrediente vivo vale `quantidade x fator`
(porções da refeição / rendimento da receita), convertido para a base do
produto. A soma é por produto, na base; só então vai para a unidade de
compra. Tudo em `Decimal`.

Cálculo puro: lê e não grava. A prévia e a geração partem dele.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from compras.enums import UnidadeMedida
from compras.models import Produto, Receita, Semana
from compras.schemas_cardapio import ListaAviso
from compras.services import conversao
from compras.services.receitas import ReceitaService
from compras.services.refeicoes import RefeicaoService


@dataclass
class Pedido:
    """O que a semana pede de um produto, já na unidade de compra."""

    produto: Produto
    #: Nula quando é só "a gosto" ou quando não converteu.
    quantidade: Decimal | None
    unidade: str | None
    #: As receitas de onde veio, na ordem em que apareceram.
    de: list[str]
    #: "cardápio: 2 colher_sopa" quando algo não converteu, ou "cardápio: a gosto".
    observacao: str | None


@dataclass
class _Soma:
    produto: Produto
    base: Decimal = Decimal(0)
    #: Alguma linha chegou à base do produto.
    converteu: bool = False
    #: O que não converteu, por unidade da receita.
    sem_conversao: dict[UnidadeMedida, Decimal] = field(default_factory=dict)
    a_gosto: bool = False
    de: list[str] = field(default_factory=list)


def _texto(valor: Decimal) -> str:
    """3 em vez de 3.000 e 0.5 em vez de 0.500, sem notação científica."""
    return format(valor.normalize(), "f")


def pedido_da_semana(
    session: Session, semana: Semana
) -> tuple[dict[int, Pedido], list[ListaAviso]]:
    """(pedido por `produto_id`, avisos de conversão e de receita apagada)."""
    refeicoes_service = RefeicaoService(session)
    refeicoes = [r for r in refeicoes_service.da_semana(semana.id) if r.receita_id is not None]
    receita_ids = sorted({r.receita_id for r in refeicoes if r.receita_id is not None})
    receitas = {
        r.id: r for r in session.scalars(select(Receita).where(Receita.id.in_(receita_ids)))
    }
    porcoes = refeicoes_service.porcoes([r.id for r in refeicoes])
    ingredientes = ReceitaService(session).ingredientes_vivos(receita_ids, semana.inicio)

    avisos: list[ListaAviso] = []
    avisada: set[int] = set()
    somas: dict[int, _Soma] = {}
    for refeicao in refeicoes:
        assert refeicao.receita_id is not None
        receita = receitas[refeicao.receita_id]
        if receita.deleted_em is not None:
            if receita.id not in avisada:
                avisada.add(receita.id)
                avisos.append(ListaAviso(produto=None, texto=f"receita apagada: {receita.nome}"))
            continue
        fator = porcoes[refeicao.id] / receita.rendimento_porcoes
        for ingrediente in ingredientes[receita.id]:
            produto = ingrediente.produto
            soma = somas.setdefault(produto.id, _Soma(produto))
            if receita.nome not in soma.de:
                soma.de.append(receita.nome)
            if ingrediente.quantidade is None:
                soma.a_gosto = True
                continue
            quantidade = ingrediente.quantidade * fator
            base = conversao.para_base_produto(
                quantidade, ingrediente.unidade, produto.medida_base, produto.medida_por_unidade
            )
            if base is None:
                soma.sem_conversao[ingrediente.unidade] = (
                    soma.sem_conversao.get(ingrediente.unidade, Decimal(0)) + quantidade
                )
            else:
                soma.base += base
                soma.converteu = True

    pedidos: dict[int, Pedido] = {}
    for produto_id, soma in somas.items():
        pedido, avisos_do_produto = _fechar(soma)
        pedidos[produto_id] = pedido
        avisos.extend(avisos_do_produto)
    return pedidos, avisos


def _fechar(soma: _Soma) -> tuple[Pedido, list[ListaAviso]]:
    """A soma na base vira a unidade de compra; o que não converteu vira aviso."""
    produto = soma.produto
    avisos: list[ListaAviso] = []
    quantidade: Decimal | None = None
    unidade: str | None = None
    pendentes: list[str] = []

    if soma.converteu:
        compra = conversao.para_compra(
            soma.base, produto.medida_base, produto.medida_por_unidade, produto.unidade_padrao
        )
        if compra is not None:
            quantidade, unidade = compra
        else:
            base = produto.medida_base.value if produto.medida_base is not None else ""
            pendentes.append(f"{_texto(soma.base)} {base}")
            avisos.append(
                ListaAviso(
                    produto=produto.nome,
                    texto=(
                        f"cadastre a medida: {_texto(soma.base)} {base} não converte para "
                        f"{produto.unidade_padrao or 'un'}"
                    ),
                )
            )

    for unidade_receita, valor in soma.sem_conversao.items():
        pendentes.append(f"{_texto(valor)} {unidade_receita.value}")
        destino = produto.medida_base.value if produto.medida_base is not None else None
        avisos.append(
            ListaAviso(
                produto=produto.nome,
                texto=(
                    f"cadastre a medida: {_texto(valor)} {unidade_receita.value} "
                    + (
                        f"não converte para {destino}"
                        if destino
                        else "não converte (sem medida_base)"
                    )
                ),
            )
        )

    observacao: str | None = None
    if pendentes:
        observacao = "cardápio: " + "; ".join(pendentes)
    elif quantidade is None and soma.a_gosto:
        observacao = "cardápio: a gosto"
    return Pedido(produto, quantidade, unidade, soma.de, observacao), avisos
