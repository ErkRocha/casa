"""A lista da casa: adicionar, comprar, desfazer, tirar (api.md, Lista).

Os dois celulares ao mesmo tempo são o caso normal, não a exceção. As
garantias moram no banco (único de `id_cliente`, um pendente por produto) e
as escritas condicionais (`UPDATE ... WHERE situacao = ...`) deixam a
segunda chegar sem erro: o resultado que ela queria já aconteceu.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.enums import FechamentoItem, OrigemItem, SituacaoItem
from compras.models import ItemLista, Produto, Secao
from compras.schemas import ItemLeitura
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.despensa import DespensaService
from compras.services.produtos import ProdutoService

#: Quantas vezes tentar de novo quando o pendente some entre o INSERT que
#: esbarrou nele e a leitura (o outro comprou nesse meio-tempo).
_TENTATIVAS = 3


class ListaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem
        self.despensa = DespensaService(session, quem)

    # -- leitura ---------------------------------------------------------

    def listar(self, comprados_desde: datetime) -> list[ItemLista]:
        """Pendentes e comprados recentes, pendentes primeiro, na ordem do percurso."""
        return list(
            self.session.scalars(
                self._ordenada().where(
                    ItemLista.deleted_em.is_(None),
                    (ItemLista.situacao == SituacaoItem.PENDENTE)
                    | (ItemLista.comprado_em >= comprados_desde),
                )
            )
        )

    def aguardando_nota(self) -> list[ItemLista]:
        """Comprados que ainda esperam nota (`fechamento` nulo), os mais antigos primeiro."""
        return list(
            self.session.scalars(
                select(ItemLista)
                .where(*self._aguardando())
                .order_by(ItemLista.comprado_em, ItemLista.id)
            )
        )

    def perguntas(self, comprados_antes_de: datetime) -> list[ItemLista]:
        """Os aguardando nota comprados antes de `comprados_antes_de` (agora menos
        7 dias) e nunca perguntados: a pergunta aparece uma vez (D-33)."""
        return list(
            self.session.scalars(
                select(ItemLista)
                .where(
                    *self._aguardando(),
                    ItemLista.perguntado_em.is_(None),
                    ItemLista.comprado_em <= comprados_antes_de,
                )
                .order_by(ItemLista.comprado_em, ItemLista.id)
            )
        )

    def historico(
        self, produto_id: int | None, limite: int, deslocamento: int
    ) -> tuple[list[ItemLista], int]:
        filtro = [ItemLista.deleted_em.is_(None), ItemLista.situacao == SituacaoItem.COMPRADO]
        if produto_id is not None:
            filtro.append(ItemLista.produto_id == produto_id)
        total = self.session.scalar(select(func.count()).select_from(ItemLista).where(*filtro))
        itens = self.session.scalars(
            select(ItemLista)
            .where(*filtro)
            .order_by(ItemLista.comprado_em.desc(), ItemLista.id.desc())
            .limit(limite)
            .offset(deslocamento)
        )
        return list(itens), int(total or 0)

    def get(self, id_: int) -> ItemLista:
        """O item em qualquer estado, apagado inclusive, recarregado do banco."""
        item = self.session.scalar(
            select(ItemLista).where(ItemLista.id == id_).execution_options(populate_existing=True)
        )
        if item is None:
            raise NaoEncontrado("item", id_)
        return item

    # -- escrita ---------------------------------------------------------

    def criar(
        self,
        id_cliente: uuid.UUID,
        produto_id: int | None = None,
        produto_nome: str | None = None,
        quantidade: Decimal | None = None,
        unidade: str | None = None,
        observacao: str | None = None,
        origem: OrigemItem = OrigemItem.MANUAL,
    ) -> tuple[ItemLista, bool, bool]:
        """(item, criado agora, já estava na lista).

        * mesmo `id_cliente` de antes: o mesmo item, nada criado (reenvio);
        * produto já pendente: o pendente que existe, sem somar quantidade.
        """
        anterior = self._por_id_cliente(id_cliente)
        if anterior is not None:
            return anterior, False, False

        produtos = ProdutoService(self.session)
        if produto_id is not None:
            produto = produtos.get(produto_id)
        else:
            assert produto_nome is not None
            produto = produtos.obter_ou_criar(produto_nome)

        for _ in range(_TENTATIVAS):
            # Sem alvo no ON CONFLICT: vale para os dois únicos, o do
            # `id_cliente` e o do pendente por produto. Se o outro celular
            # está gravando o mesmo produto agora, este INSERT espera o
            # commit dele e então não faz nada.
            novo = self.session.execute(
                insert(ItemLista)
                .values(
                    produto_id=produto.id,
                    quantidade=quantidade,
                    unidade=unidade or produto.unidade_padrao,
                    observacao=observacao,
                    situacao=SituacaoItem.PENDENTE,
                    origem=origem,
                    adicionado_por=self.quem,
                    id_cliente=id_cliente,
                )
                .on_conflict_do_nothing()
                .returning(ItemLista.id)
            ).scalar()
            if novo is not None:
                return self.get(novo), True, False

            repetido = self._por_id_cliente(id_cliente)
            if repetido is not None:
                return repetido, False, False
            pendente = self._pendente(produto.id)
            if pendente is not None:
                return pendente, False, True
        raise Conflito("A lista mudou várias vezes seguidas; tente de novo.")

    def atualizar(self, id_: int, dados: dict[str, Any]) -> ItemLista:
        item = self._vivo(id_)
        for campo in ("quantidade", "unidade", "observacao"):
            if campo in dados:
                setattr(item, campo, dados[campo])
        self.session.flush()
        return self.get(id_)

    def comprar(self, id_: int) -> ItemLista:
        """Marca comprado. Já comprado: devolve como está, com o primeiro comprador."""
        feito = self.session.execute(
            update(ItemLista)
            .where(
                ItemLista.id == id_,
                ItemLista.situacao == SituacaoItem.PENDENTE,
                ItemLista.deleted_em.is_(None),
            )
            .values(situacao=SituacaoItem.COMPRADO, comprado_por=self.quem, comprado_em=func.now())
            .returning(ItemLista.produto_id)
        ).scalar()
        if feito is not None:
            self.despensa.comprado(feito)
            return self.get(id_)
        return self._vivo(id_)

    def desfazer(self, id_: int) -> ItemLista:
        """Volta a pendente. Já pendente: devolve como está. Item fechado por
        nota: 409, porque a nota é a fonte da verdade (D-33)."""
        try:
            with self.session.begin_nested():
                feito = self.session.execute(
                    update(ItemLista)
                    .where(
                        ItemLista.id == id_,
                        ItemLista.situacao == SituacaoItem.COMPRADO,
                        ItemLista.deleted_em.is_(None),
                        ItemLista.fechamento.is_distinct_from(FechamentoItem.NOTA),
                    )
                    .values(
                        situacao=SituacaoItem.PENDENTE,
                        comprado_por=None,
                        comprado_em=None,
                        fechamento=None,
                        fechado_em=None,
                        fechado_por=None,
                        perguntado_em=None,
                    )
                    .returning(ItemLista.produto_id)
                ).scalar()
        except IntegrityError as erro:
            item = self.get(id_)
            raise Conflito(
                f'"{item.produto.nome}" já voltou para a lista por outro item.',
                {"item": ItemLeitura.de(item).model_dump(mode="json")},
            ) from erro
        if feito is not None:
            self.despensa.compra_desfeita(feito)
            return self.get(id_)
        item = self._vivo(id_)
        if item.fechamento == FechamentoItem.NOTA:
            raise Conflito(
                f'"{item.produto.nome}" foi confirmado por uma nota; a nota é a fonte da verdade.',
                {"item": ItemLeitura.de(item).model_dump(mode="json")},
            )
        return item

    def fechar(self, id_: int, como: FechamentoItem) -> ItemLista:
        """Resolve o "comprado, aguardando nota" (D-33).

        * `sem_nota`: comprou e não vai haver nota; fecha como comprado;
        * `nao_comprei`: volta a pendente, ou, se o produto já tem outro
          pendente (pendente único), é removido com `fechamento = nao_comprei`.
          A despensa vai para `acabou`, como no desfazer.
        """
        if como not in (FechamentoItem.SEM_NOTA, FechamentoItem.NAO_COMPREI):
            raise RegraViolada("Feche com `sem_nota` ou `nao_comprei`.")
        self._aguardando_vivo(id_)
        aguardando = (
            ItemLista.id == id_,
            ItemLista.situacao == SituacaoItem.COMPRADO,
            ItemLista.fechamento.is_(None),
            ItemLista.deleted_em.is_(None),
        )
        if como == FechamentoItem.SEM_NOTA:
            feito = self.session.execute(
                update(ItemLista)
                .where(*aguardando)
                .values(fechamento=como, fechado_em=func.now(), fechado_por=self.quem)
                .returning(ItemLista.produto_id)
            ).scalar()
            if feito is None:
                self._aguardando_vivo(id_)
            return self.get(id_)

        produto_id: int | None
        try:
            with self.session.begin_nested():
                produto_id = self.session.execute(
                    update(ItemLista)
                    .where(*aguardando)
                    .values(
                        situacao=SituacaoItem.PENDENTE,
                        comprado_por=None,
                        comprado_em=None,
                        perguntado_em=None,
                    )
                    .returning(ItemLista.produto_id)
                ).scalar()
        except IntegrityError:
            # O produto já tem outro pendente: este sai da lista.
            produto_id = self.session.execute(
                update(ItemLista)
                .where(*aguardando)
                .values(
                    fechamento=FechamentoItem.NAO_COMPREI,
                    fechado_em=func.now(),
                    fechado_por=self.quem,
                    deleted_em=func.now(),
                )
                .returning(ItemLista.produto_id)
            ).scalar()
        if produto_id is None:
            self._aguardando_vivo(id_)
        else:
            self.despensa.compra_desfeita(produto_id)
        return self.get(id_)

    def dispensar_pergunta(self, id_: int) -> ItemLista:
        """Grava `perguntado_em` sem fechar: não pergunta de novo e o item
        continua aguardando nota. Repetir mantém a primeira data."""
        item = self._aguardando_vivo(id_)
        if item.perguntado_em is None:
            self.session.execute(
                update(ItemLista)
                .where(ItemLista.id == id_, ItemLista.perguntado_em.is_(None))
                .values(perguntado_em=func.now())
            )
        return self.get(id_)

    def remover(self, id_: int) -> ItemLista:
        """Tira da lista (soft delete). Já tirado: devolve como está."""
        self.session.execute(
            update(ItemLista)
            .where(ItemLista.id == id_, ItemLista.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        return self.get(id_)

    # -- apoio -----------------------------------------------------------

    def _vivo(self, id_: int) -> ItemLista:
        """O item, se ainda está na lista; 409 com ele, se o outro o tirou."""
        item = self.get(id_)
        if item.deleted_em is not None:
            raise Conflito(
                f'"{item.produto.nome}" foi tirado da lista.',
                {"item": ItemLeitura.de(item).model_dump(mode="json")},
            )
        return item

    def _aguardando_vivo(self, id_: int) -> ItemLista:
        """O item comprado que ainda espera nota; senão, 409 com ele."""
        item = self._vivo(id_)
        corpo = {"item": ItemLeitura.de(item).model_dump(mode="json")}
        if item.situacao != SituacaoItem.COMPRADO:
            raise Conflito(f'"{item.produto.nome}" não está comprado.', corpo)
        if item.fechamento is not None:
            raise Conflito(f'"{item.produto.nome}" já está fechado ({item.fechamento}).', corpo)
        return item

    @staticmethod
    def _aguardando() -> tuple[Any, ...]:
        return (
            ItemLista.deleted_em.is_(None),
            ItemLista.situacao == SituacaoItem.COMPRADO,
            ItemLista.fechamento.is_(None),
        )

    def _ordenada(self) -> Any:
        return (
            select(ItemLista)
            .join(Produto, Produto.id == ItemLista.produto_id)
            .join(Secao, Secao.id == Produto.secao_id)
            .order_by(ItemLista.situacao, Secao.ordem, Produto.nome_normalizado, ItemLista.id)
        )

    def pendente(self, produto_id: int) -> ItemLista | None:
        """O item pendente do produto, se houver (no máximo um: único parcial)."""
        return self._pendente(produto_id)

    def _pendente(self, produto_id: int) -> ItemLista | None:
        return self.session.scalar(
            select(ItemLista)
            .where(
                ItemLista.produto_id == produto_id,
                ItemLista.situacao == SituacaoItem.PENDENTE,
                ItemLista.deleted_em.is_(None),
            )
            .execution_options(populate_existing=True)
        )

    def _por_id_cliente(self, id_cliente: uuid.UUID) -> ItemLista | None:
        return self.session.scalar(
            select(ItemLista)
            .where(ItemLista.id_cliente == id_cliente)
            .execution_options(populate_existing=True)
        )
