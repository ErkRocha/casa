"""Estado da sincronização com a Pluggy, para o painel (D-24).

A sync roda pelo `make sync`, pelo agendamento (fase 5b, passo 10) e pelo
"Atualizar agora" do painel, todos por `execucao_sync.executar`. A próxima
execução só aparece quando há agenda (`SYNC_AGENDA`); sem ela, a resposta
diz que a atualização é manual, em vez de inventar uma hora.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import ContaPluggy
from app.schemas.sincronizacao import EstadoSincronizacao, ExecucaoSync, LinhaHistorico
from app.services import execucao_sync
from app.services.execucao_sync import EmSegundoPlano, hora_da_agenda, proxima_execucao

#: As importações do período, com o que cada uma trouxe. Conta os itens
#: mesmo apagados: depois de desfeita, a linha mostra o que ela tinha trazido.
_HISTORICO = """
    SELECT
      i.id AS importacao_id,
      i.criado_em,
      i.origem,
      i.parser_usado,
      i.arquivo_nome,
      i.total_itens,
      count(it.id) FILTER (WHERE it.status = 'aprovado')::int AS entraram,
      count(it.id) FILTER (WHERE it.status = 'pendente' AND it.deleted_em IS NULL)::int
        AS revisar,
      CASE
        WHEN i.status = 'cancelada' THEN 'desfeita'
        WHEN i.total_itens = 0 THEN 'nada_novo'
        WHEN count(it.id) FILTER (WHERE it.status = 'pendente' AND it.deleted_em IS NULL) > 0
          THEN 'com_pendencias'
        ELSE 'concluida'
      END AS situacao,
      i.status <> 'cancelada' AND i.total_itens > 0 AS pode_desfazer
    FROM importacoes i
    LEFT JOIN importacao_itens it ON it.importacao_id = i.id
    WHERE i.deleted_em IS NULL
      AND i.criado_em >= now() - make_interval(days => :dias)
    GROUP BY i.id
    ORDER BY i.criado_em DESC, i.id DESC
"""


class SincronizacaoService:
    def __init__(
        self,
        session: Session,
        cfg: Settings | None = None,
        execucoes: EmSegundoPlano | None = None,
    ) -> None:
        self.session = session
        self.cfg = cfg or get_settings()
        # Lida na hora, não na definição: os testes trocam a instância.
        self.execucoes = execucoes or execucao_sync.em_segundo_plano

    def estado(self, agora: datetime | None = None) -> EstadoSincronizacao:
        ultima, ativas = self.session.execute(
            select(func.max(ContaPluggy.ultimo_sync_em), func.count()).where(
                ContaPluggy.deleted_em.is_(None), ContaPluggy.ativo.is_(True)
            )
        ).one()
        hora = hora_da_agenda(self.cfg.sync_agenda)
        proxima = proxima_execucao(agora or datetime.now(UTC), hora) if hora else None
        execucao = self.execucoes.estado()
        return EstadoSincronizacao(
            ultima_atualizacao=ultima,
            conexoes_ativas=int(ativas or 0),
            automatica=hora is not None,
            proxima_execucao=proxima,
            pode_atualizar=self.cfg.pluggy_habilitada,
            execucao=(
                ExecucaoSync.model_validate(asdict(execucao))
                if execucao.situacao != "nunca"
                else None
            ),
        )

    def atualizar_agora(self) -> EstadoSincronizacao:
        """Dispara a sync em segundo plano e volta na hora (`SyncDesligada`
        sem credenciais). Já rodando: devolve a execução em curso."""
        self.execucoes.iniciar(self.cfg)
        return self.estado()

    def historico(self, dias: int) -> list[LinhaHistorico]:
        """As importações dos últimos `dias`, mais recente primeiro."""
        return [
            LinhaHistorico.model_validate(dict(linha._mapping))
            for linha in self.session.execute(text(_HISTORICO), {"dias": dias})
        ]
