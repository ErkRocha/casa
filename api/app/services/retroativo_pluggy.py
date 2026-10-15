"""Preenchimento retroativo das transações já promovidas da Pluggy (D-21).

A importação #4 foi promovida antes da D-21 valer inteira: as transações de
conta corrente ficaram todas com a forma Pix do mapeamento, mesmo quando a
Pluggy dizia débito, boleto ou transferência, e quase nenhuma ganhou
categoria, porque o mapeamento das categorias da Pluggy ainda não existia.
O reprocessamento só alcança os itens **pendentes**; este service alcança as
**transações**, com duas mudanças, e só elas:

* **categoria**, pela ordem da D-21 (regra do usuário > mapeamento da Pluggy
  > local conhecido), onde a transação está sem categoria;
* **forma de pagamento**, nas transações de conta cuja operação da Pluggy
  diz débito, boleto ou transferência, pela mesma escolha da sync
  (`ResolvedorDeForma`).

**Nunca toca o que o usuário editou.** O critério é a auditoria (D-06), por
campo: a categoria fica como está se algum UPDATE de `transacoes` mudou
`categoria_id` (de qualquer autor que não este service: nenhum processo
automático muda a categoria de uma transação, então a mudança foi do
usuário), ou se a
revisão mudou `categoria_sugerida_id` do item antes de aprovar (autor fora
dos processos da Pluggy). O mesmo vale, separado, para a forma. Uma
transação com a categoria editada ainda pode ter a forma corrigida, e o
contrário.

Duas fases, como o reprocessamento: `planejar` só lê; `executar` grava o
plano com autor `retroativo_d21` na auditoria.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.conversao_pluggy import converter
from app.enums import StatusItem, TipoPagamento, TipoTransacao
from app.models import (
    Auditoria,
    Categoria,
    ContaPluggy,
    FormaPagamento,
    Importacao,
    ImportacaoItem,
    Transacao,
)
from app.services.comprovante_pluggy import Comprovante, ler_comprovante
from app.services.ingestao import _ContextoEnriquecimento
from app.services.sync_pluggy import AUTOR as AUTOR_SYNC
from app.services.sync_pluggy import FormaNova, ResolvedorDeForma

AUTOR = "retroativo_d21"

#: Quem muda item de staging sem ser o usuário. UPDATE de outro autor no
#: campo é edição na revisão.
AUTORES_AUTOMATICOS = frozenset({AUTOR_SYNC, "reprocessamento_pluggy", AUTOR})

#: As formas que a correção aplica: as que a operação da Pluggy diz e que a
#: primeira sync gravou como Pix. Pix continua Pix.
FORMAS_CORRIGIDAS = frozenset(
    {TipoPagamento.DEBITO, TipoPagamento.BOLETO, TipoPagamento.TRANSFERENCIA}
)

#: Motivos de pular, por campo, quando a auditoria mostra edição do usuário.
EDITADA_PELO_USUARIO = "editada pelo usuário"


# --------------------------------------------------------------------------
# Decisão por transação — pura, para ser testada sem banco
# --------------------------------------------------------------------------


def decidir_categoria(
    *,
    categoria_atual: int | None,
    tipo: TipoTransacao,
    editada: bool,
    sugerida: tuple[int, TipoTransacao] | None,
) -> tuple[int | None, str | None]:
    """`(categoria nova, None)` ou `(None, motivo de não mudar)`.

    A edição do usuário é checada antes da sugestão: transação que ele
    editou é pulada mesmo quando a sugestão por acaso coincidiria.
    """
    if categoria_atual is not None:
        return None, "já tem categoria"
    if tipo is TipoTransacao.TRANSFERENCIA:
        return None, "transferência não tem categoria"
    if editada:
        return None, EDITADA_PELO_USUARIO
    if sugerida is None:
        return None, "sem categoria pela ordem da D-21"
    categoria_id, tipo_categoria = sugerida
    if tipo_categoria is not tipo:
        return None, "categoria sugerida de outro tipo"
    return categoria_id, None


def decidir_forma(
    *,
    e_cartao: bool,
    forma_tipo: TipoPagamento | None,
    forma_atual_id: int | None,
    resolvida_id: int | None,
    nova: bool,
    editada: bool,
    colide: bool,
) -> str | None:
    """`None` se a forma muda; senão o motivo de não mudar."""
    if e_cartao:
        return "cartão: forma do mapeamento"
    if forma_tipo not in FORMAS_CORRIGIDAS:
        return "operação sem forma a corrigir"
    if not nova and resolvida_id == forma_atual_id:
        return "forma já certa"
    if editada:
        return EDITADA_PELO_USUARIO
    if colide:
        return "colidiria com transação idêntica"
    return None


# --------------------------------------------------------------------------
# Plano
# --------------------------------------------------------------------------


@dataclass(slots=True)
class MudancaRetroativa:
    transacao_id: int
    categoria_id: int | None = None
    categoria_rotulo: str | None = None
    origem_categoria: str | None = None
    forma_de: int | None = None
    forma_para: int | None = None
    forma_nova: FormaNova | None = None
    forma_de_rotulo: str = ""
    forma_para_rotulo: str = ""

    @property
    def muda_forma(self) -> bool:
        return self.forma_para is not None or self.forma_nova is not None


@dataclass(slots=True)
class PlanoRetroativo:
    #: Transações vivas vindas de importação da Pluggy.
    avaliadas: int = 0
    mudancas: list[MudancaRetroativa] = field(default_factory=list)
    #: Transações que ficaram fora inteiras (sem item, fora do comprovante...).
    fora: Counter[str] = field(default_factory=Counter)
    #: Por que a categoria não muda, entre as sem categoria.
    categoria_mantida: Counter[str] = field(default_factory=Counter)
    #: Por que a forma não muda, entre as de conta com operação a corrigir.
    forma_mantida: Counter[str] = field(default_factory=Counter)

    @property
    def por_categoria(self) -> Counter[str]:
        return Counter(
            m.categoria_rotulo or "?" for m in self.mudancas if m.categoria_id is not None
        )

    @property
    def por_origem(self) -> Counter[str]:
        return Counter(
            m.origem_categoria or "?" for m in self.mudancas if m.categoria_id is not None
        )

    @property
    def por_forma(self) -> Counter[tuple[str, str]]:
        return Counter(
            (m.forma_de_rotulo, m.forma_para_rotulo) for m in self.mudancas if m.muda_forma
        )

    @property
    def ganham_categoria(self) -> int:
        return sum(1 for m in self.mudancas if m.categoria_id is not None)

    @property
    def mudam_forma(self) -> int:
        return sum(1 for m in self.mudancas if m.muda_forma)

    @property
    def pulados_por_edicao(self) -> dict[str, int]:
        return {
            "categoria": self.categoria_mantida[EDITADA_PELO_USUARIO],
            "forma": self.forma_mantida[EDITADA_PELO_USUARIO],
        }

    @property
    def formas_novas(self) -> list[FormaNova]:
        vistas: dict[int, FormaNova] = {}
        for m in self.mudancas:
            if m.forma_nova is not None:
                vistas.setdefault(id(m.forma_nova), m.forma_nova)
        return list(vistas.values())


class RetroativoPluggyService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self._formas = ResolvedorDeForma(session)

    # -- planejar ---------------------------------------------------------

    def planejar(self) -> PlanoRetroativo:
        plano = PlanoRetroativo()
        transacoes = list(
            self.session.scalars(
                select(Transacao)
                .join(Importacao, Importacao.id == Transacao.importacao_id)
                .where(Importacao.origem == "pluggy", Transacao.deleted_em.is_(None))
                .order_by(Transacao.id)
            )
        )
        plano.avaliadas = len(transacoes)
        if not transacoes:
            return plano

        ids = [t.id for t in transacoes]
        itens = self._itens_por_transacao(ids)
        cat_editadas, forma_editadas = self._editadas(ids, [i.id for i in itens.values()], itens)
        contexto = _ContextoEnriquecimento.carregar(self.session)
        categorias = self._categorias()
        formas = {
            f.id: f
            for f in self.session.scalars(
                select(FormaPagamento).where(FormaPagamento.deleted_em.is_(None))
            )
        }
        mapas = self._mapeamentos()
        comprovantes: dict[int, Comprovante] = {}

        for t in transacoes:
            item = itens.get(t.id)
            if item is None:
                plano.fora["sem item de staging aprovado"] += 1
                continue
            if (item.id_externo or "").startswith("bill:"):
                plano.fora["encargo de fatura"] += 1
                continue
            comprovante = comprovantes.get(item.importacao_id)
            if comprovante is None:
                comprovante = comprovantes[item.importacao_id] = self._comprovante(
                    item.importacao_id
                )
            transacao = comprovante.transacoes.get(item.id_externo or "")
            if transacao is None:
                plano.fora["transação fora do comprovante"] += 1
                continue
            conta = comprovante.contas.get(transacao.account_id)
            mapa = mapas.get(transacao.account_id)
            if conta is None or mapa is None or mapa.deleted_em is not None or not mapa.ativo:
                plano.fora["conta sem mapeamento ativo"] += 1
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
                plano.fora["transação não convertível"] += 1
                continue

            mudanca = MudancaRetroativa(transacao_id=t.id)

            # Categoria: a mesma chamada que a sync faz, com o tipo de hoje
            # da transação (o usuário pode ter trocado o tipo).
            if t.categoria_id is None:
                sugestao = contexto.sugerir_para(
                    novo.descricao,
                    None,
                    categoria_externa_id=novo.categoria_externa_id,
                    tipo=t.tipo,
                )
                sugerida = (
                    (sugestao.categoria_id, categorias[sugestao.categoria_id][1])
                    if sugestao.categoria_id in categorias
                    else None
                )
                nova_categoria, motivo = decidir_categoria(
                    categoria_atual=t.categoria_id,
                    tipo=t.tipo,
                    editada=t.id in cat_editadas,
                    sugerida=sugerida,
                )
                if nova_categoria is None:
                    plano.categoria_mantida[motivo or "?"] += 1
                else:
                    mudanca.categoria_id = nova_categoria
                    mudanca.categoria_rotulo = categorias[nova_categoria][0]
                    mudanca.origem_categoria = sugestao.origem

            # Forma: só conta corrente, só débito, boleto e transferência.
            if not conta.e_cartao and novo.forma_tipo in FORMAS_CORRIGIDAS:
                resolvida_id, nova = self._formas.resolver(mapa, novo)
                colide = (
                    nova is None
                    and resolvida_id != t.forma_pagamento_id
                    and self._colide(t, resolvida_id)
                )
                motivo_forma = decidir_forma(
                    e_cartao=False,
                    forma_tipo=novo.forma_tipo,
                    forma_atual_id=t.forma_pagamento_id,
                    resolvida_id=resolvida_id,
                    nova=nova is not None,
                    editada=t.id in forma_editadas,
                    colide=colide,
                )
                if motivo_forma is not None:
                    plano.forma_mantida[motivo_forma] += 1
                else:
                    mudanca.forma_de = t.forma_pagamento_id
                    mudanca.forma_para = resolvida_id
                    mudanca.forma_nova = nova
                    mudanca.forma_de_rotulo = _rotulo_forma(
                        formas.get(t.forma_pagamento_id or 0), None
                    )
                    mudanca.forma_para_rotulo = _rotulo_forma(formas.get(resolvida_id or 0), nova)

            if mudanca.categoria_id is not None or mudanca.muda_forma:
                plano.mudancas.append(mudanca)
        return plano

    def _itens_por_transacao(self, ids: list[int]) -> dict[int, ImportacaoItem]:
        itens: dict[int, ImportacaoItem] = {}
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

    def _editadas(
        self, transacao_ids: list[int], item_ids: list[int], itens: dict[int, ImportacaoItem]
    ) -> tuple[set[int], set[int]]:
        """Transações com categoria e com forma editadas pelo usuário.

        Na transação, qualquer UPDATE que mudou o campo conta, menos o deste
        próprio service (rodar duas vezes não pode virar "editada"). No item,
        só o de autor fora dos processos da Pluggy: a sync e o
        reprocessamento também gravam lá.
        """
        cat: set[int] = set()
        forma: set[int] = set()
        for registro_id, antes, depois in self.session.execute(
            select(Auditoria.registro_id, Auditoria.dados_antes, Auditoria.dados_depois).where(
                Auditoria.tabela == "transacoes",
                Auditoria.acao == "UPDATE",
                Auditoria.autor != AUTOR,
                Auditoria.registro_id.in_(transacao_ids),
            )
        ):
            if _mudou(antes, depois, "categoria_id"):
                cat.add(registro_id)
            if _mudou(antes, depois, "forma_pagamento_id"):
                forma.add(registro_id)

        transacao_do_item = {item.id: t_id for t_id, item in itens.items()}
        for registro_id, antes, depois in self.session.execute(
            select(Auditoria.registro_id, Auditoria.dados_antes, Auditoria.dados_depois).where(
                Auditoria.tabela == "importacao_itens",
                Auditoria.acao == "UPDATE",
                Auditoria.autor.not_in(AUTORES_AUTOMATICOS),
                Auditoria.registro_id.in_(item_ids),
            )
        ):
            t_id = transacao_do_item.get(registro_id)
            if t_id is None:
                continue
            if _mudou(antes, depois, "categoria_sugerida_id"):
                cat.add(t_id)
            if _mudou(antes, depois, "forma_pagamento_sugerida_id"):
                forma.add(t_id)
        return cat, forma

    def _categorias(self) -> dict[int, tuple[str, TipoTransacao]]:
        """Id -> (caminho "Raiz › Filha", tipo), das vivas e ativas."""
        todas = list(
            self.session.scalars(
                select(Categoria).where(Categoria.deleted_em.is_(None), Categoria.ativo.is_(True))
            )
        )
        por_id = {c.id: c for c in todas}
        rotulos: dict[int, tuple[str, TipoTransacao]] = {}
        for c in todas:
            pai = por_id.get(c.categoria_pai_id) if c.categoria_pai_id else None
            rotulos[c.id] = (f"{pai.nome} › {c.nome}" if pai else c.nome, c.tipo)
        return rotulos

    def _mapeamentos(self) -> dict[str, ContaPluggy]:
        """Por conta da Pluggy; o mapeamento vivo vence o apagado."""
        mapas: dict[str, ContaPluggy] = {}
        for mapa in self.session.scalars(select(ContaPluggy).order_by(ContaPluggy.id)):
            atual = mapas.get(mapa.pluggy_account_id)
            if atual is None or atual.deleted_em is not None:
                mapas[mapa.pluggy_account_id] = mapa
        return mapas

    def _comprovante(self, importacao_id: int) -> Comprovante:
        importacao = self.session.get(Importacao, importacao_id)
        return ler_comprovante(importacao.arquivo_conteudo if importacao else None)

    def _colide(self, t: Transacao, forma_id: int | None) -> bool:
        """Outra transação viva já tem o `hash_dedup` que esta teria."""
        outra = self.session.scalar(
            select(Transacao.id).where(
                Transacao.id != t.id,
                Transacao.deleted_em.is_(None),
                Transacao.data == t.data,
                Transacao.valor == t.valor,
                Transacao.descricao_original.is_not_distinct_from(t.descricao_original),
                Transacao.forma_pagamento_id.is_not_distinct_from(forma_id),
                Transacao.parcela_num.is_not_distinct_from(t.parcela_num),
            )
        )
        return outra is not None

    # -- executar ---------------------------------------------------------

    def executar(self, plano: PlanoRetroativo) -> dict[str, Any]:
        """Grava o plano, uma transação por vez, com autor `retroativo_d21`.

        Confere de novo, na hora, que a categoria continua vazia e a forma
        continua a do plano: entre o planejar e o executar o usuário pode ter
        mexido. Linha que esbarra no índice único é desfeita sozinha
        (savepoint) e contada, sem derrubar as outras.
        """
        self.session.execute(text("SELECT set_config('app.autor', :autor, true)"), {"autor": AUTOR})
        # As formas novas antes das linhas, fora dos savepoints: uma linha
        # desfeita não pode levar junto a forma que as outras usam.
        for nova in plano.formas_novas:
            self._formas.criar(nova)
        resultado: dict[str, Any] = {"categorias": 0, "formas": 0, "mudou_desde_o_plano": 0}
        erros: list[dict[str, Any]] = []
        for m in plano.mudancas:
            t = self.session.get(Transacao, m.transacao_id)
            if t is None or t.deleted_em is not None:
                resultado["mudou_desde_o_plano"] += 1
                continue
            muda_categoria = m.categoria_id is not None and t.categoria_id is None
            muda_forma = m.muda_forma and t.forma_pagamento_id == m.forma_de
            if not (muda_categoria or muda_forma):
                resultado["mudou_desde_o_plano"] += 1
                continue
            try:
                with self.session.begin_nested():
                    if muda_categoria:
                        t.categoria_id = m.categoria_id
                    if muda_forma:
                        t.forma_pagamento_id = (
                            m.forma_nova.id if m.forma_nova is not None else m.forma_para
                        )
                    self.session.flush()
            except IntegrityError as exc:
                self.session.expire(t)
                erros.append({"transacao_id": t.id, "erro": type(exc.orig).__name__})
                continue
            resultado["categorias"] += int(muda_categoria)
            resultado["formas"] += int(muda_forma)
        resultado["erros"] = erros
        return resultado


def _mudou(antes: dict[str, Any] | None, depois: dict[str, Any] | None, campo: str) -> bool:
    return (antes or {}).get(campo) != (depois or {}).get(campo)


def _rotulo_forma(forma: FormaPagamento | None, nova: FormaNova | None) -> str:
    if nova is not None:
        return f"nova: {nova.apelido} ({nova.tipo.value})"
    if forma is None:
        return "sem forma"
    return f"{forma.apelido} ({forma.tipo.value})"


__all__ = [
    "AUTOR",
    "MudancaRetroativa",
    "PlanoRetroativo",
    "RetroativoPluggyService",
    "decidir_categoria",
    "decidir_forma",
]
