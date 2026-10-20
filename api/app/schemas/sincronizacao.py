"""Schemas da sincronização (D-22)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class EstadoSincronizacao(BaseModel):
    #: O `ultimo_sync_em` mais recente entre os mapeamentos ativos.
    ultima_atualizacao: datetime | None
    #: Mapeamentos de conta da Pluggy ativos.
    conexoes_ativas: int
    #: A sync roda sozinha? Hoje não: o agendamento é a fase 5b, passo 10.
    automatica: bool


class LinhaHistorico(BaseModel):
    """Uma importação: sync da Pluggy ou PDF."""

    importacao_id: int
    criado_em: datetime
    origem: str | None
    parser_usado: str | None
    arquivo_nome: str
    total_itens: int
    #: Viraram transação (sozinhos ou aprovados na revisão).
    entraram: int
    #: Ainda esperando decisão.
    revisar: int
    situacao: Literal["concluida", "com_pendencias", "nada_novo", "desfeita"]
    pode_desfazer: bool
