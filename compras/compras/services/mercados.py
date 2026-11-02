"""Mercados: saem da nota, pelo CNPJ."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.models import Mercado
from compras.services.base import NaoEncontrado


class MercadoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def listar(self) -> list[Mercado]:
        return list(
            self.session.scalars(
                select(Mercado).where(Mercado.deleted_em.is_(None)).order_by(Mercado.nome)
            )
        )

    def get(self, id_: int) -> Mercado:
        mercado = self.session.scalar(
            select(Mercado).where(Mercado.id == id_, Mercado.deleted_em.is_(None))
        )
        if mercado is None:
            raise NaoEncontrado("mercado", id_)
        return mercado

    def _por_cnpj(self, cnpj: str) -> Mercado | None:
        return self.session.scalar(
            select(Mercado).where(Mercado.cnpj == cnpj, Mercado.deleted_em.is_(None))
        )

    def por_cnpj(self, cnpj: str, nome_provisorio: str) -> Mercado:
        """O mercado do CNPJ, criado se ainda não existe.

        Duas notas do mesmo mercado lidas ao mesmo tempo não criam dois: o
        índice único decide, e quem perde lê o do outro.
        """
        existente = self._por_cnpj(cnpj)
        if existente is not None:
            return existente
        mercado = Mercado(nome=nome_provisorio, cnpj=cnpj)
        try:
            with self.session.begin_nested():
                self.session.add(mercado)
                self.session.flush()
        except IntegrityError:
            achado = self._por_cnpj(cnpj)
            if achado is None:
                raise
            return achado
        return mercado

    def completar(
        self,
        mercado: Mercado,
        razao_social: str | None,
        endereco: str | None,
        cidade: str | None,
        nome_provisorio: str,
    ) -> None:
        """Preenche o que a nota trouxe, sem sobrescrever o que já havia.

        O nome só troca se ainda é o provisório (o CNPJ formatado): o nome que
        o casal deu ("Zaffari da Ipiranga") não se perde.
        """
        if razao_social and mercado.nome == nome_provisorio:
            mercado.nome = razao_social
        mercado.razao_social = mercado.razao_social or razao_social
        mercado.endereco = mercado.endereco or endereco
        mercado.cidade = mercado.cidade or cidade

    def atualizar(self, id_: int, campos: dict[str, Any]) -> Mercado:
        mercado = self.get(id_)
        for chave, valor in campos.items():
            setattr(mercado, chave, valor)
        self.session.flush()
        return mercado
