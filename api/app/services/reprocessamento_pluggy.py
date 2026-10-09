"""Reprocessamento dos itens pendentes de uma importação da Pluggy (D-21).

A primeira sync gravou os itens antes da D-21: a forma de toda linha de conta
corrente era a do mapeamento (Pix), o enriquecimento não conhecia as
categorias da Pluggy e nada era promovido. Este service passa cada item
**pendente** pelo caminho de hoje — conversão, forma pela operação,
enriquecimento e o critério de promoção da sync — a partir do comprovante da
importação, que guarda a transação da Pluggy inteira.

Duas fases, como a sync: `planejar` só lê e diz o que aconteceria;
`executar` grava o plano (forma, categoria, observação) e promove os limpos
pelo mesmo `aprovar()` da revisão, com autor `reprocessamento_pluggy`.

O que não é tocado: item que não está pendente, item que o usuário já
editou na revisão (auditoria de UPDATE com outro autor que não a sync),
item cuja transação não está no comprovante e item de conta sem mapeamento
ativo. Encargos de fatura não dependem da conversão e ficam como estão.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.conversao_pluggy import converter
from app.enums import StatusItem, TipoTransacao
from app.ingestao.base import ItemExtraido
from app.models import Auditoria, ContaPluggy, FormaPagamento, ImportacaoItem
from app.services.base import RegraViolada
from app.services.categorias_pluggy import (
    categorias_por_caminho,
    proposta_para,
    resolver_alvo,
)
from app.services.comprovante_pluggy import Comprovante, ler_comprovante
from app.services.ingestao import IngestaoService, _ContextoEnriquecimento
from app.services.promocao_pluggy import MARCA_DUPLICATA, motivo_para_revisao
from app.services.sync_pluggy import (
    AUTOR as AUTOR_SYNC,
)
from app.services.sync_pluggy import (
    CONFIANCA_DUPLICATA,
    FormaNova,
    ResolvedorDeForma,
)

AUTOR = "reprocessamento_pluggy"

#: A nota que a sync põe no gêmeo da própria Pluggy. A conversão não a
#: reproduz (ela nasce da comparação entre itens), então o reprocessamento a
#: carrega da observação antiga.
_NOTA_DUPLICATA = re.compile(rf"{MARCA_DUPLICATA}.*?aprovar os dois\.", re.S)


@dataclass(slots=True)
class ItemReprocessado:
    item_id: int
    id_externo: str | None
    #: "promover" ou a chave do motivo (`promocao_pluggy.MOTIVOS`).
    destino: str
    forma_id: int | None
    forma_nova: FormaNova | None
    forma_rotulo: str
    categoria_id: int | None
    origem_sugestao: str
    #: Só nos itens convertidos de novo; encargos ficam como estão.
    extraido: ItemExtraido | None = None
    confianca_sugestao: Decimal = Decimal("0.50")
    local_id: int | None = None
    pessoa_id: int | None = None


@dataclass(slots=True)
class PlanoReprocessamento:
    importacao_id: int
    com_proposta: bool
    por_status: Counter[str] = field(default_factory=Counter)
    itens: list[ItemReprocessado] = field(default_factory=list)
    #: Pendentes que ficaram de fora, por motivo.
    mantidos: Counter[str] = field(default_factory=Counter)
    #: Categorias da proposta usadas em memória (só com `com_proposta`).
    proposta_usada: dict[str, str] = field(default_factory=dict)

    @property
    def promoveria(self) -> int:
        return sum(1 for i in self.itens if i.destino == "promover")

    @property
    def na_revisao(self) -> Counter[str]:
        return Counter(i.destino for i in self.itens if i.destino != "promover")

    @property
    def sem_categoria(self) -> int:
        return sum(1 for i in self.itens if i.categoria_id is None)

    @property
    def por_forma(self) -> Counter[str]:
        return Counter(i.forma_rotulo for i in self.itens)

    @property
    def por_origem_categoria(self) -> Counter[str]:
        return Counter(
            i.origem_sugestao if i.categoria_id is not None else "sem categoria" for i in self.itens
        )

    @property
    def formas_novas(self) -> list[FormaNova]:
        vistas: dict[int, FormaNova] = {}
        for i in self.itens:
            if i.forma_nova is not None:
                vistas.setdefault(id(i.forma_nova), i.forma_nova)
        return list(vistas.values())


class ReprocessamentoPluggyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._formas = ResolvedorDeForma(session)

    # -- planejar ---------------------------------------------------------

    def planejar(self, importacao_id: int, *, com_proposta: bool = False) -> PlanoReprocessamento:
        ingestao = IngestaoService(self.session)
        importacao = ingestao.get(importacao_id)
        if importacao.origem != "pluggy":
            raise RegraViolada(
                f"A importação {importacao_id} é de origem {importacao.origem!r}: só importação "
                "da Pluggy é reprocessada (D-21)."
            )
        plano = PlanoReprocessamento(importacao_id=importacao_id, com_proposta=com_proposta)
        comprovante = ler_comprovante(importacao.arquivo_conteudo)

        itens = list(
            self.session.scalars(
                select(ImportacaoItem)
                .where(
                    ImportacaoItem.importacao_id == importacao_id,
                    ImportacaoItem.deleted_em.is_(None),
                )
                .order_by(ImportacaoItem.id)
            )
        )
        plano.por_status = Counter(i.status.value for i in itens)
        pendentes = [i for i in itens if i.status is StatusItem.PENDENTE]
        editados = self._editados([i.id for i in pendentes])

        contexto = _ContextoEnriquecimento.carregar(self.session)
        if com_proposta:
            plano.proposta_usada = self._somar_proposta(contexto, comprovante)
        mapas = self._mapeamentos()
        formas = {
            f.id: f
            for f in self.session.scalars(
                select(FormaPagamento).where(FormaPagamento.deleted_em.is_(None))
            )
        }

        for item in pendentes:
            if item.id in editados:
                plano.mantidos["editado na revisão"] += 1
                continue
            if (item.id_externo or "").startswith("bill:"):
                plano.itens.append(self._encargo(item, formas))
                continue
            transacao = comprovante.transacoes.get(item.id_externo or "")
            if transacao is None:
                plano.mantidos["transação fora do comprovante"] += 1
                continue
            conta = comprovante.contas.get(transacao.account_id)
            mapa = mapas.get(transacao.account_id)
            if conta is None or mapa is None:
                plano.mantidos["conta sem mapeamento"] += 1
                continue
            if mapa.deleted_em is not None or not mapa.ativo:
                plano.mantidos["mapeamento desativado"] += 1
                continue

            faturas = {f.id: f for f in comprovante.faturas_por_conta.get(conta.id, [])}
            try:
                novo = converter(
                    transacao,
                    conta,
                    faturas,
                    dia_fechamento=mapa.forma_pagamento.dia_fechamento,
                    dia_vencimento=mapa.forma_pagamento.dia_vencimento,
                )
            except ValueError:
                plano.mantidos["transação não convertível"] += 1
                continue
            _manter_nota_de_duplicata(novo, item.observacao)

            forma_id, nova = (
                (mapa.forma_pagamento_id, None)
                if conta.e_cartao
                else self._formas.resolver(mapa, novo)
            )
            sugestao = ingestao.sugerir(
                novo,
                contexto,
                forma_fixa_id=forma_id,
                pessoa_padrao_id=mapa.conta.titular_id,
            )
            categoria = sugestao.categoria_id
            if categoria is None and novo.tipo is not TipoTransacao.TRANSFERENCIA:
                categoria = item.categoria_sugerida_id
            ja_existe = (
                forma_id is not None and ingestao._transacao_gemea(novo, forma_id) is not None
            )
            motivo = motivo_para_revisao(novo, categoria_id=categoria, ja_existe=ja_existe)
            plano.itens.append(
                ItemReprocessado(
                    item_id=item.id,
                    id_externo=item.id_externo,
                    destino=motivo or "promover",
                    forma_id=forma_id,
                    forma_nova=nova,
                    forma_rotulo=_rotulo_forma(formas.get(forma_id) if forma_id else None, nova),
                    categoria_id=categoria,
                    origem_sugestao=(
                        sugestao.origem
                        if sugestao.categoria_id is not None
                        else item.origem_sugestao or "parser"
                    ),
                    extraido=novo,
                    confianca_sugestao=sugestao.confianca,
                    local_id=sugestao.local_id,
                    pessoa_id=sugestao.pessoa_id,
                )
            )
        return plano

    def _editados(self, ids: list[int]) -> set[int]:
        """Itens com UPDATE de outro autor que não a sync: o usuário mexeu."""
        if not ids:
            return set()
        return set(
            self.session.scalars(
                select(Auditoria.registro_id).where(
                    Auditoria.tabela == "importacao_itens",
                    Auditoria.acao == "UPDATE",
                    Auditoria.autor != AUTOR_SYNC,
                    Auditoria.registro_id.in_(ids),
                )
            )
        )

    def _mapeamentos(self) -> dict[str, ContaPluggy]:
        """Por conta da Pluggy; o mapeamento vivo vence o apagado."""
        mapas: dict[str, ContaPluggy] = {}
        for mapa in self.session.scalars(select(ContaPluggy).order_by(ContaPluggy.id)):
            atual = mapas.get(mapa.pluggy_account_id)
            if atual is None or atual.deleted_em is not None:
                mapas[mapa.pluggy_account_id] = mapa
        return mapas

    def _somar_proposta(
        self, contexto: _ContextoEnriquecimento, comprovante: Comprovante
    ) -> dict[str, str]:
        """Põe em memória a proposta para as categorias ainda não mapeadas."""
        caminhos = categorias_por_caminho(self.session)
        usadas: dict[str, str] = {}
        for t in comprovante.transacoes.values():
            if not t.category_id or not t.category or t.category_id in contexto.categorias_pluggy:
                continue
            tipo, detalhe = proposta_para(t.category)
            if tipo != "mapear" or not isinstance(detalhe, tuple):
                continue
            alvo = resolver_alvo(caminhos, detalhe)
            if alvo is not None:
                contexto.categorias_pluggy[t.category_id] = (alvo.id, alvo.tipo)
                usadas[t.category_id] = t.category
        return usadas

    def _encargo(self, item: ImportacaoItem, formas: dict[int, FormaPagamento]) -> ItemReprocessado:
        forma = formas.get(item.forma_pagamento_sugerida_id or 0)
        return ItemReprocessado(
            item_id=item.id,
            id_externo=item.id_externo,
            destino="encargos",
            forma_id=item.forma_pagamento_sugerida_id,
            forma_nova=None,
            forma_rotulo=_rotulo_forma(forma, None),
            categoria_id=item.categoria_sugerida_id,
            origem_sugestao=item.origem_sugestao or "parser",
        )

    # -- executar ---------------------------------------------------------

    def executar(self, plano: PlanoReprocessamento) -> dict[str, Any]:
        """Grava o plano e promove os limpos. Não grava plano feito com proposta."""
        if plano.com_proposta:
            raise RegraViolada(
                "O plano usou a proposta de categorias em memória. Grave o mapeamento "
                "(make pluggy-categorias aplicar=1) e planeje de novo antes de executar."
            )
        self.session.execute(text("SELECT set_config('app.autor', :autor, true)"), {"autor": AUTOR})

        atualizados = 0
        for r in plano.itens:
            if r.extraido is None:
                continue  # encargos: ficam como estão
            item = self.session.get(ImportacaoItem, r.item_id)
            if (
                item is None
                or item.deleted_em is not None
                or item.status is not StatusItem.PENDENTE
            ):
                continue
            forma_id = self._formas.criar(r.forma_nova) if r.forma_nova else r.forma_id
            novo = r.extraido
            item.forma_pagamento_sugerida_id = forma_id
            item.categoria_sugerida_id = r.categoria_id
            item.local_sugerido_id = item.local_sugerido_id or r.local_id
            item.pessoa_sugerida_id = item.pessoa_sugerida_id or r.pessoa_id
            item.tipo_sugerido = novo.tipo
            item.competencia_sugerida = novo.competencia or item.competencia_sugerida
            item.observacao = novo.observacao
            item.confianca = min(novo.confianca, r.confianca_sugestao)
            item.origem_sugestao = r.origem_sugestao
            atualizados += 1
        self.session.flush()

        limpos = [r.item_id for r in plano.itens if r.destino == "promover"]
        aprovacao: dict[str, Any] = (
            IngestaoService(self.session).aprovar(limpos)
            if limpos
            else {"promovidos": 0, "duplicados": 0, "erros": []}
        )
        return {"atualizados": atualizados, **aprovacao}


def _manter_nota_de_duplicata(novo: ItemExtraido, observacao_antiga: str | None) -> None:
    casou = _NOTA_DUPLICATA.search(observacao_antiga or "")
    if casou is None:
        return
    nota = casou.group(0)
    novo.observacao = f"{novo.observacao} {nota}" if novo.observacao else nota
    novo.confianca = min(novo.confianca, CONFIANCA_DUPLICATA)


def _rotulo_forma(forma: FormaPagamento | None, nova: FormaNova | None) -> str:
    if nova is not None:
        return f"nova: {nova.apelido} ({nova.tipo.value})"
    if forma is None:
        return "sem forma"
    return f"{forma.apelido} ({forma.tipo.value})"


__all__ = [
    "AUTOR",
    "ItemReprocessado",
    "PlanoReprocessamento",
    "ReprocessamentoPluggyService",
]
