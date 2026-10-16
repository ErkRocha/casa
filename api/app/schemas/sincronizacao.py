"""Schemas da sincronização (D-22)."""

from datetime import datetime

from pydantic import BaseModel


class EstadoSincronizacao(BaseModel):
    #: O `ultimo_sync_em` mais recente entre os mapeamentos ativos.
    ultima_atualizacao: datetime | None
    #: Mapeamentos de conta da Pluggy ativos.
    conexoes_ativas: int
    #: A sync roda sozinha? Hoje não: o agendamento é a fase 5b, passo 10.
    automatica: bool
