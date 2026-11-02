"""Schemas da sincronização (D-24)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ExecucaoSync(BaseModel):
    """A sync disparada pelo "Atualizar agora", neste processo da API."""

    #: nunca | rodando | ok | erro | ocupada (outra sync estava rodando).
    situacao: Literal["nunca", "rodando", "ok", "erro", "ocupada"]
    iniciada_em: datetime | None
    terminada_em: datetime | None
    itens_novos: int
    promovidos: int
    na_revisao: int
    importacao_id: int | None
    #: Por que falhou, ou o erro de alguma conta numa execução que terminou.
    erro: str | None


class EstadoSincronizacao(BaseModel):
    #: O `ultimo_sync_em` mais recente entre os mapeamentos ativos.
    ultima_atualizacao: datetime | None
    #: Mapeamentos de conta da Pluggy ativos.
    conexoes_ativas: int
    #: A sync roda sozinha (há agenda, `SYNC_AGENDA`)? Fase 5b, passo 10.
    automatica: bool
    #: Quando roda a próxima, se `automatica`; senão nulo.
    proxima_execucao: datetime | None = None
    #: Dá para disparar pelo painel (as credenciais da Pluggy existem)?
    pode_atualizar: bool = False
    #: A última disparada pelo painel.
    execucao: ExecucaoSync | None = None


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
