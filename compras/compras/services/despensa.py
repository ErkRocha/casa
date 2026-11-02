"""Despensa: o que tem em casa, e o ciclo com a lista (modelo-dados.md).

| Acontece                         | Efeito                                          |
|----------------------------------|-------------------------------------------------|
| item comprado                    | despensa vai para `tem`, se acompanhado         |
| despensa vai para `acabou`       | cria item pendente (`origem = despensa`)        |
| despensa vai para `acabando`     | nada na lista; só sugestão (D-25)               |
| compra desfeita                  | despensa volta para `acabou`, se acompanhado    |

Tudo na transação de quem chamou: o item e a despensa mudam juntos ou não
mudam.
"""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from compras.enums import EstadoDespensa, OrigemItem, SituacaoItem
from compras.models import Despensa, ItemLista, Produto, Secao
from compras.services.base import NaoEncontrado
from compras.services.produtos import ProdutoService


class DespensaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    def listar(self, estado: EstadoDespensa | None = None) -> list[Despensa]:
        consulta = (
            select(Despensa)
            .join(Produto, Produto.id == Despensa.produto_id)
            .join(Secao, Secao.id == Produto.secao_id)
            .where(Despensa.deleted_em.is_(None))
            .order_by(Secao.ordem, Produto.nome_normalizado)
        )
        if estado is not None:
            consulta = consulta.where(Despensa.estado == estado)
        return list(self.session.scalars(consulta))

    def sugestoes(self) -> list[Despensa]:
        """ "Acabando em casa" que ainda não tem item pendente na lista."""
        pendente = (
            select(ItemLista.id)
            .where(
                ItemLista.produto_id == Despensa.produto_id,
                ItemLista.situacao == SituacaoItem.PENDENTE,
                ItemLista.deleted_em.is_(None),
            )
            .exists()
        )
        consulta = (
            select(Despensa)
            .join(Produto, Produto.id == Despensa.produto_id)
            .join(Secao, Secao.id == Produto.secao_id)
            .where(
                Despensa.deleted_em.is_(None),
                Despensa.estado == EstadoDespensa.ACABANDO,
                ~pendente,
            )
            .order_by(Secao.ordem, Produto.nome_normalizado)
        )
        return list(self.session.scalars(consulta))

    def definir(self, produto_id: int, estado: EstadoDespensa) -> tuple[Despensa, int | None]:
        """Muda o estado (e começa a acompanhar, se não acompanhava).

        Devolve a linha e o id do item que "acabou" pôs na lista, ou None.
        """
        ProdutoService(self.session).get(produto_id)
        alterada = self.session.execute(
            update(Despensa)
            .where(Despensa.produto_id == produto_id, Despensa.deleted_em.is_(None))
            .values(estado=estado, estado_por=self.quem, estado_em=func.now())
            .returning(Despensa.id)
        ).scalar()
        if alterada is None:
            # Os dois começando a acompanhar o mesmo produto ao mesmo tempo
            # esbarram no único parcial; quem chegou depois atualiza.
            criada = self.session.execute(
                insert(Despensa)
                .values(produto_id=produto_id, estado=estado, estado_por=self.quem)
                .on_conflict_do_nothing()
                .returning(Despensa.id)
            ).scalar()
            if criada is None:
                return self.definir(produto_id, estado)

        item_id = self._por_na_lista(produto_id) if estado == EstadoDespensa.ACABOU else None
        return self._viva(produto_id), item_id

    def remover(self, produto_id: int) -> Despensa:
        """Para de acompanhar (soft delete)."""
        linha = self.session.scalar(
            select(Despensa).where(Despensa.produto_id == produto_id, Despensa.deleted_em.is_(None))
        )
        if linha is None:
            raise NaoEncontrado("produto na despensa", produto_id)
        linha.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(linha)
        return linha

    def comprado(self, produto_id: int) -> None:
        """Comprou: em casa passa a ter. Só se o produto é acompanhado."""
        self._se_acompanhado(produto_id, EstadoDespensa.TEM)

    def compra_desfeita(self, produto_id: int) -> None:
        """A compra não aconteceu: o produto continua faltando."""
        self._se_acompanhado(produto_id, EstadoDespensa.ACABOU)

    def _se_acompanhado(self, produto_id: int, estado: EstadoDespensa) -> None:
        self.session.execute(
            update(Despensa)
            .where(
                Despensa.produto_id == produto_id,
                Despensa.deleted_em.is_(None),
                Despensa.estado != estado,
            )
            .values(estado=estado, estado_por=self.quem, estado_em=func.now())
        )

    def _por_na_lista(self, produto_id: int) -> int | None:
        """Item pendente de origem `despensa`, se ainda não houver um."""
        return self.session.execute(
            insert(ItemLista)
            .values(
                produto_id=produto_id,
                situacao=SituacaoItem.PENDENTE,
                origem=OrigemItem.DESPENSA,
                adicionado_por=self.quem,
            )
            .on_conflict_do_nothing()
            .returning(ItemLista.id)
        ).scalar()

    def _viva(self, produto_id: int) -> Despensa:
        linha = self.session.scalar(
            select(Despensa)
            .where(Despensa.produto_id == produto_id, Despensa.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        assert linha is not None
        return linha
