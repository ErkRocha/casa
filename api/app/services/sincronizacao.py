"""Estado da sincronização com a Pluggy, para o painel (D-22).

Só leitura. A sync roda pelo `make sync`; o agendamento (fase 5b, passo 10)
ainda não existe, e a resposta diz isso em vez de inventar uma próxima
execução.
"""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import ContaPluggy
from app.schemas.sincronizacao import EstadoSincronizacao, LinhaHistorico

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

    def historico(self, dias: int) -> list[LinhaHistorico]:
        """As importações dos últimos `dias`, mais recente primeiro."""
        return [
            LinhaHistorico.model_validate(dict(linha._mapping))
            for linha in self.session.execute(text(_HISTORICO), {"dias": dias})
        ]
