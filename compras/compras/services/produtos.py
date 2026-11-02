"""Produtos canônicos: busca enquanto se digita, criação idempotente."""

import uuid
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.enums import SituacaoItem
from compras.models import Despensa, ItemLista, Produto
from compras.normalizar import normalizar
from compras.schemas import ProdutoLeitura
from compras.services.base import Conflito, NaoEncontrado
from compras.services.secoes import SecaoService


class ProdutoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def buscar(self, busca: str | None, limite: int) -> list[Produto]:
        """Contém o texto, sem caixa nem acento; quem começa com ele vem antes,
        depois os mais comprados. A contagem é do banco (regra 10)."""
        compras = (
            select(ItemLista.produto_id, func.count().label("vezes"))
            .where(ItemLista.situacao == SituacaoItem.COMPRADO, ItemLista.deleted_em.is_(None))
            .group_by(ItemLista.produto_id)
            .subquery()
        )
        consulta = (
            select(Produto)
            .outerjoin(compras, compras.c.produto_id == Produto.id)
            .where(Produto.deleted_em.is_(None))
        )
        ordem: list[Any] = []
        termo = normalizar(busca or "")
        if termo:
            consulta = consulta.where(Produto.nome_normalizado.contains(termo, autoescape=True))
            ordem.append(
                case((Produto.nome_normalizado.startswith(termo, autoescape=True), 0), else_=1)
            )
        ordem += [func.coalesce(compras.c.vezes, 0).desc(), Produto.nome_normalizado]
        return list(self.session.scalars(consulta.order_by(*ordem).limit(limite)))

    def get(self, id_: int) -> Produto:
        produto = self.session.scalar(
            select(Produto).where(Produto.id == id_, Produto.deleted_em.is_(None))
        )
        if produto is None:
            raise NaoEncontrado("produto", id_)
        return produto

    def criar(
        self,
        nome: str,
        id_cliente: uuid.UUID,
        secao_id: int | None = None,
        unidade_padrao: str | None = None,
    ) -> tuple[Produto, bool]:
        """(produto, criado agora). Reenvio do mesmo `id_cliente` devolve o mesmo."""
        existente = self._por_id_cliente(id_cliente)
        if existente is not None:
            return existente, False

        normalizado = normalizar(nome)
        mesmo_nome = self._por_nome(normalizado)
        if mesmo_nome is not None:
            raise Conflito(
                f'Já existe o produto "{mesmo_nome.nome}".',
                {"produto": ProdutoLeitura.de(mesmo_nome).model_dump(mode="json")},
            )
        secoes = SecaoService(self.session)
        secao = secoes.get(secao_id) if secao_id is not None else secoes.sem_secao()

        produto = Produto(
            nome=nome,
            nome_normalizado=normalizado,
            secao_id=secao.id,
            unidade_padrao=unidade_padrao,
            id_cliente=id_cliente,
        )
        try:
            with self.session.begin_nested():
                self.session.add(produto)
                self.session.flush()
        except IntegrityError as erro:
            # O mesmo pedido chegou duas vezes ao mesmo tempo.
            repetido = self._por_id_cliente(id_cliente)
            if repetido is not None:
                return repetido, False
            raise Conflito(f'Já existe o produto "{nome}".') from erro
        return produto, True

    def obter_ou_criar(self, nome: str) -> Produto:
        """Pelo nome, sem caixa nem acento; senão cria em "Sem seção".

        `ON CONFLICT DO NOTHING`: os dois digitando o mesmo produto novo ao
        mesmo tempo dão um produto só.
        """
        normalizado = normalizar(nome)
        produto = self._por_nome(normalizado)
        if produto is not None:
            return produto
        secao = SecaoService(self.session).sem_secao()
        self.session.execute(
            insert(Produto)
            .values(nome=nome, nome_normalizado=normalizado, secao_id=secao.id)
            .on_conflict_do_nothing()
        )
        produto = self._por_nome(normalizado)
        assert produto is not None
        return produto

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Produto:
        produto = self.get(id_)
        if "secao_id" in dados and dados["secao_id"] is not None:
            produto.secao_id = SecaoService(self.session).get(dados["secao_id"]).id
        if dados.get("nome") is not None:
            produto.nome = dados["nome"]
            produto.nome_normalizado = normalizar(dados["nome"])
        if "unidade_padrao" in dados:
            produto.unidade_padrao = dados["unidade_padrao"]
        try:
            with self.session.begin_nested():
                self.session.flush()
        except IntegrityError as erro:
            raise Conflito(f'Já existe o produto "{produto.nome}".') from erro
        self.session.refresh(produto)
        return produto

    def remover(self, id_: int) -> Produto:
        """Soft delete do produto e da despensa dele. Recusa com item pendente."""
        produto = self.get(id_)
        pendente = self.session.scalar(
            select(ItemLista.id).where(
                ItemLista.produto_id == id_,
                ItemLista.situacao == SituacaoItem.PENDENTE,
                ItemLista.deleted_em.is_(None),
            )
        )
        if pendente is not None:
            raise Conflito(f'"{produto.nome}" está na lista; tire-o de lá antes.')
        self.session.execute(
            update(Despensa)
            .where(Despensa.produto_id == id_, Despensa.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        produto.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(produto)
        return produto

    def _por_nome(self, normalizado: str) -> Produto | None:
        return self.session.scalar(
            select(Produto).where(
                Produto.nome_normalizado == normalizado, Produto.deleted_em.is_(None)
            )
        )

    def _por_id_cliente(self, id_cliente: uuid.UUID) -> Produto | None:
        """Em qualquer estado, apagado inclusive: é a idempotência do POST."""
        return self.session.scalar(select(Produto).where(Produto.id_cliente == id_cliente))
