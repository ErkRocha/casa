"""Service de regras de categorização (D-09).

As regras nascem sozinhas quando o usuário corrige um item na revisão, mas
precisam ser visíveis e editáveis: uma regra errada erra em silêncio para
sempre, e regra que ninguém enxerga não dá para consertar.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RegraCategorizacao
from app.schemas.common import Paginacao
from app.services.base import CrudService, RegraViolada

TIPOS_MATCH = {"contem", "regex", "exato"}


class RegraService(CrudService[RegraCategorizacao]):
    model = RegraCategorizacao
    nome_recurso = "regra de categorização"

    def criar(self, dados: dict[str, Any]) -> RegraCategorizacao:
        self._validar(dados)
        return super().criar(dados)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> RegraCategorizacao:
        atual = self.get(id_)
        self._validar({**self._como_dict(atual), **dados})
        return super().atualizar(id_, dados)

    def listar_ordenado(self, paginacao: Paginacao) -> tuple[list[RegraCategorizacao], int]:
        """Na ordem em que rodam: prioridade primeiro, depois o que mais acerta."""
        base = self._base_query()
        total = self.session.scalar(select(func.count()).select_from(base.subquery()))
        itens = list(
            self.session.scalars(
                base.order_by(
                    RegraCategorizacao.prioridade,
                    RegraCategorizacao.acertos.desc(),
                    RegraCategorizacao.id,
                )
                .limit(paginacao.limit)
                .offset(paginacao.offset)
            )
        )
        return itens, int(total or 0)

    def testar(self, padrao: str, tipo_match: str, texto: str) -> bool:
        """Prévia do casamento, para a tela não virar tentativa e erro."""
        return _casa(padrao, tipo_match, texto)

    # -- validação -------------------------------------------------------

    def _validar(self, dados: dict[str, Any]) -> None:
        tipo = dados.get("tipo_match") or "contem"
        if tipo not in TIPOS_MATCH:
            raise RegraViolada(f"tipo_match tem que ser um de {sorted(TIPOS_MATCH)}.")

        padrao = (dados.get("padrao") or "").strip()
        if not padrao:
            raise RegraViolada("A regra precisa de um padrão.")

        if tipo == "regex":
            # Regex inválida cadastrada aqui viraria erro silencioso no meio
            # da próxima importação; melhor recusar agora.
            try:
                re.compile(padrao)
            except re.error as exc:
                raise RegraViolada(f"Expressão regular inválida: {exc}") from exc

        if not any(dados.get(campo) for campo in ("categoria_id", "local_id", "pessoa_id")):
            raise RegraViolada("A regra tem que aplicar alguma coisa: categoria, local ou pessoa.")

    @staticmethod
    def _como_dict(regra: RegraCategorizacao) -> dict[str, Any]:
        return {
            "padrao": regra.padrao,
            "tipo_match": regra.tipo_match,
            "categoria_id": regra.categoria_id,
            "local_id": regra.local_id,
            "pessoa_id": regra.pessoa_id,
        }


def _casa(padrao: str, tipo_match: str, texto: str) -> bool:
    from app.ingestao.base import sem_acento

    alvo = sem_acento(texto).upper()
    limpo = sem_acento(padrao).upper()

    if tipo_match == "exato":
        return alvo == limpo
    if tipo_match == "regex":
        try:
            return re.search(padrao, alvo, re.I) is not None
        except re.error:
            return False
    return limpo in alvo


def contar_por_origem(session: Session) -> dict[str, int]:
    """Quantas regras vieram de correção automática e quantas foram na mão."""
    linhas = session.execute(
        select(RegraCategorizacao.criada_por, func.count())
        .where(RegraCategorizacao.deleted_em.is_(None))
        .group_by(RegraCategorizacao.criada_por)
    ).all()
    return {str(linha[0]): int(linha[1]) for linha in linhas}


def reforcar_regra(
    session: Session, padrao: str, categoria_id: int | None, pessoa_id: int | None
) -> None:
    """Correção vira regra, ou reforça a que já existe (D-09).

    Serve à revisão e, desde a D-21, à edição de categoria na tela de
    transações: as duas são o usuário dizendo "isto é aquilo", e as duas têm
    que ensinar a próxima importação. `padrao` vazio (linha sem trecho
    estável) não vira regra.
    """
    if not padrao:
        return

    existente = session.scalar(
        select(RegraCategorizacao).where(
            func.lower(RegraCategorizacao.padrao) == padrao.lower(),
            RegraCategorizacao.tipo_match == "contem",
            RegraCategorizacao.deleted_em.is_(None),
        )
    )
    if existente is not None:
        existente.categoria_id = categoria_id
        existente.pessoa_id = pessoa_id
        existente.acertos += 1
        return

    session.add(
        RegraCategorizacao(
            padrao=padrao,
            tipo_match="contem",
            categoria_id=categoria_id,
            pessoa_id=pessoa_id,
            criada_por="correcao_automatica",
        )
    )
