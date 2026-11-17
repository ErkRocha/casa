"""A lista de compras pelo cardápio (modelo-cardapio.md, "Geração da lista", D-30).

`GET /semanas/{id}/lista` é a prévia e `POST` grava; os dois partem do mesmo
plano, que só lê. O plano diz, produto a produto, o que mudaria; gravar é
aplicá-lo, numa transação, com a linha da semana travada (`FOR UPDATE`).

Quem criou ou ajustou o quê fica em `itens_lista_cardapio`: o quanto cada
semana pôs em cada item. É isso que faz repetir a geração aplicar só a
diferença. O item em si nasce e muda pelo `ListaService` (pendente único,
ciclo da despensa), sem duplicar a regra aqui.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from compras import tempo
from compras.enums import EstadoDespensa, OrigemItem
from compras.models import Despensa, ItemLista, ItemListaCardapio, Semana
from compras.schemas_cardapio import (
    ListaAjustado,
    ListaAviso,
    ListaCardapio,
    ListaConfira,
    ListaCriado,
    ListaSemMudanca,
)
from compras.services.base import Conflito, NaoEncontrado
from compras.services.lista import ListaService
from compras.services.pedido import Pedido, pedido_da_semana

TEXTO_CONFIRA = "provavelmente já tem, confira"

Vinculo = tuple[ItemListaCardapio, ItemLista]


def _mesma_unidade(a: str | None, b: str | None) -> bool:
    """Item sem unidade é lido como a unidade do pedido; senão, igual sem caixa."""
    if a is None or b is None:
        return True
    return a.strip().lower() == b.strip().lower()


# --- o plano -----------------------------------------------------------------


@dataclass
class Somar:
    """Soma no item pendente que já existe."""

    pedido: Pedido
    item: ItemLista
    delta: Decimal | None
    antes: Decimal | None
    depois: Decimal | None
    #: A quantidade do item muda (os dois têm quantidade e a mesma unidade).
    mexe: bool


@dataclass
class Criar:
    pedido: Pedido
    quantidade: Decimal | None
    item_id: int | None = None
    #: Outra geração pôs o pendente entre o plano e a gravação: virou soma nele.
    ajuste: Somar | None = None


@dataclass
class Diminuir:
    """Tira do pendente o que esta semana tinha posto nele (no máximo isso)."""

    pedido: Pedido
    item: ItemLista
    contrib: ItemListaCardapio
    antes: Decimal | None
    depois: Decimal | None
    mexe: bool
    #: A contribuição da semana zerou: sai a linha dela.
    consumida: bool
    restante: Decimal | None
    #: O item era só do cardápio e zerou: sai da lista (soft delete).
    remover: bool


@dataclass
class SemMudanca:
    pedido: Pedido
    item_id: int | None


@dataclass
class Confira:
    pedido: Pedido
    estado: EstadoDespensa


Acao = Somar | Criar | Diminuir | SemMudanca | Confira


@dataclass
class Plano:
    acoes: list[Acao] = field(default_factory=list)
    avisos: list[ListaAviso] = field(default_factory=list)


# --- o service ---------------------------------------------------------------


class ListaCardapioService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem
        self.lista = ListaService(session, quem)

    def previa(self, semana: Semana) -> ListaCardapio:
        """O que a geração faria, sem gravar nada."""
        self._exigir_nao_passada(semana)
        return self._resposta(self._planejar(semana))

    def gerar(self, semana_id: int) -> ListaCardapio:
        """Grava. A semana fica travada até o commit: duas gerações ao mesmo tempo
        dão o resultado de uma só (a segunda espera e então não tem o que mudar)."""
        semana = self.session.scalar(
            select(Semana)
            .where(Semana.id == semana_id, Semana.deleted_em.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if semana is None:
            raise NaoEncontrado("semana", semana_id)
        self._exigir_nao_passada(semana)
        plano = self._planejar(semana)
        self._aplicar(plano, semana)
        return self._resposta(plano)

    @staticmethod
    def _exigir_nao_passada(semana: Semana) -> None:
        if tempo.passou(semana.inicio):
            raise Conflito(
                "A semana já passou: vira histórico e não gera lista (D-30).",
                {"semana": {"id": semana.id, "inicio": semana.inicio.isoformat()}},
            )

    # -- planejar --------------------------------------------------------

    def _planejar(self, semana: Semana) -> Plano:
        pedidos, avisos = pedido_da_semana(self.session, semana)
        vinculos = self._vinculos(semana.id)
        ids = set(pedidos) | set(vinculos)
        estados = self._despensa(ids)

        def nome(produto_id: int) -> str:
            if produto_id in pedidos:
                return pedidos[produto_id].produto.nome_normalizado
            return vinculos[produto_id][0][1].produto.nome_normalizado

        plano = Plano(avisos=avisos)
        for produto_id in sorted(ids, key=nome):
            plano.acoes.append(
                self._produto(
                    pedidos.get(produto_id),
                    vinculos.get(produto_id, []),
                    self.lista.pendente(produto_id),
                    estados.get(produto_id),
                )
            )
        return plano

    def _produto(
        self,
        pedido: Pedido | None,
        vinculos: list[Vinculo],
        pendente: ItemLista | None,
        estado: EstadoDespensa | None,
    ) -> Acao:
        if pedido is None:
            # A semana não pede mais: desfaz o que pôs no pendente.
            item = vinculos[0][1]
            apagado = Pedido(item.produto, Decimal("0.000"), vinculos[0][0].unidade, [], None)
            return self._recolher(apagado, vinculos, pendente, None)

        itens = [i.id for _, i in vinculos]
        item_id = pendente.id if pendente is not None else (itens[-1] if itens else None)

        if pedido.quantidade is None:
            # "A gosto" ou sem conversão: atendido se esta semana já pôs algo.
            if vinculos:
                return SemMudanca(pedido, item_id)
            return self._entrar(pedido, None, pendente, estado)

        atendido = sum(
            (
                c.quantidade
                for c, _ in vinculos
                if c.quantidade is not None and _mesma_unidade(c.unidade, pedido.unidade)
            ),
            Decimal(0),
        )
        diferenca = pedido.quantidade - atendido
        if diferenca == 0:
            return SemMudanca(pedido, item_id)
        if diferenca > 0:
            return self._entrar(pedido, diferenca, pendente, estado)
        return self._recolher(pedido, vinculos, pendente, -diferenca)

    @staticmethod
    def _entrar(
        pedido: Pedido,
        delta: Decimal | None,
        pendente: ItemLista | None,
        estado: EstadoDespensa | None,
    ) -> Acao:
        """O pedido cresceu (ou é novo): soma no pendente, cria um, ou manda conferir."""
        if pendente is not None:
            # Já está na lista (o casal já decidiu): ajusta mesmo com a despensa em `tem`.
            return ListaCardapioService._somar(pedido, pendente, delta)
        if estado == EstadoDespensa.TEM:
            return Confira(pedido, estado)
        return Criar(pedido, delta)

    @staticmethod
    def _somar(pedido: Pedido, item: ItemLista, delta: Decimal | None) -> Somar:
        mexe = (
            delta is not None
            and item.quantidade is not None
            and _mesma_unidade(item.unidade, pedido.unidade)
        )
        antes = item.quantidade
        depois = antes + delta if mexe and antes is not None and delta is not None else antes
        return Somar(pedido, item, delta, antes, depois, mexe)

    def _recolher(
        self,
        pedido: Pedido,
        vinculos: list[Vinculo],
        pendente: ItemLista | None,
        quanto: Decimal | None,
    ) -> Acao:
        """O pedido encolheu: tira do pendente, no máximo o que esta semana pôs nele.
        Comprado não se desfaz; item removido à mão já conta como atendido."""
        alvo = next(
            ((c, i) for c, i in vinculos if pendente is not None and i.id == pendente.id), None
        )
        if alvo is None or (alvo[0].quantidade is None and quanto is not None):
            return SemMudanca(pedido, pendente.id if pendente is not None else None)
        contrib, item = alvo

        if quanto is None:
            tirar = contrib.quantidade
        else:
            assert contrib.quantidade is not None
            tirar = min(quanto, contrib.quantidade)
        restante = (
            None if tirar is None or contrib.quantidade is None else contrib.quantidade - tirar
        )
        consumida = restante is None or restante <= 0

        mexe = (
            tirar is not None
            and item.quantidade is not None
            and contrib.quantidade is not None
            and _mesma_unidade(contrib.unidade, item.unidade)
        )
        antes = item.quantidade
        depois = antes
        if mexe and antes is not None and tirar is not None:
            depois = max(antes - tirar, Decimal(0))

        so_do_cardapio = item.origem == OrigemItem.CARDAPIO
        if mexe:
            remover = so_do_cardapio and depois is not None and depois <= 0
        else:
            outras = self.session.scalar(
                select(func.count())
                .select_from(ItemListaCardapio)
                .where(
                    ItemListaCardapio.item_lista_id == item.id,
                    ItemListaCardapio.deleted_em.is_(None),
                    ItemListaCardapio.id != contrib.id,
                )
            )
            remover = so_do_cardapio and consumida and not outras
        return Diminuir(pedido, item, contrib, antes, depois, mexe, consumida, restante, remover)

    def _vinculos(self, semana_id: int) -> dict[int, list[Vinculo]]:
        """O que esta semana pôs, por produto: a linha e o item (em qualquer estado)."""
        linhas = self.session.execute(
            select(ItemListaCardapio, ItemLista)
            .join(ItemLista, ItemLista.id == ItemListaCardapio.item_lista_id)
            .where(ItemListaCardapio.semana_id == semana_id, ItemListaCardapio.deleted_em.is_(None))
            .order_by(ItemListaCardapio.id)
            .execution_options(populate_existing=True)
        )
        por_produto: dict[int, list[Vinculo]] = defaultdict(list)
        for contrib, item in linhas:
            por_produto[item.produto_id].append((contrib, item))
        return por_produto

    def _despensa(self, produto_ids: set[int]) -> dict[int, EstadoDespensa]:
        if not produto_ids:
            return {}
        linhas = self.session.execute(
            select(Despensa.produto_id, Despensa.estado).where(
                Despensa.produto_id.in_(produto_ids), Despensa.deleted_em.is_(None)
            )
        )
        return {int(p): e for p, e in linhas}

    # -- gravar ----------------------------------------------------------

    def _aplicar(self, plano: Plano, semana: Semana) -> None:
        for acao in plano.acoes:
            if isinstance(acao, Criar):
                self._criar(acao, semana)
            elif isinstance(acao, Somar):
                self._somar_no_item(acao, semana)
            elif isinstance(acao, Diminuir):
                self._diminuir(acao)
        self.session.flush()

    def _criar(self, acao: Criar, semana: Semana) -> None:
        pedido = acao.pedido
        item, criado, _ = self.lista.criar(
            uuid.uuid4(),
            produto_id=pedido.produto.id,
            quantidade=acao.quantidade,
            unidade=pedido.unidade,
            observacao=pedido.observacao,
            origem=OrigemItem.CARDAPIO,
        )
        if criado:
            acao.item_id = item.id
            self._registrar(item.id, semana.id, acao.quantidade, pedido.unidade)
            return
        # Outra geração (de outra semana) pôs o pendente nesse meio-tempo: soma nele.
        acao.ajuste = self._somar(pedido, item, acao.quantidade)
        self._somar_no_item(acao.ajuste, semana)

    def _somar_no_item(self, acao: Somar, semana: Semana) -> None:
        if acao.mexe and acao.delta is not None:
            self.lista.atualizar(acao.item.id, {"quantidade": acao.depois})
        self._registrar(acao.item.id, semana.id, acao.delta, acao.pedido.unidade)

    def _diminuir(self, acao: Diminuir) -> None:
        if acao.consumida:
            acao.contrib.deleted_em = func.now()
        else:
            acao.contrib.quantidade = acao.restante
        if acao.remover:
            self.lista.remover(acao.item.id)
        elif acao.mexe:
            # Quantidade zero não existe (check): o item de outra origem fica "o de sempre".
            quantidade = acao.depois if acao.depois is not None and acao.depois > 0 else None
            self.lista.atualizar(acao.item.id, {"quantidade": quantidade})

    def _registrar(
        self, item_id: int, semana_id: int, delta: Decimal | None, unidade: str | None
    ) -> None:
        """Soma `delta` à linha desta semana no item, ou cria a linha."""
        linha = self.session.scalar(
            select(ItemListaCardapio)
            .where(
                ItemListaCardapio.item_lista_id == item_id,
                ItemListaCardapio.semana_id == semana_id,
                ItemListaCardapio.deleted_em.is_(None),
            )
            .execution_options(populate_existing=True)
        )
        if linha is None:
            self.session.add(
                ItemListaCardapio(
                    item_lista_id=item_id,
                    semana_id=semana_id,
                    quantidade=delta,
                    unidade=unidade,
                    gerado_por=self.quem,
                )
            )
            return
        if delta is not None:
            linha.quantidade = (linha.quantidade or Decimal(0)) + delta
        if linha.unidade is None:
            linha.unidade = unidade

    # -- resposta --------------------------------------------------------

    def _resposta(self, plano: Plano) -> ListaCardapio:
        resposta = ListaCardapio(
            criados=[], ajustados=[], sem_mudanca=[], confira=[], avisos=plano.avisos
        )
        for acao in plano.acoes:
            pedido = acao.pedido
            nome = pedido.produto.nome
            if isinstance(acao, Criar) and acao.ajuste is None:
                resposta.criados.append(
                    ListaCriado(
                        produto=nome,
                        item_id=acao.item_id,
                        quantidade=acao.quantidade,
                        unidade=pedido.unidade or pedido.produto.unidade_padrao,
                        de=pedido.de,
                    )
                )
            elif isinstance(acao, Criar | Somar):
                soma = acao.ajuste if isinstance(acao, Criar) else acao
                assert soma is not None
                resposta.ajustados.append(
                    ListaAjustado(
                        produto=nome,
                        item_id=soma.item.id,
                        antes=soma.antes,
                        depois=soma.depois,
                        unidade=soma.item.unidade,
                        origem_item=soma.item.origem,
                        pedido=pedido.quantidade,
                        de=pedido.de,
                    )
                )
            elif isinstance(acao, Diminuir):
                resposta.ajustados.append(
                    ListaAjustado(
                        produto=nome,
                        item_id=acao.item.id,
                        antes=acao.antes,
                        depois=Decimal("0.000") if acao.remover else acao.depois,
                        unidade=acao.item.unidade,
                        origem_item=acao.item.origem,
                        removido=acao.remover,
                        pedido=pedido.quantidade,
                        de=pedido.de,
                    )
                )
            elif isinstance(acao, SemMudanca):
                resposta.sem_mudanca.append(
                    ListaSemMudanca(
                        produto=nome,
                        item_id=acao.item_id,
                        pedido=pedido.quantidade,
                        unidade=pedido.unidade,
                        de=pedido.de,
                    )
                )
            elif isinstance(acao, Confira):
                resposta.confira.append(
                    ListaConfira(
                        produto=nome,
                        estado_despensa=acao.estado,
                        pedido=pedido.quantidade,
                        unidade=pedido.unidade,
                        texto=TEXTO_CONFIRA,
                        de=pedido.de,
                    )
                )
        return resposta
