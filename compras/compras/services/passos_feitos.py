"""Passos do roteiro marcados como feitos (D-30).

O roteiro é calculado; esta tabela só guarda o que o casal concluiu, por sessão
de preparo e receita. Linha viva é passo feito; desfazer é soft delete, e é
assim que a marcação chega ao outro celular, pelo `/mudancas`.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.models import PassoFeito, Receita, SessaoPreparo
from compras.services.base import Conflito, NaoEncontrado


class PassoFeitoService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    def marcar(
        self, sessao_id: int, receita_id: int, id_cliente: uuid.UUID
    ) -> tuple[PassoFeito, bool]:
        """(passo, marcado agora). Já feito, ou o mesmo `id_cliente`: devolve o que existe."""
        self._exigir_existentes(sessao_id, receita_id)
        vivo = self._vivo(sessao_id, receita_id)
        if vivo is not None:
            return vivo, False  # vale o primeiro a marcar

        anterior = self.session.scalar(
            select(PassoFeito)
            .where(PassoFeito.id_cliente == id_cliente)
            .execution_options(populate_existing=True)
        )
        if anterior is not None:
            if (anterior.sessao_id, anterior.receita_id) != (sessao_id, receita_id):
                raise Conflito("Esse id_cliente já foi usado em outro passo.")
            # O mesmo pedido de uma marcação que já foi desfeita: marca de novo.
            anterior.deleted_em = None
            anterior.feito_por = self.quem
            anterior.feito_em = func.now()
            return self._gravar(anterior, sessao_id, receita_id, novo=False)

        passo = PassoFeito(
            sessao_id=sessao_id,
            receita_id=receita_id,
            feito_por=self.quem,
            feito_em=func.now(),
            id_cliente=id_cliente,
        )
        return self._gravar(passo, sessao_id, receita_id, novo=True)

    def desfazer(self, sessao_id: int, receita_id: int) -> PassoFeito | None:
        """Soft delete. Não feito: não muda nada e devolve `None`."""
        passo = self._vivo(sessao_id, receita_id)
        if passo is None:
            return None
        passo.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(passo)
        return passo

    def vivos(self, sessao_ids: list[int]) -> dict[tuple[int, int], PassoFeito]:
        """Os passos feitos das sessões, por (sessão, receita)."""
        if not sessao_ids:
            return {}
        linhas = self.session.scalars(
            select(PassoFeito)
            .where(PassoFeito.sessao_id.in_(sessao_ids), PassoFeito.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        return {(p.sessao_id, p.receita_id): p for p in linhas}

    # -- apoio -----------------------------------------------------------

    def _vivo(self, sessao_id: int, receita_id: int) -> PassoFeito | None:
        return self.session.scalar(
            select(PassoFeito)
            .where(
                PassoFeito.sessao_id == sessao_id,
                PassoFeito.receita_id == receita_id,
                PassoFeito.deleted_em.is_(None),
            )
            .execution_options(populate_existing=True)
        )

    def _exigir_existentes(self, sessao_id: int, receita_id: int) -> None:
        sessao = self.session.scalar(
            select(SessaoPreparo.id).where(
                SessaoPreparo.id == sessao_id, SessaoPreparo.deleted_em.is_(None)
            )
        )
        if sessao is None:
            raise NaoEncontrado("sessão de preparo", sessao_id)
        receita = self.session.scalar(
            select(Receita.id).where(Receita.id == receita_id, Receita.deleted_em.is_(None))
        )
        if receita is None:
            raise NaoEncontrado("receita", receita_id)

    def _gravar(
        self, passo: PassoFeito, sessao_id: int, receita_id: int, novo: bool
    ) -> tuple[PassoFeito, bool]:
        try:
            with self.session.begin_nested():
                if novo:
                    self.session.add(passo)
                self.session.flush()
        except IntegrityError:
            # Outro celular marcou entre a leitura e a escrita: vale o primeiro.
            self.session.expire_all()
            vivo = self._vivo(sessao_id, receita_id)
            if vivo is None:
                raise
            return vivo, False
        self.session.refresh(passo)
        return passo, True
