"""Leitura dos relatórios para a tela (fase 6).

Só leitura, pela sessão normal da API. Gerar continua sendo o CLI no host
(`make relatorio`), pelo `RelatorioService` de `app.services.insights`, que
lê os números pela role read-only e grava com a credencial de aplicação.
Este módulo não importa nada do caminho de geração: a tela não precisa da
sessão read-only nem do harness para mostrar um texto já gravado.
"""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.insights.deteccoes import PROMPT_SEM_IA
from app.models import Relatorio
from app.schemas.common import Paginacao
from app.services.base import NaoEncontrado


def com_ia(relatorio: Relatorio) -> bool:
    """O texto foi escrito por modelo, ou saiu só dos números (seco)?"""
    return relatorio.prompt_versao != PROMPT_SEM_IA


class RelatorioLeituraService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _vivos(self) -> Select[tuple[Relatorio]]:
        return select(Relatorio).where(Relatorio.deleted_em.is_(None))

    def listar(self, paginacao: Paginacao) -> tuple[list[Relatorio], int]:
        """Mais recente primeiro: competência, depois a geração mais nova."""
        total = self.session.scalar(select(func.count()).select_from(self._vivos().subquery()))
        itens = list(
            self.session.scalars(
                self._vivos()
                .order_by(Relatorio.competencia.desc(), Relatorio.id.desc())
                .limit(paginacao.limit)
                .offset(paginacao.offset)
            )
        )
        return itens, int(total or 0)

    def get(self, id_: int) -> Relatorio:
        relatorio: Relatorio | None = self.session.scalar(self._vivos().where(Relatorio.id == id_))
        if relatorio is None:
            raise NaoEncontrado("relatório", id_)
        return relatorio
