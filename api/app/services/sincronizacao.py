"""Estado da sincronização com a Pluggy, para o painel (D-22).

Só leitura. A sync roda pelo `make sync`; o agendamento (fase 5b, passo 10)
ainda não existe, e a resposta diz isso em vez de inventar uma próxima
execução.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ContaPluggy
from app.schemas.sincronizacao import EstadoSincronizacao


class SincronizacaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def estado(self) -> EstadoSincronizacao:
        ultima, ativas = self.session.execute(
            select(func.max(ContaPluggy.ultimo_sync_em), func.count()).where(
                ContaPluggy.deleted_em.is_(None), ContaPluggy.ativo.is_(True)
            )
        ).one()
        return EstadoSincronizacao(
            ultima_atualizacao=ultima, conexoes_ativas=int(ativas or 0), automatica=False
        )
