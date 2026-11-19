"""Ligar a nota à despesa de finanças (D-33): sugerir, confirmar, consolidar e
lançar.

A nota guarda só ids (`transacao_id`, `pendente_id_externo`), sem FK (D-25).
Tudo o que é de finanças vem pela API dela (`compras.financas`). Ligar não é
obrigatório; a única escrita em finanças é "lançar despesa pela nota".
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from compras.db import definir_autor
from compras.enums import StatusNota
from compras.financas import (
    Financas,
    FinancasRecusou,
    FormaPagamentoResumo,
    NovaDespesa,
    PendenteResumo,
    TransacaoResumo,
)
from compras.models import NotaFiscal, NotaItem, Produto, Secao
from compras.nfce.html import FUSO
from compras.normalizar import normalizar
from compras.schemas import (
    ConsolidacaoResultado,
    FormaPagamentoOpcao,
    LancarDespesa,
    PreviaLancamento,
    SugestaoLigacao,
)
from compras.services.base import Conflito, NaoEncontrado, RegraViolada

#: Autor da auditoria no que a consolidação grava sozinha (como a leitura).
AUTOR_CONSOLIDACAO = "leitura_nfce"

#: Dias antes e depois da emissão em que a despesa pode estar (a data da Pluggy
#: varia, D-23).
FOLGA_DIAS = 1

#: A forma da página da nota (normalizada) -> o tipo de forma em finanças.
TIPO_DA_FORMA_DA_NOTA: dict[str, str] = {
    "CARTAO DE CREDITO": "credito",
    "CARTAO DE DEBITO": "debito",
    "PIX": "pix",
    "DINHEIRO": "dinheiro",
}

#: Quantas notas anteriores do mesmo mercado se consultam atrás de categoria.
NOTAS_PARA_CATEGORIA = 10

#: Quantos saltos de `substituida_por_id` se seguem (juntar de novo uma já juntada).
SALTOS_MAX = 5


def tipo_esperado(forma_pagamento_nota: str | None) -> str | None:
    """O tipo de forma de finanças que a forma da página sugere; nulo se desconhecida."""
    if not forma_pagamento_nota:
        return None
    return TIPO_DA_FORMA_DA_NOTA.get(normalizar(forma_pagamento_nota))


@dataclass(frozen=True, slots=True)
class _Candidata:
    sugestao: SugestaoLigacao
    distancia: int


class LigacaoNotaService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # --- consultas ---------------------------------------------------------------

    def _nota(self, id_: int) -> NotaFiscal:
        nota = self.session.scalar(
            select(NotaFiscal).where(NotaFiscal.id == id_, NotaFiscal.deleted_em.is_(None))
        )
        if nota is None:
            raise NaoEncontrado("nota", id_)
        return nota

    @staticmethod
    def _dia(nota: NotaFiscal) -> date:
        assert nota.emitida_em is not None
        return nota.emitida_em.astimezone(FUSO).date()

    @staticmethod
    def _exigir_lida(nota: NotaFiscal) -> None:
        if nota.status != StatusNota.LIDA or nota.emitida_em is None or nota.valor_total is None:
            raise RegraViolada("A nota precisa estar lida, com data e valor.")

    @staticmethod
    def _ligada(nota: NotaFiscal) -> bool:
        return nota.transacao_id is not None or nota.pendente_id_externo is not None

    # --- sugestão ----------------------------------------------------------------

    def sugestoes(self, id_: int, financas: Financas) -> list[SugestaoLigacao]:
        """De um dia antes a um dia depois da emissão, valor exato, nas
        transações e nas compras pendentes do cartão.

        A forma do mesmo tipo que a da página vem primeiro, depois o dia mais
        próximo. Só sugere: ligar é o `PUT /notas/{id}/transacao`.
        """
        nota = self._nota(id_)
        self._exigir_lida(nota)
        assert nota.valor_total is not None
        dia = self._dia(nota)
        inicio, fim = dia - timedelta(days=FOLGA_DIAS), dia + timedelta(days=FOLGA_DIAS)
        esperado = tipo_esperado(nota.forma_pagamento_nota)

        candidatas: list[_Candidata] = []
        for t in financas.despesas(inicio, fim, nota.valor_total):
            candidatas.append(self._de_transacao(t, dia, esperado))
        for p in financas.pendentes(inicio, fim, nota.valor_total):
            candidatas.append(self._de_pendente(p, dia, esperado))
        # `sorted` é estável: dentro do mesmo empate, transações antes de pendentes.
        candidatas.sort(key=lambda c: (not c.sugestao.forma_combina, c.distancia))
        return [c.sugestao for c in candidatas]

    @staticmethod
    def _de_transacao(t: TransacaoResumo, dia: date, esperado: str | None) -> _Candidata:
        return _Candidata(
            SugestaoLigacao(
                tipo="transacao",
                transacao_id=t.id,
                data=t.data,
                valor=t.valor,
                descricao=t.descricao,
                cartao=t.forma_pagamento,
                forma_tipo=t.forma_tipo,
                forma_combina=esperado is not None and t.forma_tipo == esperado,
                lancada_pela_nota=t.lancada_pela_nota,
            ),
            abs((t.data - dia).days),
        )

    @staticmethod
    def _de_pendente(p: PendenteResumo, dia: date, esperado: str | None) -> _Candidata:
        return _Candidata(
            SugestaoLigacao(
                tipo="pendente",
                id_externo=p.id_externo,
                data=p.data,
                valor=p.valor,
                descricao=p.descricao,
                cartao=p.forma_pagamento,
                forma_tipo=p.forma_tipo,
                forma_combina=esperado is not None and p.forma_tipo == esperado,
            ),
            abs((p.data - dia).days),
        )

    # --- ligar -------------------------------------------------------------------

    def vincular(
        self,
        id_: int,
        transacao_id: int | None,
        pendente_id_externo: str | None,
        financas: Financas,
    ) -> NotaFiscal:
        """Confirma a transação ou a pendente (um dos dois); nulos desfazem. O
        que se liga precisa existir em finanças."""
        nota = self._nota(id_)
        if transacao_id is not None and not financas.existe(transacao_id):
            raise RegraViolada(f"A transação {transacao_id} não existe em finanças.")
        if pendente_id_externo is not None and not financas.pendente_existe(pendente_id_externo):
            raise RegraViolada(f"A compra pendente {pendente_id_externo} não existe em finanças.")
        # Os dois antes de gravar: a check do banco recusa os dois juntos.
        nota.transacao_id = None
        nota.pendente_id_externo = None
        nota.despesa_lancada_pela_nota = False
        self.session.flush()
        nota.transacao_id = transacao_id
        nota.pendente_id_externo = pendente_id_externo
        self.session.flush()
        return nota

    # --- consolidar --------------------------------------------------------------

    def consolidar(self, financas: Financas) -> ConsolidacaoResultado:
        """Idempotente. Pendente que virou transação passa a transação; pendente
        que sumiu desfaz a ligação; transação juntada pela revisão passa para a
        substituta."""
        definir_autor(self.session, AUTOR_CONSOLIDACAO)
        notas = list(
            self.session.scalars(
                select(NotaFiscal)
                .where(
                    NotaFiscal.deleted_em.is_(None),
                    (NotaFiscal.pendente_id_externo.is_not(None))
                    | (NotaFiscal.transacao_id.is_not(None)),
                )
                .order_by(NotaFiscal.id)
            )
        )
        consolidadas = desfeitas = movidas = 0
        for nota in notas:
            if nota.pendente_id_externo is not None:
                pluggy = nota.pendente_id_externo
                transacao_id = financas.transacao_da_pluggy(pluggy)
                if transacao_id is not None:
                    nota.pendente_id_externo = None
                    nota.transacao_id = transacao_id
                    nota.despesa_lancada_pela_nota = False
                    consolidadas += 1
                elif not financas.pendente_existe(pluggy):
                    nota.pendente_id_externo = None
                    desfeitas += 1
                self.session.flush()
            elif nota.transacao_id is not None:
                destino = self._seguir_substituta(nota.transacao_id, financas)
                if destino != nota.transacao_id:
                    nota.transacao_id = destino
                    nota.despesa_lancada_pela_nota = False
                    movidas += 1
                    self.session.flush()
        return ConsolidacaoResultado(
            verificadas=len(notas),
            consolidadas=consolidadas,
            desfeitas=desfeitas,
            movidas=movidas,
        )

    @staticmethod
    def _seguir_substituta(transacao_id: int, financas: Financas) -> int:
        atual = transacao_id
        for _ in range(SALTOS_MAX):
            situacao = financas.situacao(atual)
            if situacao is None or situacao.viva or situacao.substituida_por_id is None:
                return atual
            atual = situacao.substituida_por_id
        return atual

    # --- lançar despesa pela nota ------------------------------------------------

    def previa(self, id_: int, financas: Financas) -> PreviaLancamento:
        nota = self._nota(id_)
        self._exigir_lida(nota)
        if self._ligada(nota):
            raise Conflito("A nota já está ligada a uma despesa.")
        assert nota.valor_total is not None
        formas = financas.formas_pagamento()
        categoria, origem = self.categoria_sugerida(nota, financas)
        return PreviaLancamento(
            valor=nota.valor_total,
            data=self._dia(nota),
            descricao=nota.mercado.nome if nota.mercado is not None else "Compra no mercado",
            forma_pagamento_nota=nota.forma_pagamento_nota,
            forma_pagamento_id_sugerida=_forma_sugerida(
                formas, tipo_esperado(nota.forma_pagamento_nota)
            ),
            categoria_id_sugerida=categoria,
            categoria_origem=origem,
            formas_pagamento=[
                FormaPagamentoOpcao(id=f.id, apelido=f.apelido, tipo=f.tipo) for f in formas
            ],
        )

    def lancar(self, id_: int, dados: LancarDespesa, financas: Financas) -> NotaFiscal:
        """Cria a despesa em finanças (`lancada_pela_nota`) e liga a nota a ela.
        Finanças fora do ar: a exceção sobe e nada é gravado aqui."""
        nota = self._nota(id_)
        self._exigir_lida(nota)
        if self._ligada(nota):
            raise Conflito("A nota já está ligada a uma despesa.")
        if dados.categoria_id is not None and not financas.categoria_de_despesa(dados.categoria_id):
            raise RegraViolada(f"A categoria {dados.categoria_id} não é uma categoria de despesa.")
        try:
            transacao_id = financas.criar_despesa(
                NovaDespesa(
                    data=dados.data,
                    valor=dados.valor,
                    descricao=dados.descricao,
                    pessoa_id=dados.pessoa_id,
                    forma_pagamento_id=dados.forma_pagamento_id,
                    categoria_id=dados.categoria_id,
                    local_nome=nota.mercado.nome if nota.mercado is not None else None,
                    observacao=f"Lançada pela nota fiscal {nota.chave_acesso}",
                )
            )
        except FinancasRecusou as exc:
            raise RegraViolada(str(exc)) from exc
        nota.transacao_id = transacao_id
        nota.pendente_id_externo = None
        nota.despesa_lancada_pela_nota = True
        self.session.flush()
        return nota

    # --- categoria sugerida ------------------------------------------------------

    def categoria_sugerida(
        self, nota: NotaFiscal, financas: Financas
    ) -> tuple[int | None, str | None]:
        """A categoria com mais valor entre os itens associados (pela seção do
        produto); sem item associado, a da última despesa ligada a uma nota do
        mesmo mercado; senão nenhuma."""
        por_categoria = self._valor_por_categoria(nota.id)
        if por_categoria:
            melhor = max(por_categoria.items(), key=lambda kv: (kv[1], -kv[0]))
            return melhor[0], "itens"
        if nota.mercado_id is not None:
            anteriores = self.session.scalars(
                select(NotaFiscal)
                .where(
                    NotaFiscal.deleted_em.is_(None),
                    NotaFiscal.mercado_id == nota.mercado_id,
                    NotaFiscal.transacao_id.is_not(None),
                    NotaFiscal.id != nota.id,
                )
                .order_by(NotaFiscal.emitida_em.desc().nulls_last(), NotaFiscal.id.desc())
                .limit(NOTAS_PARA_CATEGORIA)
            )
            for anterior in anteriores:
                assert anterior.transacao_id is not None
                categoria = financas.categoria_da_transacao(anterior.transacao_id)
                if categoria is not None:
                    return categoria, "ultima_do_mercado"
        return None, None

    def _valor_por_categoria(self, nota_id: int) -> dict[int, Decimal]:
        linhas = self.session.execute(
            select(Secao.categoria_id_financas, NotaItem.valor_total)
            .join(Produto, Produto.id == NotaItem.produto_id)
            .join(Secao, Secao.id == Produto.secao_id)
            .where(
                NotaItem.nota_fiscal_id == nota_id,
                NotaItem.deleted_em.is_(None),
                Secao.categoria_id_financas.is_not(None),
            )
        )
        soma: dict[int, Decimal] = defaultdict(Decimal)
        for categoria, valor in linhas:
            if categoria is not None:  # o filtro já exclui; é para o tipo
                soma[int(categoria)] += valor
        return dict(soma)


def _forma_sugerida(formas: list[FormaPagamentoResumo], tipo: str | None) -> int | None:
    """A forma do tipo esperado, se for uma só (com várias, quem escolhe é o usuário)."""
    if tipo is None:
        return None
    do_tipo = [f for f in formas if f.tipo == tipo]
    return do_tipo[0].id if len(do_tipo) == 1 else None
