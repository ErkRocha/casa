"""Limpeza dos dados de PDF dentro da janela da Pluggy (fase 5b, passo 7).

Pré-requisito da primeira sync (D-16). Sem ela, o mesmo gasto apareceria
duas vezes — uma pelo PDF, outra pela Pluggy —, com descrições diferentes que
o `hash_dedup` não une.

- **Escopo:** só o que veio de PDF, de uma origem de parser ligada
  explicitamente a um mapeamento da Pluggy, e com data igual ou posterior ao
  `sincronizar_desde` dele. O anterior fica: é o único registro do período.
- **Como achar a conta:** pela origem do parser, não pela conta da
  transação — o PDF gravou nas formas do seed, não nas contas novas. Origem
  sem correspondência não é tocada.
- **O quê:** soft delete das transações promovidas e dos itens de staging,
  com `app.autor = 'limpeza_pdf'` (D-06). A importação fica, com o PDF;
  vira `cancelada` quando não sobra item vivo nela.
- **Simulação** conta tudo e não grava. Rodar de novo não muda nada.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.enums import StatusImportacao
from app.models import ContaPluggy, Importacao, ImportacaoItem, Transacao
from app.services.base import RegraViolada

AUTOR = "limpeza_pdf"


@dataclass(slots=True)
class ResultadoOrigem:
    origem: str
    mapeamento_id: int
    rotulo: str
    corte: date
    transacoes: int = 0
    itens: int = 0
    itens_por_status: Counter[str] = field(default_factory=Counter)
    importacoes_canceladas: list[int] = field(default_factory=list)
    #: Antes do corte: ficam, são o único registro do período.
    transacoes_preservadas: int = 0
    itens_preservados: int = 0


@dataclass(slots=True)
class ResultadoLimpeza:
    simulado: bool
    origens: list[ResultadoOrigem] = field(default_factory=list)
    #: Origens de PDF com dado vivo e sem correspondência: não tocadas.
    nao_tocadas: list[str] = field(default_factory=list)

    @property
    def transacoes(self) -> int:
        return sum(o.transacoes for o in self.origens)

    @property
    def itens(self) -> int:
        return sum(o.itens for o in self.origens)


class LimpezaPdfService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def limpar(
        self, correspondencia: Mapping[str, int], *, simular: bool = True
    ) -> ResultadoLimpeza:
        """`correspondencia`: origem do parser -> id do mapeamento da Pluggy."""
        if "pluggy" in correspondencia:
            raise RegraViolada("A origem 'pluggy' não é PDF e nunca entra na limpeza.")

        resultado = ResultadoLimpeza(simulado=simular)
        mapas = {origem: self._mapeamento(id_) for origem, id_ in correspondencia.items()}
        if not simular:
            self.session.execute(
                text("SELECT set_config('app.autor', :autor, true)"), {"autor": AUTOR}
            )

        for origem, mapa in mapas.items():
            resultado.origens.append(self._limpar_origem(origem, mapa, simular))

        origens_vivas: set[str | None] = set(
            self.session.scalars(
                select(Importacao.origem)
                .join(ImportacaoItem, ImportacaoItem.importacao_id == Importacao.id)
                .where(
                    Importacao.deleted_em.is_(None),
                    ImportacaoItem.deleted_em.is_(None),
                    Importacao.origem.is_distinct_from("pluggy"),
                )
            )
        )
        resultado.nao_tocadas = sorted(
            o for o in origens_vivas if o is not None and o not in correspondencia
        )
        self.session.flush()
        return resultado

    def _mapeamento(self, id_: int) -> ContaPluggy:
        mapa = self.session.get(ContaPluggy, id_)
        if mapa is None or mapa.deleted_em is not None or not mapa.ativo:
            raise RegraViolada(f"Mapeamento {id_} não existe ou está desativado.")
        return mapa

    def _limpar_origem(self, origem: str, mapa: ContaPluggy, simular: bool) -> ResultadoOrigem:
        corte = mapa.sincronizar_desde
        r = ResultadoOrigem(
            origem=origem,
            mapeamento_id=mapa.id,
            rotulo=f"{mapa.conta.nome} / {mapa.forma_pagamento.apelido}",
            corte=corte,
        )
        importacoes = select(Importacao.id).where(
            Importacao.origem == origem, Importacao.deleted_em.is_(None)
        )

        itens = list(
            self.session.scalars(
                select(ImportacaoItem).where(
                    ImportacaoItem.importacao_id.in_(importacoes),
                    ImportacaoItem.deleted_em.is_(None),
                    ImportacaoItem.data >= corte,
                )
            )
        )
        transacoes = list(
            self.session.scalars(
                select(Transacao).where(
                    Transacao.importacao_id.in_(importacoes),
                    Transacao.deleted_em.is_(None),
                    Transacao.data >= corte,
                )
            )
        )
        r.itens, r.transacoes = len(itens), len(transacoes)
        r.itens_por_status = Counter(i.status.value for i in itens)
        r.itens_preservados = int(
            self.session.scalar(
                select(func.count()).where(
                    ImportacaoItem.importacao_id.in_(importacoes),
                    ImportacaoItem.deleted_em.is_(None),
                    ImportacaoItem.data < corte,
                )
            )
            or 0
        )
        r.transacoes_preservadas = int(
            self.session.scalar(
                select(func.count()).where(
                    Transacao.importacao_id.in_(importacoes),
                    Transacao.deleted_em.is_(None),
                    Transacao.data < corte,
                )
            )
            or 0
        )

        removidos_por_importacao = Counter(i.importacao_id for i in itens)
        vivos_por_importacao: dict[int, int] = {
            id_: total
            for id_, total in self.session.execute(
                select(ImportacaoItem.importacao_id, func.count())
                .where(
                    ImportacaoItem.importacao_id.in_(list(removidos_por_importacao)),
                    ImportacaoItem.deleted_em.is_(None),
                )
                .group_by(ImportacaoItem.importacao_id)
            ).tuples()
        }
        r.importacoes_canceladas = sorted(
            id_
            for id_, removidos in removidos_por_importacao.items()
            if vivos_por_importacao.get(id_, 0) == removidos
        )

        if simular:
            return r

        for transacao in transacoes:
            transacao.deleted_em = func.now()
        for item in itens:
            item.deleted_em = func.now()
        for id_ in r.importacoes_canceladas:
            importacao = self.session.get(Importacao, id_)
            if importacao is not None:
                importacao.status = StatusImportacao.CANCELADA
        self.session.flush()
        return r
