"""Service de transações: listagem filtrada, escrita e ação em lote.

Todo filtro e toda soma acontecem no banco (D-14). Nada aqui traz linha para
a memória só para contar ou somar.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    Select,
    Text,
    and_,
    func,
    or_,
    select,
    update,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import TipoTransacao
from app.models import Transacao
from app.schemas.common import Paginacao
from app.schemas.transacoes import TransacaoFiltros
from app.services.base import Conflito, NaoEncontrado, _mensagem_integridade
from app.services.cadastros import primeiro_dia_do_mes
from app.services.ingestao import _padrao_de
from app.services.regras import reforcar_regra
from app.views import vw_transacoes_completa as V

#: Chave do balde conjunto nas agregações e no filtro.
BALDE_CONJUNTO = "conjunto"

#: Marca "pessoa não muda" no lote — `None` já quer dizer conjunto (D-03).
_SEM_TROCA = object()


def _aprende_categoria(
    transacao: Transacao, categoria_nova: int | None, tipo: TipoTransacao | None
) -> bool:
    """A edição ensina uma regra? Só categoria que muda, em linha de extrato.

    Lançamento manual não tem `descricao_original` e não vira padrão;
    transferência não tem categoria.
    """
    return (
        categoria_nova is not None
        and categoria_nova != transacao.categoria_id
        and bool(transacao.descricao_original)
        and tipo is not TipoTransacao.TRANSFERENCIA
    )


def montar_filtros(f: TransacaoFiltros) -> list[ColumnElement[bool]]:
    """Traduz o filtro da tela em predicados SQL.

    A mesma função serve a listagem e ao analytics — é o que faz "filtros
    compartilhados com a tela de transações" ser verdade e não coincidência.
    """
    where: list[ColumnElement[bool]] = []

    if f.data_inicio is not None:
        where.append(V.c.data >= f.data_inicio)
    if f.data_fim is not None:
        where.append(V.c.data <= f.data_fim)
    if f.competencia_inicio is not None:
        where.append(V.c.competencia >= primeiro_dia_do_mes(f.competencia_inicio))
    if f.competencia_fim is not None:
        where.append(V.c.competencia <= primeiro_dia_do_mes(f.competencia_fim))

    if f.categoria_ids:
        # Aceita id de raiz ou de folha: marcar "Alimentação" tem que trazer
        # também "Alimentação › Mercado".
        where.append(
            or_(
                V.c.categoria_id.in_(f.categoria_ids),
                V.c.categoria_raiz_id.in_(f.categoria_ids),
            )
        )

    if f.pessoa is not None:
        if f.pessoa == BALDE_CONJUNTO:
            where.append(V.c.pessoa_id.is_(None))
        else:
            where.append(V.c.pessoa_id == f.pessoa)

    if f.forma_pagamento_ids:
        where.append(V.c.forma_pagamento_id.in_(f.forma_pagamento_ids))

    if f.tipos:
        where.append(V.c.tipo.in_(f.tipos))

    if f.local:
        where.append(V.c.local_nome.ilike(f"%{f.local}%"))

    if f.valor_min is not None:
        where.append(V.c.valor >= f.valor_min)
    if f.valor_max is not None:
        where.append(V.c.valor <= f.valor_max)

    if f.texto:
        alvo = f"%{f.texto}%"
        where.append(
            or_(
                V.c.descricao.ilike(alvo),
                V.c.local_nome.ilike(alvo),
                V.c.categoria_caminho.ilike(alvo),
            )
        )

    return where


class TransacaoService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- leitura ---------------------------------------------------------

    def listar(
        self, filtros: TransacaoFiltros, paginacao: Paginacao
    ) -> tuple[list[dict[str, Any]], int]:
        where = montar_filtros(filtros)

        total = self.session.scalar(select(func.count()).select_from(V).where(and_(True, *where)))

        # Mais recente primeiro; `id` desempata para a paginação ser estável
        # quando várias transações caem no mesmo dia.
        base: Select[Any] = (
            select(V)
            .where(and_(True, *where))
            .order_by(V.c.data.desc(), V.c.id.desc())
            .limit(paginacao.limit)
            .offset(paginacao.offset)
        )
        linhas = self.session.execute(base).mappings()

        return [dict(linha) for linha in linhas], int(total or 0)

    def totais(self, filtros: TransacaoFiltros) -> dict[str, Any]:
        """Rodapé da tabela.

        Transferência fica fora: pagar fatura não é despesa nova (D-05).
        """
        where = montar_filtros(filtros)
        sem_transferencia = V.c.tipo != TipoTransacao.TRANSFERENCIA

        agregado = self.session.execute(
            select(
                func.coalesce(
                    func.sum(V.c.valor).filter(V.c.tipo == TipoTransacao.DESPESA), 0
                ).label("despesa"),
                func.coalesce(
                    func.sum(V.c.valor).filter(V.c.tipo == TipoTransacao.RECEITA), 0
                ).label("receita"),
            ).where(and_(True, *where, sem_transferencia))
        ).one()

        # Os três baldes somam o total exato, sem sobreposição (D-03).
        balde = func.coalesce(sql_cast(V.c.pessoa_id, Text), BALDE_CONJUNTO).label("balde")
        baldes = self.session.execute(
            select(balde, func.coalesce(func.sum(V.c.valor), 0).label("total"))
            .where(and_(True, *where, V.c.tipo == TipoTransacao.DESPESA))
            .group_by(balde)
        ).all()

        despesa = Decimal(agregado.despesa)
        receita = Decimal(agregado.receita)
        return {
            "total_despesa": despesa,
            "total_receita": receita,
            "resultado": receita - despesa,
            "por_balde": {str(linha.balde): Decimal(linha.total) for linha in baldes},
        }

    def get(self, id_: int) -> dict[str, Any]:
        linha = self.session.execute(select(V).where(V.c.id == id_)).mappings().first()
        if linha is None:
            raise NaoEncontrado("transação", id_)
        return dict(linha)

    # -- escrita ---------------------------------------------------------

    def criar(self, dados: dict[str, Any]) -> dict[str, Any]:
        # Sem competência explícita, vale o mês da data do fato (D-02).
        if dados.get("competencia") is None:
            dados["competencia"] = primeiro_dia_do_mes(dados["data"])
        else:
            dados["competencia"] = primeiro_dia_do_mes(dados["competencia"])

        obj = Transacao(**dados)
        self.session.add(obj)
        self._flush()
        return self.get(obj.id)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> dict[str, Any]:
        obj = self.session.get(Transacao, id_)
        if obj is None or obj.deleted_em is not None:
            raise NaoEncontrado("transação", id_)

        if "competencia" in dados and dados["competencia"] is not None:
            dados["competencia"] = primeiro_dia_do_mes(dados["competencia"])

        aprender = _aprende_categoria(obj, dados.get("categoria_id"), dados.get("tipo", obj.tipo))
        for campo, valor in dados.items():
            setattr(obj, campo, valor)
        if aprender and obj.descricao_original:
            # D-09, estendida pela D-21: corrigir aqui ensina a próxima
            # importação, como corrigir na revisão.
            reforcar_regra(
                self.session, _padrao_de(obj.descricao_original), obj.categoria_id, obj.pessoa_id
            )
        self._flush()
        return self.get(id_)

    def remover(self, id_: int) -> None:
        obj = self.session.get(Transacao, id_)
        if obj is None:
            raise NaoEncontrado("transação", id_)
        if obj.deleted_em is not None:
            return
        obj.deleted_em = func.now()
        self._flush()

    # -- ação em lote ----------------------------------------------------

    def atribuir_em_lote(
        self,
        ids: Sequence[int],
        categoria_id: int | None,
        pessoa: str | int | None,
    ) -> int:
        """Aplica categoria e/ou pessoa a várias transações de uma vez.

        UPDATE único no banco. Os triggers de auditoria e de `atualizado_em`
        disparam por linha, então o histórico fica igual ao da edição
        individual.
        """
        valores: dict[str, Any] = {}
        if categoria_id is not None:
            valores["categoria_id"] = categoria_id
        if pessoa is not None:
            # `conjunto` limpa o dono — é `NULL`, não uma pessoa chamada
            # "conjunto" (D-03).
            valores["pessoa_id"] = None if pessoa == BALDE_CONJUNTO else int(pessoa)

        if not valores:
            return 0

        if categoria_id is not None:
            self._aprender_em_lote(ids, categoria_id, valores.get("pessoa_id", _SEM_TROCA))

        stmt = (
            update(Transacao)
            .where(Transacao.id.in_(ids), Transacao.deleted_em.is_(None))
            .values(**valores)
        )
        try:
            resultado = self.session.execute(stmt)
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflito(_mensagem_integridade(exc)) from exc

        return int(cast(CursorResult[Any], resultado).rowcount or 0)

    def remover_em_lote(self, ids: Sequence[int]) -> int:
        """Soft delete em lote. Nunca DELETE físico (regra 2)."""
        stmt = (
            update(Transacao)
            .where(Transacao.id.in_(ids), Transacao.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        resultado = self.session.execute(stmt)
        return int(cast(CursorResult[Any], resultado).rowcount or 0)

    def _aprender_em_lote(self, ids: Sequence[int], categoria_id: int, pessoa: object) -> None:
        """Cada transação do lote que muda de categoria ensina uma regra (D-09).

        Antes do UPDATE, para comparar com a categoria antiga. Várias linhas
        do mesmo estabelecimento caem na mesma regra, que é reforçada.
        """
        for transacao in self.session.scalars(
            select(Transacao)
            .where(Transacao.id.in_(ids), Transacao.deleted_em.is_(None))
            .order_by(Transacao.id)
        ):
            if not _aprende_categoria(transacao, categoria_id, transacao.tipo):
                continue
            pessoa_id = transacao.pessoa_id if pessoa is _SEM_TROCA else pessoa
            reforcar_regra(
                self.session,
                _padrao_de(transacao.descricao_original or ""),
                categoria_id,
                cast(int | None, pessoa_id),
            )

    # -- utilidades ------------------------------------------------------

    def competencias_disponiveis(self) -> list[date]:
        """Meses que têm lançamento — alimenta o seletor de período."""
        return list(
            self.session.scalars(
                select(V.c.competencia).distinct().order_by(V.c.competencia.desc())
            )
        )

    def _flush(self) -> None:
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflito(_mensagem_integridade(exc)) from exc
