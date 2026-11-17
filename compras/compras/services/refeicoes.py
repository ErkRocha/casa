"""Refeições de uma semana: o prato, o dia, o tipo e quem come (D-30).

Cada linha de `refeicoes` é um prato; o almoço de arroz, feijão e frango são
três linhas no mesmo dia e tipo. `refeicao_pessoas` diz quem come e quanto:
`porcoes` nulo é a porção padrão da pessoa, e por isso mudar o perfil muda
todas as refeições não ajustadas.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from compras.models import Pessoa, Receita, Refeicao, RefeicaoPessoa, Semana
from compras.schemas_cardapio import (
    IngredienteDaSemana,
    PessoaNaRefeicao,
    PessoaPorcao,
    ReceitaNaRefeicao,
    RefeicaoCriar,
    RefeicaoLeitura,
)
from compras.services.base import NaoEncontrado, RegraViolada
from compras.services.conversao import tres_casas
from compras.services.pessoas import PessoaService
from compras.services.receitas import ReceitaService


class RefeicaoService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    # -- leitura ---------------------------------------------------------

    def get(self, id_: int) -> Refeicao:
        refeicao = self.session.scalar(
            select(Refeicao)
            .where(Refeicao.id == id_, Refeicao.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        if refeicao is None:
            raise NaoEncontrado("refeição", id_)
        return refeicao

    def da_semana(self, semana_id: int) -> list[Refeicao]:
        return list(
            self.session.scalars(
                select(Refeicao)
                .where(Refeicao.semana_id == semana_id, Refeicao.deleted_em.is_(None))
                .order_by(Refeicao.dia, Refeicao.tipo, Refeicao.ordem, Refeicao.id)
                .execution_options(populate_existing=True)
            )
        )

    def porcoes(self, refeicao_ids: Sequence[int]) -> dict[int, Decimal]:
        """Porções de cada refeição: a soma, por pessoa, do ajuste ou da porção padrão.

        A soma é do banco (`numeric`), sem float. Pessoa apagada depois conta
        enquanto a linha dela estiver viva: a refeição passada mantém o que foi.
        """
        if not refeicao_ids:
            return {}
        linhas = self.session.execute(
            select(
                RefeicaoPessoa.refeicao_id,
                func.sum(func.coalesce(RefeicaoPessoa.porcoes, Pessoa.porcao_padrao)),
            )
            .join(Pessoa, Pessoa.id == RefeicaoPessoa.pessoa_id)
            .where(
                RefeicaoPessoa.refeicao_id.in_(list(refeicao_ids)),
                RefeicaoPessoa.deleted_em.is_(None),
            )
            .group_by(RefeicaoPessoa.refeicao_id)
        )
        resultado = {i: Decimal(0) for i in refeicao_ids}
        for refeicao_id, soma in linhas:
            resultado[int(refeicao_id)] = Decimal(soma)
        return resultado

    def leituras(
        self,
        refeicoes: Sequence[Refeicao],
        com_ingredientes: bool = False,
        semana_inicio: date | None = None,
    ) -> list[RefeicaoLeitura]:
        """As refeições prontas para a tela, na ordem recebida."""
        ids = [r.id for r in refeicoes]
        pessoas: dict[int, list[PessoaNaRefeicao]] = {i: [] for i in ids}
        if ids:
            linhas = self.session.execute(
                select(RefeicaoPessoa, Pessoa)
                .join(Pessoa, Pessoa.id == RefeicaoPessoa.pessoa_id)
                .where(RefeicaoPessoa.refeicao_id.in_(ids), RefeicaoPessoa.deleted_em.is_(None))
                .order_by(func.lower(Pessoa.nome), Pessoa.id)
                .execution_options(populate_existing=True)
            )
            for rp, pessoa in linhas:
                pessoas[rp.refeicao_id].append(
                    PessoaNaRefeicao(
                        pessoa_id=pessoa.id,
                        nome=pessoa.nome,
                        porcoes=rp.porcoes if rp.porcoes is not None else pessoa.porcao_padrao,
                        ajustada=rp.porcoes is not None,
                    )
                )

        receita_ids = sorted({r.receita_id for r in refeicoes if r.receita_id is not None})
        receitas: dict[int, Receita] = {}
        ingredientes: dict[int, list[IngredienteDaSemana]] = {}
        if receita_ids:
            receitas = {
                r.id: r
                for r in self.session.scalars(
                    select(Receita)
                    .where(Receita.id.in_(receita_ids))
                    .execution_options(populate_existing=True)
                )
            }
            if com_ingredientes:
                vivos = ReceitaService(self.session).ingredientes_vivos(receita_ids, semana_inicio)
                ingredientes = {
                    rid: [
                        IngredienteDaSemana(
                            produto_id=i.produto_id,
                            produto_nome=i.produto.nome,
                            quantidade=i.quantidade,
                            unidade=i.unidade,
                            observacao=i.observacao,
                        )
                        for i in lista
                    ]
                    for rid, lista in vivos.items()
                }

        saida: list[RefeicaoLeitura] = []
        for r in refeicoes:
            receita = receitas.get(r.receita_id) if r.receita_id is not None else None
            total = sum((p.porcoes for p in pessoas[r.id]), Decimal(0))
            saida.append(
                RefeicaoLeitura(
                    id=r.id,
                    criado_em=r.criado_em,
                    atualizado_em=r.atualizado_em,
                    deleted_em=r.deleted_em,
                    semana_id=r.semana_id,
                    dia=r.dia,
                    tipo=r.tipo,
                    receita=ReceitaNaRefeicao(
                        id=receita.id,
                        nome=receita.nome,
                        rendimento_porcoes=receita.rendimento_porcoes,
                        tempo_preparo_min=receita.tempo_preparo_min,
                        apagada=receita.deleted_em is not None,
                        ingredientes=ingredientes.get(receita.id) if com_ingredientes else None,
                    )
                    if receita is not None
                    else None,
                    observacao=r.observacao,
                    ordem=r.ordem,
                    pessoas=pessoas[r.id],
                    porcoes=total,
                    fator=tres_casas(total / receita.rendimento_porcoes)
                    if receita is not None
                    else None,
                )
            )
        return saida

    def leitura(self, refeicao: Refeicao) -> RefeicaoLeitura:
        return self.leituras([refeicao])[0]

    # -- escrita ---------------------------------------------------------

    def criar(self, semana: Semana, dados: RefeicaoCriar) -> Refeicao:
        self._dia_na_semana(semana, dados.dia)
        if dados.receita_id is not None:
            ReceitaService(self.session).get(dados.receita_id)
        pessoas = self._pessoas_da_refeicao(dados.pessoas)
        proxima = self.session.scalar(
            select(func.coalesce(func.max(Refeicao.ordem) + 1, 0)).where(
                Refeicao.semana_id == semana.id,
                Refeicao.dia == dados.dia,
                Refeicao.tipo == dados.tipo,
                Refeicao.deleted_em.is_(None),
            )
        )
        refeicao = Refeicao(
            semana_id=semana.id,
            dia=dados.dia,
            tipo=dados.tipo,
            receita_id=dados.receita_id,
            observacao=(dados.observacao or "").strip() or None,
            ordem=int(proxima or 0),
        )
        self.session.add(refeicao)
        self.session.flush()
        for pessoa_id, porcoes in pessoas:
            self.session.add(
                RefeicaoPessoa(refeicao_id=refeicao.id, pessoa_id=pessoa_id, porcoes=porcoes)
            )
        self.session.flush()
        return self.get(refeicao.id)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Refeicao:
        refeicao = self.get(id_)
        semana = self._semana(refeicao.semana_id)
        if dados.get("dia") is not None:
            self._dia_na_semana(semana, dados["dia"])
            refeicao.dia = dados["dia"]
        if dados.get("tipo") is not None:
            refeicao.tipo = dados["tipo"]
        if "receita_id" in dados:
            if dados["receita_id"] is not None:
                ReceitaService(self.session).get(dados["receita_id"])
            refeicao.receita_id = dados["receita_id"]
        if "observacao" in dados:
            refeicao.observacao = (dados["observacao"] or "").strip() or None
        if dados.get("ordem") is not None:
            refeicao.ordem = dados["ordem"]
        if refeicao.receita_id is None and not refeicao.observacao:
            raise RegraViolada("a refeição precisa de receita_id ou observacao")
        self.session.flush()
        return self.get(id_)

    def definir_pessoas(self, id_: int, lista: Sequence[PessoaPorcao]) -> Refeicao:
        """Quem come e quanto. `porcoes` nulo volta ao padrão do perfil."""
        refeicao = self.get(id_)
        novas = self._pessoas_da_refeicao(lista)
        atuais = {
            rp.pessoa_id: rp
            for rp in self.session.scalars(
                select(RefeicaoPessoa)
                .where(RefeicaoPessoa.refeicao_id == id_, RefeicaoPessoa.deleted_em.is_(None))
                .execution_options(populate_existing=True)
            )
        }
        quem_fica = {pessoa_id for pessoa_id, _ in novas}
        for pessoa_id, rp in atuais.items():
            if pessoa_id not in quem_fica:
                rp.deleted_em = func.now()
        for pessoa_id, porcoes in novas:
            if pessoa_id in atuais:
                atuais[pessoa_id].porcoes = porcoes
            else:
                self.session.add(
                    RefeicaoPessoa(refeicao_id=id_, pessoa_id=pessoa_id, porcoes=porcoes)
                )
        self.session.flush()
        return refeicao

    def remover(self, id_: int) -> Refeicao:
        refeicao = self.get(id_)
        self.session.execute(
            update(RefeicaoPessoa)
            .where(RefeicaoPessoa.refeicao_id == id_, RefeicaoPessoa.deleted_em.is_(None))
            .values(deleted_em=func.now())
        )
        refeicao.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(refeicao)
        return refeicao

    # -- apoio -----------------------------------------------------------

    def _semana(self, semana_id: int) -> Semana:
        semana = self.session.get(Semana, semana_id)
        assert semana is not None
        return semana

    @staticmethod
    def _dia_na_semana(semana: Semana, dia: date) -> None:
        if not semana.inicio <= dia <= semana.inicio + timedelta(days=6):
            raise RegraViolada(
                f"o dia {dia.isoformat()} está fora da semana de {semana.inicio.isoformat()}"
            )

    def _pessoas_da_refeicao(
        self, lista: Sequence[PessoaPorcao] | None
    ) -> list[tuple[int, Decimal | None]]:
        """(pessoa_id, porcoes); sem lista, todas as vivas com a porção padrão."""
        pessoas = PessoaService(self.session)
        if lista is None:
            return [(p.id, None) for p in pessoas.listar()]
        ids = [p.pessoa_id for p in lista]
        if len(set(ids)) != len(ids):
            raise RegraViolada("pessoa repetida na refeição")
        for pessoa_id in ids:
            pessoas.get(pessoa_id)
        return [(p.pessoa_id, p.porcoes) for p in lista]
