"""Conferência da lista pela nota (D-33; modelo-notas.md, "Casamento entre lista e nota").

A **prévia** monta um plano e não grava; a **confirmação** monta o mesmo plano
dentro da transação, com os itens da lista travados, e o aplica. Lista pede
produto, nota traz variante: casam pelo produto da variante.

O conjunto conferido é o dos pendentes e dos comprados sem `fechamento`
(o marco é o fechamento, não uma data). A única regra de data: o comprado só
casa com nota emitida depois de `comprado_em` menos 1 dia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from compras.enums import EstadoDespensa, FechamentoItem, OrigemItem, SituacaoItem, StatusNota
from compras.models import Despensa, ItemLista, NotaFiscal, NotaItem
from compras.schemas import Proximos
from compras.schemas_conferencia import (
    AguardandoNota,
    ConferenciaResposta,
    Confirmado,
    ContinuaPendente,
    Diferenca,
    Extra,
    Marcado,
    MudancaDespensa,
    NaoReconhecido,
)
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.despensa import DespensaService
from compras.services.lista import ListaService
from compras.services.mudancas import agora
from compras.services.notas import AUTOR_LEITURA

#: O comprado casa com nota emitida depois de `comprado_em` menos isto.
FOLGA_DA_MARCACAO = timedelta(days=1)

#: Unidades da nota que contam peças (as mesmas da view de preço).
UNIDADES_DE_CONTAGEM = {"UN", "UND", "UNID", "PC", "PCT"}

AVISO_MARCADO = "não estava marcado; marcado como comprado pela nota"


def _txt(valor: Decimal) -> str:
    """`6.000` -> `6`; `0.500` -> `0.5`."""
    texto = format(valor.normalize(), "f")
    return texto


@dataclass
class _Diferenca:
    item: ItemLista
    pedido: Decimal
    veio: Decimal
    unidade: str

    @property
    def falta(self) -> Decimal:
        return self.pedido - self.veio


@dataclass
class _Plano:
    nota: NotaFiscal
    quando: datetime
    confirmados: list[tuple[ItemLista, list[NotaItem]]] = field(default_factory=list)
    marcados: list[tuple[ItemLista, list[NotaItem]]] = field(default_factory=list)
    extras: list[NotaItem] = field(default_factory=list)
    continuam_pendentes: list[ItemLista] = field(default_factory=list)
    aguardando: list[ItemLista] = field(default_factory=list)
    diferencas: list[_Diferenca] = field(default_factory=list)
    nao_reconhecidos: list[NotaItem] = field(default_factory=list)
    #: (produto_id, nome, antes)
    despensa: list[tuple[int, str, EstadoDespensa]] = field(default_factory=list)
    acompanhados: set[int] = field(default_factory=set)

    @property
    def sem_lista(self) -> bool:
        return not (self.confirmados or self.marcados)


class ConferenciaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem
        self.despensa = DespensaService(session, quem)

    # -- leitura -----------------------------------------------------------

    def previa(self, nota_id: int) -> ConferenciaResposta:
        """O que a confirmação faria. Não grava nada."""
        nota = self._nota(nota_id)
        if nota.conferida_em is not None:
            return self._feita(nota)
        return self._resposta(self._planejar(nota), "pendente", None)

    def estado(self, nota: NotaFiscal) -> str:
        """`pendente`, `sem_lista` ou `feita`, para o `proximos` do `POST /notas`."""
        if nota.conferida_em is not None:
            return "feita"
        if nota.status != StatusNota.LIDA:
            return "sem_lista"
        return "sem_lista" if self._planejar(nota).sem_lista else "pendente"

    def proximos(self, nota: NotaFiscal) -> Proximos:
        sem_variante = self.session.scalar(
            select(func.count())
            .select_from(NotaItem)
            .where(
                NotaItem.nota_fiscal_id == nota.id,
                NotaItem.deleted_em.is_(None),
                NotaItem.variante_id.is_(None),
            )
        )
        return Proximos(
            ligar_despesa=(
                nota.status == StatusNota.LIDA
                and nota.transacao_id is None
                and nota.pendente_id_externo is None
            ),
            itens_sem_variante=int(sem_variante or 0),
            conferencia=self.estado(nota),
        )

    # -- escrita -----------------------------------------------------------

    def confirmar(self, nota_id: int, volta: dict[int, bool]) -> ConferenciaResposta:
        """Aplica a conferência. `volta` é a resposta de cada pergunta de
        quantidade (por `item_lista_id`). Confirmar de novo não muda nada."""
        nota = self._nota(nota_id, travar=True)
        if nota.conferida_em is not None:
            return self._feita(nota)

        plano = self._planejar(nota, travar=True)
        faltam = [d for d in plano.diferencas if d.item.id not in volta]
        if faltam:
            raise RegraViolada(
                "Responda se a diferença volta para a lista: "
                + ", ".join(d.item.produto.nome for d in faltam)
                + ".",
                {
                    "faltam": [
                        {"item_lista_id": d.item.id, "produto": d.item.produto.nome} for d in faltam
                    ]
                },
            )
        self._aplicar(plano, volta)
        return self._resposta(plano, "feita", volta)

    def linha_associada_depois(self, nota: NotaFiscal, linha: NotaItem) -> None:
        """A linha de uma nota **já conferida** ganhou variante (`PUT .../variante`):
        aplica a despensa a ela e a casa com um "aguardando nota" do mesmo
        produto, se houver."""
        if nota.conferida_em is None or linha.produto_id is None:
            return
        quando = nota.emitida_em or nota.conferida_em
        item = self.session.scalar(
            select(ItemLista)
            .where(
                ItemLista.produto_id == linha.produto_id,
                ItemLista.situacao == SituacaoItem.COMPRADO,
                ItemLista.fechamento.is_(None),
                ItemLista.deleted_em.is_(None),
                ItemLista.comprado_em > quando - FOLGA_DA_MARCACAO,
            )
            .order_by(ItemLista.comprado_em, ItemLista.id)
            .limit(1)
            .with_for_update(of=ItemLista)
            .execution_options(populate_existing=True)
        )
        if item is not None:
            self._fechar_por_nota(item)
            linha.item_lista_id = item.id
        self.despensa.pela_nota(linha.produto_id, quando)
        self.session.flush()

    # -- plano ---------------------------------------------------------------

    def _nota(self, nota_id: int, travar: bool = False) -> NotaFiscal:
        consulta = select(NotaFiscal).where(
            NotaFiscal.id == nota_id, NotaFiscal.deleted_em.is_(None)
        )
        if travar:
            consulta = consulta.with_for_update(of=NotaFiscal)
        nota = self.session.scalar(consulta.execution_options(populate_existing=True))
        if nota is None:
            raise NaoEncontrado("nota", nota_id)
        if nota.status != StatusNota.LIDA:
            raise Conflito("A nota não foi lida; não há o que conferir.")
        return nota

    def _linhas(self, nota: NotaFiscal) -> list[NotaItem]:
        return list(
            self.session.scalars(
                select(NotaItem)
                .where(NotaItem.nota_fiscal_id == nota.id, NotaItem.deleted_em.is_(None))
                .order_by(NotaItem.linha_num)
                .execution_options(populate_existing=True)
            )
        )

    def _planejar(self, nota: NotaFiscal, travar: bool = False) -> _Plano:
        quando = nota.emitida_em or agora(self.session)
        plano = _Plano(nota=nota, quando=quando)

        por_produto: dict[int, list[NotaItem]] = {}
        for linha in self._linhas(nota):
            if linha.variante_id is None or linha.produto_id is None:
                plano.nao_reconhecidos.append(linha)
            else:
                por_produto.setdefault(linha.produto_id, []).append(linha)

        candidatos = self._candidatos(list(por_produto), travar)
        for produto_id, linhas in por_produto.items():
            doproduto = [i for i in candidatos if i.produto_id == produto_id]
            esperando = [
                i
                for i in doproduto
                if i.situacao == SituacaoItem.COMPRADO and self._elegivel(i, quando)
            ]
            pendente = next((i for i in doproduto if i.situacao == SituacaoItem.PENDENTE), None)
            escolhido = esperando[0] if esperando else pendente
            if escolhido is None:
                plano.extras.extend(linhas)
                continue
            if escolhido.situacao == SituacaoItem.COMPRADO:
                plano.confirmados.append((escolhido, linhas))
            else:
                plano.marcados.append((escolhido, linhas))
            diferenca = self._diferenca(escolhido, linhas)
            if diferenca is not None:
                plano.diferencas.append(diferenca)

        usados = {i.id for i, _ in plano.confirmados} | {i.id for i, _ in plano.marcados}
        if not plano.sem_lista:
            for item in candidatos:
                if item.id in usados:
                    continue
                if item.situacao == SituacaoItem.PENDENTE:
                    plano.continuam_pendentes.append(item)
                elif self._elegivel(item, quando):
                    plano.aguardando.append(item)

        acompanhadas = {
            d.produto_id: d
            for d in self.session.scalars(
                select(Despensa)
                .where(Despensa.produto_id.in_(list(por_produto)), Despensa.deleted_em.is_(None))
                .execution_options(populate_existing=True)
            )
        }
        plano.acompanhados = set(acompanhadas)
        for produto_id, linhas in por_produto.items():
            linha_despensa = acompanhadas.get(produto_id)
            if (
                linha_despensa is not None
                and linha_despensa.estado != EstadoDespensa.TEM
                and linha_despensa.estado_em < quando
            ):
                plano.despensa.append((produto_id, linhas[0].produto.nome, linha_despensa.estado))  # type: ignore[union-attr]
        return plano

    def _candidatos(self, produtos: list[int], travar: bool) -> list[ItemLista]:
        """Pendentes e comprados aguardando nota, os comprados mais antigos primeiro."""
        conjunto = (
            ItemLista.deleted_em.is_(None),
            (ItemLista.situacao == SituacaoItem.PENDENTE)
            | ((ItemLista.situacao == SituacaoItem.COMPRADO) & ItemLista.fechamento.is_(None)),
        )
        if travar and produtos:
            # Trava os envolvidos; a leitura abaixo já vê o que o outro confirmou.
            self.session.execute(
                select(ItemLista.id)
                .where(*conjunto, ItemLista.produto_id.in_(produtos))
                .order_by(ItemLista.id)
                .with_for_update(of=ItemLista)
            ).all()
        return list(
            self.session.scalars(
                select(ItemLista)
                .where(*conjunto)
                .order_by(ItemLista.comprado_em.asc().nulls_last(), ItemLista.id)
                .execution_options(populate_existing=True)
            )
        )

    @staticmethod
    def _elegivel(item: ItemLista, quando: datetime) -> bool:
        """O comprado só casa com nota emitida depois de `comprado_em` menos 1 dia."""
        assert item.comprado_em is not None
        return quando > item.comprado_em - FOLGA_DA_MARCACAO

    @staticmethod
    def _diferenca(item: ItemLista, linhas: list[NotaItem]) -> _Diferenca | None:
        """Quantidade menor que a pedida, só quando as unidades batem: lista em
        `un` e nota em UN, ou lista em `kg` e variante pesada. Sem quantidade
        na lista, nunca é menor. As linhas do mesmo produto somam antes."""
        if item.quantidade is None or item.unidade is None:
            return None
        unidade = item.unidade.strip().lower()
        veio = Decimal(0)
        if unidade == "un":
            for linha in linhas:
                na_nota = (linha.unidade or "").strip().upper()
                if na_nota not in UNIDADES_DE_CONTAGEM or (
                    linha.variante is not None and linha.variante.pesada
                ):
                    return None
                veio += linha.quantidade
        elif unidade == "kg":
            for linha in linhas:
                na_nota = (linha.unidade or "").strip().upper()
                if linha.variante is None or not linha.variante.pesada:
                    return None
                if na_nota == "KG":
                    veio += linha.quantidade
                elif na_nota == "G":
                    veio += linha.quantidade / 1000
                else:
                    return None
        else:
            return None
        if veio >= item.quantidade:
            return None
        return _Diferenca(item=item, pedido=item.quantidade, veio=veio, unidade=unidade)

    # -- aplicação --------------------------------------------------------------

    def _aplicar(self, plano: _Plano, volta: dict[int, bool]) -> None:
        for item, linhas in plano.confirmados:
            self._fechar_por_nota(item)
            self._ligar(linhas, item)
        for item, linhas in plano.marcados:
            item.situacao = SituacaoItem.COMPRADO
            item.comprado_por = self.quem
            item.comprado_em = plano.quando
            self._fechar_por_nota(item)
            self._ligar(linhas, item)
        self.session.flush()

        for d in plano.diferencas:
            if volta.get(d.item.id):
                self._devolver_a_lista(d)
        for produto_id, _nome, _antes in plano.despensa:
            self.despensa.pela_nota(produto_id, plano.quando)

        plano.nota.conferida_em = func.now()
        plano.nota.conferida_por = self.quem
        self.session.flush()
        self.session.refresh(plano.nota)

    def _fechar_por_nota(self, item: ItemLista) -> None:
        item.fechamento = FechamentoItem.NOTA
        item.fechado_em = func.now()
        item.fechado_por = AUTOR_LEITURA
        self.session.flush()

    @staticmethod
    def _ligar(linhas: list[NotaItem], item: ItemLista) -> None:
        for linha in linhas:
            linha.item_lista_id = item.id

    def _devolver_a_lista(self, d: _Diferenca) -> None:
        """A diferença vira um pendente (`origem = nota`), ou soma ao pendente
        que já existe (pendente único)."""
        for _ in range(3):
            criado = self.session.execute(
                insert(ItemLista)
                .values(
                    produto_id=d.item.produto_id,
                    quantidade=d.falta,
                    unidade=d.item.unidade,
                    situacao=SituacaoItem.PENDENTE,
                    origem=OrigemItem.NOTA,
                    adicionado_por=self.quem,
                )
                .on_conflict_do_nothing()
                .returning(ItemLista.id)
            ).scalar()
            if criado is not None:
                return
            pendente = ListaService(self.session, self.quem).pendente(d.item.produto_id)
            if pendente is None:
                continue
            same = (pendente.unidade or "").strip().lower() == d.unidade
            if pendente.quantidade is not None and same:
                pendente.quantidade = pendente.quantidade + d.falta
                self.session.flush()
            return
        raise Conflito("A lista mudou várias vezes seguidas; tente de novo.")

    # -- resposta ------------------------------------------------------------------

    def _resposta(
        self, plano: _Plano, estado: str, volta: dict[int, bool] | None
    ) -> ConferenciaResposta:
        agora_ = agora(self.session)
        return ConferenciaResposta(
            nota_id=plano.nota.id,
            conferencia="sem_lista" if plano.sem_lista and estado == "pendente" else estado,
            confirmados=[
                Confirmado(
                    item_lista_id=i.id,
                    produto=i.produto.nome,
                    linhas=[ln.linha_num for ln in linhas],
                    estava="aguardando_nota",
                )
                for i, linhas in plano.confirmados
            ],
            marcados=[
                Marcado(
                    item_lista_id=i.id,
                    produto=i.produto.nome,
                    linhas=[ln.linha_num for ln in linhas],
                    aviso=AVISO_MARCADO,
                )
                for i, linhas in plano.marcados
            ],
            extras=[self._extra(ln, ln.produto_id in plano.acompanhados) for ln in plano.extras],
            continuam_pendentes=[
                ContinuaPendente(item_lista_id=i.id, produto=i.produto.nome)
                for i in plano.continuam_pendentes
            ],
            aguardando_nota=[
                AguardandoNota(
                    item_lista_id=i.id,
                    produto=i.produto.nome,
                    comprado_em=i.comprado_em,
                    dias=max((agora_ - i.comprado_em).days, 0),  # type: ignore[operator]
                )
                for i in plano.aguardando
            ],
            diferencas=[
                Diferenca(
                    item_lista_id=d.item.id,
                    produto=d.item.produto.nome,
                    pedido=_txt(d.pedido),
                    veio=_txt(d.veio),
                    unidade=d.unidade,
                    pergunta=(f"Os {_txt(d.falta)} {d.unidade} que faltaram voltam para a lista?"),
                    volta=None if volta is None else volta.get(d.item.id),
                )
                for d in plano.diferencas
            ],
            nao_reconhecidos=[
                NaoReconhecido(linha=ln.linha_num, descricao_original=ln.descricao_original)
                for ln in plano.nao_reconhecidos
            ],
            despensa=[
                MudancaDespensa(
                    produto_id=produto_id, produto=nome, antes=antes.value, depois="tem"
                )
                for produto_id, nome, antes in plano.despensa
            ],
        )

    @staticmethod
    def _extra(linha: NotaItem, acompanhado: bool) -> Extra:
        assert linha.produto_id is not None and linha.produto is not None
        return Extra(
            linha=linha.linha_num,
            produto_id=linha.produto_id,
            produto=linha.produto.nome,
            variante=linha.variante.nome if linha.variante is not None else None,
            acompanhado=acompanhado,
            acao=None if acompanhado else "acompanhar_na_despensa",
        )

    def _feita(self, nota: NotaFiscal) -> ConferenciaResposta:
        """Nota já conferida: o que foi aplicado, reconstruído do que ficou
        gravado (`item_lista_id` nas linhas). Não muda nada."""
        linhas = self._linhas(nota)
        por_item: dict[int, list[NotaItem]] = {}
        extras: list[NotaItem] = []
        nao_reconhecidos: list[NotaItem] = []
        for linha in linhas:
            if linha.variante_id is None:
                nao_reconhecidos.append(linha)
            elif linha.item_lista_id is None:
                extras.append(linha)
            else:
                por_item.setdefault(linha.item_lista_id, []).append(linha)

        itens = {
            i.id: i
            for i in self.session.scalars(
                select(ItemLista)
                .where(ItemLista.id.in_(list(por_item)))
                .execution_options(populate_existing=True)
            )
        }
        marcado_em = nota.emitida_em or nota.conferida_em
        confirmados: list[Confirmado] = []
        marcados: list[Marcado] = []
        for item_id, doitem in por_item.items():
            item = itens[item_id]
            numeros = [ln.linha_num for ln in doitem]
            if item.comprado_por == nota.conferida_por and item.comprado_em == marcado_em:
                marcados.append(
                    Marcado(
                        item_lista_id=item_id,
                        produto=item.produto.nome,
                        linhas=numeros,
                        aviso=AVISO_MARCADO,
                    )
                )
            else:
                confirmados.append(
                    Confirmado(
                        item_lista_id=item_id,
                        produto=item.produto.nome,
                        linhas=numeros,
                        estava="aguardando_nota",
                    )
                )
        acompanhados = set(
            self.session.scalars(
                select(Despensa.produto_id).where(
                    Despensa.produto_id.in_([e.produto_id for e in extras if e.produto_id]),
                    Despensa.deleted_em.is_(None),
                )
            )
        )
        return ConferenciaResposta(
            nota_id=nota.id,
            conferencia="feita",
            confirmados=confirmados,
            marcados=marcados,
            extras=[self._extra(e, e.produto_id in acompanhados) for e in extras],
            nao_reconhecidos=[
                NaoReconhecido(linha=ln.linha_num, descricao_original=ln.descricao_original)
                for ln in nao_reconhecidos
            ],
        )
