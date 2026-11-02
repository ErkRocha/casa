"""Seções do mercado e a ordem do percurso (uma ordem só, D-25)."""

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.models import SEM_SECAO, Produto, Secao
from compras.services.base import Conflito, NaoEncontrado, RegraViolada


class SecaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar(self) -> list[Secao]:
        return list(
            self.session.scalars(
                select(Secao).where(Secao.deleted_em.is_(None)).order_by(Secao.ordem, Secao.id)
            )
        )

    def get(self, id_: int) -> Secao:
        secao = self.session.scalar(
            select(Secao).where(Secao.id == id_, Secao.deleted_em.is_(None))
        )
        if secao is None:
            raise NaoEncontrado("seção", id_)
        return secao

    def sem_secao(self) -> Secao:
        """A seção de quem não tem seção; criada na hora se o seed não rodou."""
        secao = self.session.scalar(
            select(Secao).where(
                func.lower(Secao.nome) == SEM_SECAO.lower(), Secao.deleted_em.is_(None)
            )
        )
        if secao is None:
            maior = self.session.scalar(
                select(func.max(Secao.ordem)).where(Secao.deleted_em.is_(None))
            )
            secao = Secao(nome=SEM_SECAO, ordem=(maior or 0) + 1)
            self.session.add(secao)
            self._flush(SEM_SECAO)
        return secao

    def criar(self, nome: str) -> Secao:
        """Entra no fim do percurso, antes de "Sem seção"."""
        sem = self.sem_secao()
        maior = self.session.scalar(
            select(func.max(Secao.ordem)).where(Secao.deleted_em.is_(None), Secao.id != sem.id)
        )
        ordem = (maior or 0) + 1
        if sem.ordem <= ordem:
            sem.ordem = ordem + 1
        secao = Secao(nome=nome, ordem=ordem)
        self.session.add(secao)
        self._flush(nome)
        return secao

    def renomear(self, id_: int, nome: str) -> Secao:
        secao = self._editavel(id_)
        secao.nome = nome
        self._flush(nome)
        return secao

    def reordenar(self, ids: list[int]) -> list[Secao]:
        secoes = {s.id: s for s in self.listar()}
        if len(ids) != len(set(ids)) or set(ids) != set(secoes):
            raise RegraViolada("A ordem nova precisa ter cada seção exatamente uma vez.")
        for posicao, id_ in enumerate(ids, start=1):
            secoes[id_].ordem = posicao
        self.session.flush()
        return self.listar()

    def remover(self, id_: int) -> Secao:
        """Soft delete; os produtos dela vão para "Sem seção"."""
        secao = self._editavel(id_)
        sem = self.sem_secao()
        self.session.execute(
            update(Produto)
            .where(Produto.secao_id == secao.id, Produto.deleted_em.is_(None))
            .values(secao_id=sem.id)
        )
        secao.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(secao)
        return secao

    def _editavel(self, id_: int) -> Secao:
        secao = self.get(id_)
        if secao.nome.lower() == SEM_SECAO.lower():
            raise RegraViolada(f'"{SEM_SECAO}" não pode ser renomeada nem removida.')
        return secao

    def _flush(self, nome: str) -> None:
        try:
            with self.session.begin_nested():
                self.session.flush()
        except IntegrityError as erro:
            raise Conflito(f'Já existe a seção "{nome}".') from erro
