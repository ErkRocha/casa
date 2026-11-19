"""Reaplicação da D-34 nos dados já gravados: estornos e aplicações/resgates.

Dois itens, duas regras da D-34:

* **Estorno** (item 1). Hoje é `receita` num cartão de crédito. A regra nova o
  abate do gasto, na categoria e na pessoa da compra original. **Aguarda
  mudança de schema**: este service só SIMULA o efeito (`planejar`) e
  `executar_estornos` recusa. Nenhuma escrita para estorno, de jeito nenhum.
* **Aplicação e resgate** (item 2). Dinheiro entrando ou saindo de
  investimento é transferência; rendimento (`Proceeds interests and
  dividends`) segue receita. A conversão já classifica assim os itens novos
  (`conversao_pluggy.e_aplicacao_ou_resgate`); aqui se alcançam as
  **transações** já gravadas.

**Nunca toca o que o usuário editou.** Mesmo critério do retroativo da D-21:
a auditoria (D-06) mostra algum UPDATE de autor fora dos processos
automáticos naquela transação.

`transacoes` exige as duas contas na transferência, e o staging só conhece
uma. Por isso `executar_aplicacoes` não converte a transação no lugar: devolve
o item à revisão como transferência (a transação sai por soft delete) e é lá
que o usuário escolhe a outra conta — o mesmo caminho dos itens novos.

Duas fases: `planejar` só lê; `executar_aplicacoes` grava com autor
`d34_reaplicar` na auditoria. Privacidade: nada aqui expõe descrição de
transação; só contagens, somas, meses e categorias.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.conversao_pluggy import (
    OBS_APLICACAO_RESGATE,
    e_aplicacao_ou_resgate,
    e_operacao_de_aplicacao,
)
from app.enums import StatusImportacao, StatusItem, TipoPagamento, TipoTransacao
from app.ingestao.base import sem_acento
from app.models import (
    Categoria,
    CategoriaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Pessoa,
    Transacao,
)
from app.services.comprovante_pluggy import Comprovante, ler_comprovante
from app.services.sync_pluggy import _campos_editados

AUTOR = "d34_reaplicar"

#: Até quantos dias antes do estorno a compra original pode estar.
JANELA_ORIGINAL_DIAS = 90

MENSAGEM_ESTORNO_AGUARDA_SCHEMA = "o estorno aguarda a mudança de schema da D-34"

DesfechoEstorno = Literal["original", "sugestao", "sem_destino", "editado"]
DesfechoAplicacao = Literal["transferencia", "rendimento", "editado"]


class AguardaSchema(Exception):
    """O item 1 depende de migration e não pode ser executado."""


# --------------------------------------------------------------------------
# Achar a compra original — pura
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Compra:
    """Uma despesa candidata a ser a compra original do estorno."""

    id: int
    data: date
    valor: Decimal
    local_id: int | None
    estabelecimento: str
    categoria_id: int | None
    pessoa_id: int | None


def estabelecimento_de(descricao_original: str | None) -> str:
    """Texto comparável do estabelecimento: sem acento, sem parcela, sem pontuação."""
    texto = sem_acento(descricao_original or "").lower()
    texto = re.sub(r"\s+\d{1,2}\s*/\s*\d{1,2}$", "", texto.strip())
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def achar_original(
    *,
    valor: Decimal,
    local_id: int | None,
    estabelecimento: str,
    candidatas: list[Compra],
) -> Compra | None:
    """A compra que o estorno desfez, se for uma só; senão nada.

    Mesmo valor primeiro. Havendo várias, vale a do mesmo estabelecimento (mesmo
    local ou mesmo texto normalizado). Sem nenhuma de mesmo valor (estorno
    parcial), vale a única do mesmo estabelecimento com valor maior.
    """

    def mesmo_lugar(c: Compra) -> bool:
        return (local_id is not None and c.local_id == local_id) or (
            bool(estabelecimento) and c.estabelecimento == estabelecimento
        )

    por_valor = [c for c in candidatas if c.valor == valor]
    if len(por_valor) == 1:
        return por_valor[0]
    if len(por_valor) > 1:
        mesmo = [c for c in por_valor if mesmo_lugar(c)]
        return mesmo[0] if len(mesmo) == 1 else None
    parcial = [c for c in candidatas if c.valor > valor and mesmo_lugar(c)]
    return parcial[0] if len(parcial) == 1 else None


# --------------------------------------------------------------------------
# Plano
# --------------------------------------------------------------------------


@dataclass(slots=True)
class EstornoAvaliado:
    transacao_id: int
    competencia: date
    valor: Decimal
    desfecho: DesfechoEstorno
    categoria: str | None = None
    pessoa: str | None = None


@dataclass(slots=True)
class AplicacaoAvaliada:
    transacao_id: int
    item_id: int
    competencia: date
    valor: Decimal
    tipo: TipoTransacao
    desfecho: DesfechoAplicacao


@dataclass(slots=True)
class TotalMes:
    receitas: Decimal = Decimal("0")
    despesas: Decimal = Decimal("0")


@dataclass(slots=True)
class PlanoD34:
    estornos: list[EstornoAvaliado] = field(default_factory=list)
    aplicacoes: list[AplicacaoAvaliada] = field(default_factory=list)
    #: Receita e despesa de hoje, por competência (só dos meses afetados).
    atuais: dict[date, TotalMes] = field(default_factory=dict)

    def estornos_com(self, *desfechos: DesfechoEstorno) -> list[EstornoAvaliado]:
        return [e for e in self.estornos if e.desfecho in desfechos]

    def aplicacoes_com(self, desfecho: DesfechoAplicacao) -> list[AplicacaoAvaliada]:
        return [a for a in self.aplicacoes if a.desfecho == desfecho]

    def meses(self) -> list[date]:
        afetados = {e.competencia for e in self.estornos if e.desfecho != "editado"}
        afetados |= {a.competencia for a in self.aplicacoes_com("transferencia")}
        return sorted(afetados)

    def depois(self, competencia: date) -> TotalMes:
        """O mês depois das duas regras: o estorno sai das receitas e abate o
        gasto; aplicação e resgate saem de receita ou de despesa."""
        atual = self.atuais.get(competencia, TotalMes())
        receitas, despesas = atual.receitas, atual.despesas
        for e in self.estornos:
            if e.competencia == competencia and e.desfecho != "editado":
                receitas -= e.valor
                despesas -= e.valor
        for a in self.aplicacoes_com("transferencia"):
            if a.competencia == competencia:
                if a.tipo is TipoTransacao.RECEITA:
                    receitas -= a.valor
                else:
                    despesas -= a.valor
        return TotalMes(receitas=receitas, despesas=despesas)


class D34ReaplicarService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._comprovantes: dict[int, Comprovante] = {}

    # -- planejar ---------------------------------------------------------

    def planejar(self) -> PlanoD34:
        plano = PlanoD34()
        self._estornos(plano)
        self._aplicacoes(plano)
        plano.atuais = self._totais(plano.meses())
        return plano

    def _comprovante(self, importacao_id: int) -> Comprovante:
        if importacao_id not in self._comprovantes:
            importacao = self.session.get(Importacao, importacao_id)
            self._comprovantes[importacao_id] = ler_comprovante(
                importacao.arquivo_conteudo if importacao else None
            )
        return self._comprovantes[importacao_id]

    def _itens_aprovados(self, ids: list[int]) -> dict[int, ImportacaoItem]:
        itens: dict[int, ImportacaoItem] = {}
        if not ids:
            return itens
        for item in self.session.scalars(
            select(ImportacaoItem)
            .where(
                ImportacaoItem.transacao_id.in_(ids),
                ImportacaoItem.status == StatusItem.APROVADO,
                ImportacaoItem.deleted_em.is_(None),
            )
            .order_by(ImportacaoItem.id)
        ):
            if item.transacao_id is not None:
                itens.setdefault(item.transacao_id, item)
        return itens

    def _rotulos_de_categoria(self) -> dict[int, tuple[str, TipoTransacao]]:
        todas = list(self.session.scalars(select(Categoria).where(Categoria.deleted_em.is_(None))))
        por_id = {c.id: c for c in todas}
        rotulos: dict[int, tuple[str, TipoTransacao]] = {}
        for c in todas:
            pai = por_id.get(c.categoria_pai_id) if c.categoria_pai_id else None
            rotulos[c.id] = (f"{pai.nome} › {c.nome}" if pai else c.nome, c.tipo)
        return rotulos

    # -- item 1: estornos (só simulação) ----------------------------------

    def _estornos(self, plano: PlanoD34) -> None:
        """Receita em forma de crédito: o que a regra nova trataria como estorno."""
        estornos = list(
            self.session.scalars(
                select(Transacao)
                .join(FormaPagamento, FormaPagamento.id == Transacao.forma_pagamento_id)
                .where(
                    Transacao.tipo == TipoTransacao.RECEITA,
                    Transacao.deleted_em.is_(None),
                    FormaPagamento.tipo == TipoPagamento.CREDITO,
                )
                .order_by(Transacao.id)
            )
        )
        if not estornos:
            return
        itens = self._itens_aprovados([t.id for t in estornos])
        rotulos = self._rotulos_de_categoria()
        formas = {f.id: f for f in self.session.scalars(select(FormaPagamento))}
        pessoas = {p.id: p.nome for p in self.session.scalars(select(Pessoa))}
        mapa = {
            m.pluggy_categoria_id: m.categoria_id
            for m in self.session.scalars(
                select(CategoriaPluggy).where(
                    CategoriaPluggy.deleted_em.is_(None), CategoriaPluggy.ativo.is_(True)
                )
            )
        }

        for t in estornos:
            if _campos_editados(self.session, t.id):
                plano.estornos.append(EstornoAvaliado(t.id, t.competencia, t.valor, "editado"))
                continue
            original = achar_original(
                valor=t.valor,
                local_id=t.local_id,
                estabelecimento=estabelecimento_de(t.descricao_original),
                candidatas=self._compras_antes(t),
            )
            if original is not None:
                plano.estornos.append(
                    EstornoAvaliado(
                        t.id,
                        t.competencia,
                        t.valor,
                        "original",
                        categoria=_rotulo(rotulos, original.categoria_id),
                        pessoa=pessoas.get(original.pessoa_id, "Conjunto")
                        if original.pessoa_id
                        else "Conjunto",
                    )
                )
                continue

            categoria_id = self._categoria_pluggy(itens.get(t.id), mapa, rotulos)
            forma = formas.get(t.forma_pagamento_id) if t.forma_pagamento_id else None
            titular = forma.titular_id if forma else None
            plano.estornos.append(
                EstornoAvaliado(
                    t.id,
                    t.competencia,
                    t.valor,
                    "sugestao" if categoria_id is not None else "sem_destino",
                    categoria=_rotulo(rotulos, categoria_id),
                    pessoa=pessoas.get(titular, "Conjunto") if titular else "Conjunto",
                )
            )

    def _compras_antes(self, estorno: Transacao) -> list[Compra]:
        linhas = self.session.scalars(
            select(Transacao).where(
                Transacao.tipo == TipoTransacao.DESPESA,
                Transacao.deleted_em.is_(None),
                Transacao.forma_pagamento_id == estorno.forma_pagamento_id,
                Transacao.data <= estorno.data,
                Transacao.data >= estorno.data - timedelta(days=JANELA_ORIGINAL_DIAS),
            )
        )
        return [
            Compra(
                id=c.id,
                data=c.data,
                valor=c.valor,
                local_id=c.local_id,
                estabelecimento=estabelecimento_de(c.descricao_original),
                categoria_id=c.categoria_id,
                pessoa_id=c.pessoa_id,
            )
            for c in linhas
        ]

    def _categoria_pluggy(
        self,
        item: ImportacaoItem | None,
        mapa: dict[str, int],
        rotulos: dict[int, tuple[str, TipoTransacao]],
    ) -> int | None:
        """Categoria de despesa mapeada para a categoria da Pluggy do item."""
        if item is None or not item.id_externo:
            return None
        pluggy = self._comprovante(item.importacao_id).transacoes.get(item.id_externo)
        if pluggy is None or not pluggy.category_id:
            return None
        categoria_id = mapa.get(pluggy.category_id)
        if categoria_id is None:
            return None
        destino = rotulos.get(categoria_id)
        if destino is None or destino[1] is not TipoTransacao.DESPESA:
            return None
        return categoria_id

    # -- item 2: aplicações e resgates ------------------------------------

    def _aplicacoes(self, plano: PlanoD34) -> None:
        transacoes = list(
            self.session.scalars(
                select(Transacao)
                .join(Importacao, Importacao.id == Transacao.importacao_id)
                .where(
                    Importacao.origem == "pluggy",
                    Transacao.deleted_em.is_(None),
                    Transacao.tipo.in_([TipoTransacao.RECEITA, TipoTransacao.DESPESA]),
                )
                .order_by(Transacao.id)
            )
        )
        itens = self._itens_aprovados([t.id for t in transacoes])
        for t in transacoes:
            item = itens.get(t.id)
            if item is None or (item.id_externo or "").startswith("bill:"):
                continue
            comprovante = self._comprovante(item.importacao_id)
            pluggy = comprovante.transacoes.get(item.id_externo or "")
            if pluggy is None:
                continue
            conta = comprovante.contas.get(pluggy.account_id)
            if conta is None or conta.e_cartao:
                continue
            if e_aplicacao_ou_resgate(pluggy):
                desfecho: DesfechoAplicacao = (
                    "editado" if _campos_editados(self.session, t.id) else "transferencia"
                )
            elif e_operacao_de_aplicacao(pluggy.operation_type):
                # Operação de resgate com a categoria de rendimento: segue receita.
                desfecho = "rendimento"
            else:
                continue
            plano.aplicacoes.append(
                AplicacaoAvaliada(t.id, item.id, t.competencia, t.valor, t.tipo, desfecho)
            )

    def _totais(self, meses: list[date]) -> dict[date, TotalMes]:
        if not meses:
            return {}
        linhas = self.session.execute(
            select(
                Transacao.competencia,
                func.coalesce(
                    func.sum(Transacao.valor).filter(Transacao.tipo == TipoTransacao.RECEITA), 0
                ),
                func.coalesce(
                    func.sum(Transacao.valor).filter(Transacao.tipo == TipoTransacao.DESPESA), 0
                ),
            )
            .where(Transacao.deleted_em.is_(None), Transacao.competencia.in_(meses))
            .group_by(Transacao.competencia)
        )
        return {
            competencia: TotalMes(receitas=Decimal(receitas), despesas=Decimal(despesas))
            for competencia, receitas, despesas in linhas
        }

    # -- executar ---------------------------------------------------------

    def executar_estornos(self, plano: PlanoD34) -> None:
        """Recusa sempre: o estorno depende de mudança de schema (D-34)."""
        raise AguardaSchema(MENSAGEM_ESTORNO_AGUARDA_SCHEMA)

    def executar_aplicacoes(self, plano: PlanoD34) -> dict[str, int]:
        """Devolve à revisão, como transferência, as aplicações e resgates do plano.

        A transação sai por soft delete e o item volta a `pendente` com
        `tipo_sugerido = transferencia` e a nota da D-34; lá o usuário escolhe
        a outra conta. Confere de novo, na hora, que a transação continua viva
        e sem edição. Sem commit: quem chama decide.
        """
        self.session.execute(text("SELECT set_config('app.autor', :a, true)"), {"a": AUTOR})
        movidas = mudou = 0
        importacoes: set[int] = set()
        for a in plano.aplicacoes_com("transferencia"):
            t = self.session.get(Transacao, a.transacao_id)
            item = self.session.get(ImportacaoItem, a.item_id)
            if (
                t is None
                or t.deleted_em is not None
                or item is None
                or item.deleted_em is not None
                or item.transacao_id != t.id
                or _campos_editados(self.session, t.id)
            ):
                mudou += 1
                continue
            t.deleted_em = func.now()
            item.status = StatusItem.PENDENTE
            item.transacao_id = None
            item.tipo_sugerido = TipoTransacao.TRANSFERENCIA
            item.categoria_sugerida_id = None
            item.confianca = Decimal("0.70")
            item.observacao = f"{item.observacao or ''} {OBS_APLICACAO_RESGATE}".strip()
            importacoes.add(item.importacao_id)
            movidas += 1
        self.session.flush()
        for importacao_id in importacoes:
            importacao = self.session.get(Importacao, importacao_id)
            if importacao is None:
                continue
            importacao.itens_aprovados = int(
                self.session.scalar(
                    select(func.count())
                    .select_from(ImportacaoItem)
                    .where(
                        ImportacaoItem.importacao_id == importacao_id,
                        ImportacaoItem.status == StatusItem.APROVADO,
                        ImportacaoItem.deleted_em.is_(None),
                    )
                )
                or 0
            )
            if importacao.status is StatusImportacao.CONCLUIDA:
                importacao.status = StatusImportacao.AGUARDANDO_REVISAO
        self.session.flush()
        return {"devolvidas_a_revisao": movidas, "mudou_desde_o_plano": mudou}


def _rotulo(rotulos: dict[int, tuple[str, TipoTransacao]], categoria_id: int | None) -> str | None:
    if categoria_id is None:
        return None
    alvo = rotulos.get(categoria_id)
    return alvo[0] if alvo else None


__all__ = [
    "AUTOR",
    "MENSAGEM_ESTORNO_AGUARDA_SCHEMA",
    "AguardaSchema",
    "D34ReaplicarService",
    "PlanoD34",
    "achar_original",
    "estabelecimento_de",
]
