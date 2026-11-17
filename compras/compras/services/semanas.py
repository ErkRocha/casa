"""Semanas do cardápio: de segunda a domingo (D-30).

Uma semana nasce com a sessão de preparo do domingo anterior. A que já
passou (domingo antes de hoje, São Paulo) ainda pode ser editada, mas não
gera lista: vira histórico.
"""

from datetime import date, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras import tempo
from compras.models import (
    Pessoa,
    Receita,
    Refeicao,
    RefeicaoPessoa,
    Semana,
    SessaoPreparo,
)
from compras.schemas_cardapio import (
    AvisoRefeicao,
    DiaLeitura,
    SemanaDetalhe,
    SemanaResumo,
    SessaoLeitura,
)
from compras.services.base import Conflito, NaoEncontrado, RegraViolada
from compras.services.refeicoes import RefeicaoService

#: Rótulo da sessão que a semana ganha ao nascer.
ROTULO_DOMINGO = "domingo"


def exigir_segunda(dia: date, nome: str = "inicio") -> None:
    if dia.isoweekday() != 1:
        raise RegraViolada(f"{nome} precisa ser uma segunda-feira ({dia.isoformat()} não é)")


class SemanaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    # -- leitura ---------------------------------------------------------

    def get(self, id_: int) -> Semana:
        semana = self.session.scalar(
            select(Semana)
            .where(Semana.id == id_, Semana.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        if semana is None:
            raise NaoEncontrado("semana", id_)
        return semana

    def por_inicio(self, inicio: date) -> Semana | None:
        """A semana viva que começa em `inicio` (segunda-feira; senão 422)."""
        exigir_segunda(inicio)
        return self.session.scalar(
            select(Semana)
            .where(Semana.inicio == inicio, Semana.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )

    def listar(self, limite: int, deslocamento: int) -> tuple[list[SemanaResumo], int]:
        """Mais recentes primeiro, com quantas refeições cada uma tem."""
        total = self.session.scalar(
            select(func.count()).select_from(Semana).where(Semana.deleted_em.is_(None))
        )
        linhas = self.session.execute(
            select(Semana, func.count(Refeicao.id))
            .outerjoin(Refeicao, (Refeicao.semana_id == Semana.id) & Refeicao.deleted_em.is_(None))
            .where(Semana.deleted_em.is_(None))
            .group_by(Semana.id)
            .order_by(Semana.inicio.desc())
            .limit(limite)
            .offset(deslocamento)
            .execution_options(populate_existing=True)
        )
        itens = [
            SemanaResumo(
                id=s.id,
                criado_em=s.criado_em,
                atualizado_em=s.atualizado_em,
                deleted_em=s.deleted_em,
                inicio=s.inicio,
                observacao=s.observacao,
                passada=tempo.passou(s.inicio),
                refeicoes=int(n),
            )
            for s, n in linhas
        ]
        return itens, int(total or 0)

    def sessoes(self, semana_id: int) -> list[SessaoPreparo]:
        return list(
            self.session.scalars(
                select(SessaoPreparo)
                .where(SessaoPreparo.semana_id == semana_id, SessaoPreparo.deleted_em.is_(None))
                .order_by(SessaoPreparo.data, SessaoPreparo.id)
                .execution_options(populate_existing=True)
            )
        )

    def detalhe(self, semana: Semana, com_ingredientes: bool = False) -> SemanaDetalhe:
        """A semana com as refeições por dia e tipo, quem come e as sessões."""
        refeicoes = RefeicaoService(self.session)
        leituras = refeicoes.leituras(
            refeicoes.da_semana(semana.id), com_ingredientes, semana.inicio
        )
        dias = [
            DiaLeitura(
                dia=semana.inicio + timedelta(days=n),
                refeicoes=[r for r in leituras if r.dia == semana.inicio + timedelta(days=n)],
            )
            for n in range(7)
        ]
        return SemanaDetalhe(
            id=semana.id,
            criado_em=semana.criado_em,
            atualizado_em=semana.atualizado_em,
            deleted_em=semana.deleted_em,
            inicio=semana.inicio,
            observacao=semana.observacao,
            passada=tempo.passou(semana.inicio),
            dias=dias,
            sessoes=[
                SessaoLeitura.model_validate(s, from_attributes=True)
                for s in self.sessoes(semana.id)
            ],
        )

    # -- escrita ---------------------------------------------------------

    def criar(self, inicio: date, observacao: str | None = None) -> tuple[Semana, bool]:
        """(semana, criada agora), com a sessão do domingo anterior. Já existe: a que existe."""
        existente = self.por_inicio(inicio)
        if existente is not None:
            return existente, False
        try:
            semana = self._inserir(inicio, observacao, com_sessao_padrao=True)
        except IntegrityError:
            # As duas criando a mesma semana ao mesmo tempo.
            existente = self.por_inicio(inicio)
            if existente is None:
                raise
            return existente, False
        return semana, True

    def remover(self, id_: int) -> Semana:
        """Soft delete da semana, das refeições e das sessões. O que ela pôs na
        lista fica: já é da lista."""
        semana = self.get(id_)
        refeicoes = select(Refeicao.id).where(
            Refeicao.semana_id == id_, Refeicao.deleted_em.is_(None)
        )
        self.session.execute(
            update(RefeicaoPessoa)
            .where(RefeicaoPessoa.refeicao_id.in_(refeicoes), RefeicaoPessoa.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        self.session.execute(
            update(Refeicao)
            .where(Refeicao.semana_id == id_, Refeicao.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        self.session.execute(
            update(SessaoPreparo)
            .where(SessaoPreparo.semana_id == id_, SessaoPreparo.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        semana.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(semana)
        return semana

    def copiar(self, id_: int, destino: date) -> tuple[Semana, list[AvisoRefeicao]]:
        """Copia refeições, pessoas, ajustes e sessões para a semana `destino`.

        Cria o destino se precisar, ou usa o que existe sem refeição. Destino
        com refeição viva: 409. Refeição de receita apagada vai sem receita,
        com a observação "receita apagada: <nome>", e volta como aviso.
        """
        exigir_segunda(destino, "destino")
        origem = self.get(id_)
        if destino == origem.inicio:
            raise RegraViolada("o destino é a própria semana")
        alvo = self.por_inicio(destino)
        if alvo is not None:
            ocupada = self.session.scalar(
                select(func.count())
                .select_from(Refeicao)
                .where(Refeicao.semana_id == alvo.id, Refeicao.deleted_em.is_(None))
            )
            if ocupada:
                raise Conflito(
                    "A semana de destino já tem refeições.",
                    {"semana": {"id": alvo.id, "inicio": alvo.inicio.isoformat()}},
                )
        else:
            alvo = self._inserir(destino, None, com_sessao_padrao=False)

        deslocamento = destino - origem.inicio
        avisos: list[AvisoRefeicao] = []
        refeicoes = RefeicaoService(self.session).da_semana(origem.id)
        receitas = {
            r.id: r
            for r in self.session.scalars(
                select(Receita).where(
                    Receita.id.in_({x.receita_id for x in refeicoes if x.receita_id is not None})
                )
            )
        }
        for original in refeicoes:
            receita_id = original.receita_id
            observacao = original.observacao
            receita = receitas.get(receita_id) if receita_id is not None else None
            if receita is not None and receita.deleted_em is not None:
                receita_id = None
                texto = f"receita apagada: {receita.nome}"
                observacao = f"{texto}; {observacao}" if observacao else texto
            nova = Refeicao(
                semana_id=alvo.id,
                dia=original.dia + deslocamento,
                tipo=original.tipo,
                receita_id=receita_id,
                observacao=observacao,
                ordem=original.ordem,
            )
            self.session.add(nova)
            self.session.flush()
            if receita_id is None and receita is not None:
                avisos.append(
                    AvisoRefeicao(refeicao_id=nova.id, texto=f"receita apagada: {receita.nome}")
                )
            vivas = self.session.execute(
                select(RefeicaoPessoa.pessoa_id, RefeicaoPessoa.porcoes)
                .join(Pessoa, Pessoa.id == RefeicaoPessoa.pessoa_id)
                .where(
                    RefeicaoPessoa.refeicao_id == original.id,
                    RefeicaoPessoa.deleted_em.is_(None),
                    Pessoa.deleted_em.is_(None),
                )
            )
            for pessoa_id, porcoes in vivas:
                self.session.add(
                    RefeicaoPessoa(refeicao_id=nova.id, pessoa_id=pessoa_id, porcoes=porcoes)
                )

        ocupadas = {s.data for s in self.sessoes(alvo.id)}
        for sessao in self.sessoes(origem.id):
            data = sessao.data + deslocamento
            if data not in ocupadas:
                self.session.add(SessaoPreparo(semana_id=alvo.id, data=data, rotulo=sessao.rotulo))
        self.session.flush()
        return self.get(alvo.id), avisos

    # -- apoio -----------------------------------------------------------

    def _inserir(self, inicio: date, observacao: str | None, com_sessao_padrao: bool) -> Semana:
        semana = Semana(inicio=inicio, observacao=(observacao or "").strip() or None)
        with self.session.begin_nested():
            self.session.add(semana)
            self.session.flush()
        if com_sessao_padrao:
            self.session.add(
                SessaoPreparo(
                    semana_id=semana.id, data=inicio - timedelta(days=1), rotulo=ROTULO_DOMINGO
                )
            )
            self.session.flush()
        return self.get(semana.id)
