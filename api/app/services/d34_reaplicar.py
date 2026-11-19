"""Reaplicação da D-34 nos dados já gravados: estornos e aplicações/resgates.

Dois itens, duas regras da D-34:

* **Estorno** (item 1). Era `receita` num cartão de crédito. A regra nova o
  abate do gasto: vira `tipo = 'estorno'`, com a categoria e a pessoa da compra
  original (e `estorno_de_id` ligando as duas) quando ela se acha, senão com a
  categoria sugerida pela Pluggy e o titular do cartão. A busca da original é a
  de `app.services.estorno`, a mesma da promoção.
* **Aplicação e resgate** (item 2). Dinheiro entrando ou saindo de
  investimento é transferência; rendimento (`Proceeds interests and
  dividends`) segue receita. A conversão já classifica assim os itens novos
  (`conversao_pluggy.e_aplicacao_ou_resgate`); aqui se alcançam as
  **transações** já gravadas.

**Nunca toca o que o usuário editou.** Mesmo critério do retroativo da D-21:
a auditoria (D-06) mostra algum UPDATE de autor fora dos processos
automáticos naquela transação.

**A simulação funciona sem a migration 0009.** `planejar` só lê, por colunas
explícitas (nunca a entidade `Transacao`, que traria `estorno_de_id`) e nunca
usa o valor `estorno` do enum. Só `executar_*` exige a migration.

`transacoes` exige as duas contas na transferência, e o staging só conhece
uma. Por isso `executar_aplicacoes` não converte a transação no lugar: devolve
o item à revisão como transferência (a transação sai por soft delete) e é lá
que o usuário escolhe a outra conta — o mesmo caminho dos itens novos.

Duas fases: `planejar` só lê; `executar_*` grava com autor `d34_reaplicar` na
auditoria. Privacidade: nada aqui expõe descrição de transação; só contagens,
somas, meses, categorias e ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from sqlalchemy import Text, case, cast, func, select, text
from sqlalchemy.orm import Session

from app.conversao_pluggy import (
    OBS_APLICACAO_RESGATE,
    e_aplicacao_ou_resgate,
    e_operacao_de_aplicacao,
)
from app.enums import StatusImportacao, StatusItem, TipoPagamento, TipoTransacao
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
from app.services.estorno import (
    JANELA_ORIGINAL_DIAS,
    Compra,
    achar_original,
    compras_antes,
    estabelecimento_de,
    titular_do_cartao,
)
from app.services.sync_pluggy import _campos_editados

AUTOR = "d34_reaplicar"

DesfechoEstorno = Literal["original", "sugestao", "sem_destino", "editado"]
DesfechoAplicacao = Literal["transferencia", "rendimento", "editado"]


class SchemaDesatualizado(Exception):
    """A migration 0009 (tipo estorno) não está aplicada: só dá para simular."""


def schema_pronto(session: Session) -> bool:
    """A migration 0009 já foi aplicada (existe `transacoes.estorno_de_id`)?"""
    return bool(
        session.scalar(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'transacoes' AND column_name = 'estorno_de_id'"
            )
        )
    )


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
    #: O que `executar_estornos` grava: categoria e pessoa de destino e a
    #: compra original (`estorno_de_id`), quando achada.
    categoria_id: int | None = None
    pessoa_id: int | None = None
    original_id: int | None = None


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

    # -- item 1: estornos ---------------------------------------------------

    def _estornos(self, plano: PlanoD34) -> None:
        """Receita em forma de crédito: o que a regra nova trata como estorno."""
        # Colunas, não a entidade: sem a migration 0009 a coluna `estorno_de_id`
        # não existe, e a simulação tem que funcionar assim mesmo.
        estornos = self.session.execute(
            select(
                Transacao.id,
                Transacao.competencia,
                Transacao.data,
                Transacao.valor,
                Transacao.local_id,
                Transacao.descricao_original,
                Transacao.forma_pagamento_id,
            )
            .join(FormaPagamento, FormaPagamento.id == Transacao.forma_pagamento_id)
            .where(
                Transacao.tipo == TipoTransacao.RECEITA,
                Transacao.deleted_em.is_(None),
                FormaPagamento.tipo == TipoPagamento.CREDITO,
            )
            .order_by(Transacao.id)
        ).all()
        if not estornos:
            return
        itens = self._itens_aprovados([t.id for t in estornos])
        rotulos = self._rotulos_de_categoria()
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
                candidatas=compras_antes(
                    self.session, forma_pagamento_id=t.forma_pagamento_id, data=t.data
                ),
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
                        categoria_id=original.categoria_id,
                        pessoa_id=original.pessoa_id,
                        original_id=original.id,
                    )
                )
                continue

            categoria_id = self._categoria_pluggy(itens.get(t.id), mapa, rotulos)
            titular = titular_do_cartao(self.session, t.forma_pagamento_id)
            plano.estornos.append(
                EstornoAvaliado(
                    t.id,
                    t.competencia,
                    t.valor,
                    "sugestao" if categoria_id is not None else "sem_destino",
                    categoria=_rotulo(rotulos, categoria_id),
                    pessoa=pessoas.get(titular, "Conjunto") if titular else "Conjunto",
                    categoria_id=categoria_id,
                    pessoa_id=titular,
                )
            )

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
        transacoes = self.session.execute(
            select(Transacao.id, Transacao.competencia, Transacao.valor, Transacao.tipo)
            .join(Importacao, Importacao.id == Transacao.importacao_id)
            .where(
                Importacao.origem == "pluggy",
                Transacao.deleted_em.is_(None),
                Transacao.tipo.in_([TipoTransacao.RECEITA, TipoTransacao.DESPESA]),
            )
            .order_by(Transacao.id)
        ).all()
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
                # Gasto líquido (D-34), comparando o tipo como texto: sem a
                # migration 0009 o enum ainda não tem o valor `estorno`.
                func.coalesce(
                    func.sum(
                        case(
                            (cast(Transacao.tipo, Text) == "despesa", Transacao.valor),
                            (cast(Transacao.tipo, Text) == "estorno", -Transacao.valor),
                        )
                    ),
                    0,
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

    def executar_estornos(self, plano: PlanoD34) -> dict[str, int]:
        """Converte em estorno as receitas de cartão do plano.

        Cada uma vira `tipo = 'estorno'`, com categoria, pessoa e
        `estorno_de_id` do destino planejado (sem destino de categoria, fica
        sem categoria: a de receita não serve a um estorno). Confere de novo,
        na hora, que a transação continua viva, receita e sem edição do usuário.
        Sem commit: quem chama decide.
        """
        if not schema_pronto(self.session):
            raise SchemaDesatualizado("aplique a migration 0009 antes de executar os estornos")
        self.session.execute(text("SELECT set_config('app.autor', :a, true)"), {"a": AUTOR})
        convertidos = mudou = 0
        for e in plano.estornos_com("original", "sugestao", "sem_destino"):
            t = self.session.get(Transacao, e.transacao_id)
            if (
                t is None
                or t.deleted_em is not None
                or t.tipo is not TipoTransacao.RECEITA
                or _campos_editados(self.session, t.id)
            ):
                mudou += 1
                continue
            t.tipo = TipoTransacao.ESTORNO
            t.categoria_id = e.categoria_id
            t.pessoa_id = e.pessoa_id
            t.estorno_de_id = e.original_id
            convertidos += 1
        self.session.flush()
        return {"convertidos": convertidos, "mudou_desde_o_plano": mudou}

    def executar_aplicacoes(self, plano: PlanoD34) -> dict[str, int]:
        """Devolve à revisão, como transferência, as aplicações e resgates do plano.

        A transação sai por soft delete e o item volta a `pendente` com
        `tipo_sugerido = transferencia` e a nota da D-34; lá o usuário escolhe
        a outra conta. Confere de novo, na hora, que a transação continua viva
        e sem edição. Sem commit: quem chama decide.
        """
        if not schema_pronto(self.session):
            raise SchemaDesatualizado("aplique a migration 0009 antes de executar")
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
    "JANELA_ORIGINAL_DIAS",
    "Compra",
    "D34ReaplicarService",
    "PlanoD34",
    "SchemaDesatualizado",
    "achar_original",
    "estabelecimento_de",
    "schema_pronto",
]
