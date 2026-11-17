"""Receitas e ingredientes (api-cardapio.md, Receitas).

Editar uma receita nunca muda um ingrediente no lugar: apaga (soft delete)
todos e cria os novos. A semana passada continua lendo os que estavam vivos
no fim dela (D-30), por `ingredientes_vivos`.
"""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta

from sqlalchemy import ColumnElement, case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras import tempo
from compras.enums import TipoRefeicao, UnidadeMedida
from compras.models import Produto, Receita, ReceitaIngrediente, Refeicao, Semana
from compras.normalizar import normalizar
from compras.schemas_cardapio import (
    IngredienteEntrada,
    IngredienteLeitura,
    ReceitaCorpo,
    ReceitaCriar,
    ReceitaDetalhe,
    ReceitaResumo,
)
from compras.services import conversao
from compras.services.base import Conflito, NaoEncontrado
from compras.services.produtos import ProdutoService


class ReceitaService:
    def __init__(self, session: Session, quem: str = "") -> None:
        self.session = session
        self.quem = quem

    # -- leitura ---------------------------------------------------------

    def listar(
        self,
        busca: str | None,
        tipo: TipoRefeicao | None,
        pode_antecipar: bool | None,
        limite: int,
        deslocamento: int,
        revisadas: bool | None = None,
    ) -> tuple[list[Receita], int]:
        filtro: list[ColumnElement[bool]] = [Receita.deleted_em.is_(None)]
        ordem: list[ColumnElement[int]] = []
        termo = normalizar(busca or "")
        if termo:
            filtro.append(Receita.nome_normalizado.contains(termo, autoescape=True))
            ordem.append(
                case((Receita.nome_normalizado.startswith(termo, autoescape=True), 0), else_=1)
            )
        if tipo is not None:
            filtro.append(Receita.tipo == tipo)
        if pode_antecipar is not None:
            filtro.append(Receita.pode_antecipar == pode_antecipar)
        if revisadas is not None:
            filtro.append(Receita.quantidades_revisadas == revisadas)
        total = self.session.scalar(select(func.count()).select_from(Receita).where(*filtro))
        receitas = self.session.scalars(
            select(Receita)
            .where(*filtro)
            .order_by(*ordem, Receita.nome_normalizado, Receita.id)
            .limit(limite)
            .offset(deslocamento)
        )
        return list(receitas), int(total or 0)

    def get(self, id_: int) -> Receita:
        receita = self.session.scalar(
            select(Receita)
            .where(Receita.id == id_, Receita.deleted_em.is_(None))
            .execution_options(populate_existing=True)
        )
        if receita is None:
            raise NaoEncontrado("receita", id_)
        return receita

    def detalhe(self, receita: Receita) -> ReceitaDetalhe:
        ingredientes = self.session.scalars(
            select(ReceitaIngrediente)
            .where(
                ReceitaIngrediente.receita_id == receita.id,
                ReceitaIngrediente.deleted_em.is_(None),
            )
            .order_by(ReceitaIngrediente.ordem, ReceitaIngrediente.id)
            .execution_options(populate_existing=True)
        )
        base = ReceitaResumo.model_validate(receita, from_attributes=True)
        return ReceitaDetalhe(
            **base.model_dump(),
            modo_preparo=receita.modo_preparo,
            ingredientes=[self._leitura(i) for i in ingredientes],
        )

    @staticmethod
    def _leitura(i: ReceitaIngrediente) -> IngredienteLeitura:
        p = i.produto
        return IngredienteLeitura(
            id=i.id,
            criado_em=i.criado_em,
            atualizado_em=i.atualizado_em,
            deleted_em=i.deleted_em,
            produto_id=i.produto_id,
            produto_nome=p.nome,
            quantidade=i.quantidade,
            unidade=i.unidade,
            observacao=i.observacao,
            ordem=i.ordem,
            converte=conversao.converte(
                i.quantidade if i.quantidade is not None else conversao.UM,
                i.unidade,
                p.medida_base,
                p.medida_por_unidade,
                p.unidade_padrao,
            ),
        )

    def ingredientes_vivos(
        self, receita_ids: Sequence[int], semana_inicio: date | None = None
    ) -> dict[int, list[ReceitaIngrediente]]:
        """Os ingredientes de cada receita, na ordem da receita.

        Sem `semana_inicio`, ou numa semana atual ou futura: os vivos agora.
        Numa semana passada: os vivos no fim do domingo dela (`criado_em` até
        lá, `deleted_em` nulo ou depois), para a edição da receita não
        reescrever o que se planejou (D-30).
        """
        consulta = (
            select(ReceitaIngrediente)
            .where(ReceitaIngrediente.receita_id.in_(list(receita_ids)))
            .order_by(
                ReceitaIngrediente.receita_id, ReceitaIngrediente.ordem, ReceitaIngrediente.id
            )
            .execution_options(populate_existing=True)
        )
        if semana_inicio is not None and tempo.passou(semana_inicio):
            fim = tempo.fim_do_domingo(semana_inicio)
            consulta = consulta.where(
                ReceitaIngrediente.criado_em <= fim,
                (ReceitaIngrediente.deleted_em.is_(None)) | (ReceitaIngrediente.deleted_em > fim),
            )
        else:
            consulta = consulta.where(ReceitaIngrediente.deleted_em.is_(None))
        por_receita: dict[int, list[ReceitaIngrediente]] = {r: [] for r in receita_ids}
        for ingrediente in self.session.scalars(consulta):
            por_receita[ingrediente.receita_id].append(ingrediente)
        return por_receita

    # -- escrita ---------------------------------------------------------

    def criar(self, dados: ReceitaCriar, revisada: bool = True) -> tuple[Receita, bool]:
        """(receita, criada agora). O mesmo `id_cliente` devolve a que existe.

        Quem cria a receita à mão a conhece: nasce com as quantidades revisadas
        por ele. A carga inicial passa `revisada=False` (quantidades estimadas).
        """
        anterior = self.session.scalar(
            select(Receita)
            .where(Receita.id_cliente == dados.id_cliente)
            .execution_options(populate_existing=True)
        )
        if anterior is not None:
            return anterior, False
        receita = self._nova(dados, dados.id_cliente, revisada)
        return receita, True

    def substituir(self, id_: int, dados: ReceitaCorpo) -> Receita:
        """Troca os campos e os ingredientes (os antigos levam soft delete)."""
        receita = self.get(id_)
        self._exigir_nome_livre(dados.nome, ignorar=id_)
        self._campos(receita, dados)
        self._salvar(receita, dados.nome)
        self.session.execute(
            update(ReceitaIngrediente)
            .where(
                ReceitaIngrediente.receita_id == id_,
                ReceitaIngrediente.deleted_em.is_(None),
            )
            .values(deleted_em=func.now())
        )
        self._ingredientes(receita.id, dados.ingredientes)
        self.session.flush()
        return self.get(id_)

    def conferir(self, id_: int) -> Receita:
        """ "Conferi, está certa". Já conferida: devolve como está, com o primeiro autor."""
        receita = self.session.scalar(
            select(Receita)
            .where(Receita.id == id_, Receita.deleted_em.is_(None))
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if receita is None:
            raise NaoEncontrado("receita", id_)
        if not receita.quantidades_revisadas:
            receita.quantidades_revisadas = True
            receita.revisadas_por = self.quem
            receita.revisadas_em = func.now()
            self.session.flush()
        return self.get(id_)

    def duplicar(self, id_: int) -> Receita:
        origem = self.get(id_)
        ingredientes = self.ingredientes_vivos([id_])[id_]
        nome = f"{origem.nome} (cópia)"
        n = 1
        while self._por_nome(normalizar(nome)) is not None:
            n += 1
            nome = f"{origem.nome} (cópia {n})"
        receita = Receita(
            nome=nome,
            nome_normalizado=normalizar(nome),
            tipo=origem.tipo,
            rendimento_porcoes=origem.rendimento_porcoes,
            tempo_preparo_min=origem.tempo_preparo_min,
            modo_preparo=origem.modo_preparo,
            pode_antecipar=origem.pode_antecipar,
            dura_dias=origem.dura_dias,
            pode_congelar=origem.pode_congelar,
            # Os mesmos ingredientes e quantidades: a conferência acompanha.
            quantidades_revisadas=origem.quantidades_revisadas,
            revisadas_por=origem.revisadas_por,
            revisadas_em=origem.revisadas_em,
        )
        self._salvar(receita, nome, novo=True)
        for ordem, i in enumerate(ingredientes):
            self.session.add(
                ReceitaIngrediente(
                    receita_id=receita.id,
                    produto_id=i.produto_id,
                    quantidade=i.quantidade,
                    unidade=i.unidade,
                    observacao=i.observacao,
                    ordem=ordem,
                )
            )
        self.session.flush()
        return self.get(receita.id)

    def remover(self, id_: int) -> Receita:
        """Soft delete. Usada em semana que não passou: 409, com as semanas."""
        receita = self.get(id_)
        semanas = self.semanas_em_uso(id_)
        if semanas:
            raise Conflito(
                f'"{receita.nome}" está no cardápio de semana que ainda não acabou.',
                {"semanas": [{"id": i, "inicio": d.isoformat()} for i, d in semanas]},
            )
        receita.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(receita)
        return receita

    def semanas_em_uso(self, receita_id: int) -> list[tuple[int, date]]:
        """Semanas vivas, atuais ou futuras, com refeição viva desta receita."""
        corte = tempo.hoje() - timedelta(days=6)
        linhas = self.session.execute(
            select(Semana.id, Semana.inicio)
            .join(Refeicao, Refeicao.semana_id == Semana.id)
            .where(
                Refeicao.receita_id == receita_id,
                Refeicao.deleted_em.is_(None),
                Semana.deleted_em.is_(None),
                Semana.inicio >= corte,
            )
            .distinct()
            .order_by(Semana.inicio)
        )
        return [(int(i), d) for i, d in linhas]

    # -- apoio -----------------------------------------------------------

    def _nova(self, dados: ReceitaCorpo, id_cliente: uuid.UUID | None, revisada: bool) -> Receita:
        self._exigir_nome_livre(dados.nome)
        receita = Receita(id_cliente=id_cliente)
        if revisada:
            receita.quantidades_revisadas = True
            receita.revisadas_por = self.quem
            receita.revisadas_em = func.now()
        self._campos(receita, dados)
        self._salvar(receita, dados.nome, novo=True)
        self._ingredientes(receita.id, dados.ingredientes)
        self.session.flush()
        return self.get(receita.id)

    @staticmethod
    def _campos(receita: Receita, dados: ReceitaCorpo) -> None:
        receita.nome = dados.nome
        receita.nome_normalizado = normalizar(dados.nome)
        receita.tipo = dados.tipo
        receita.rendimento_porcoes = dados.rendimento_porcoes
        receita.tempo_preparo_min = dados.tempo_preparo_min
        receita.modo_preparo = dados.modo_preparo
        receita.pode_antecipar = dados.pode_antecipar
        receita.dura_dias = dados.dura_dias
        receita.pode_congelar = dados.pode_congelar

    def _salvar(self, receita: Receita, nome: str, novo: bool = False) -> None:
        try:
            with self.session.begin_nested():
                if novo:
                    self.session.add(receita)
                self.session.flush()
        except IntegrityError as erro:
            raise Conflito(f'Já existe a receita "{nome}".') from erro

    def _exigir_nome_livre(self, nome: str, ignorar: int | None = None) -> None:
        existente = self._por_nome(normalizar(nome))
        if existente is not None and existente.id != ignorar:
            resumo = ReceitaResumo.model_validate(existente, from_attributes=True)
            raise Conflito(
                f'Já existe a receita "{existente.nome}".',
                {"receita": resumo.model_dump(mode="json")},
            )

    def _por_nome(self, normalizado: str) -> Receita | None:
        return self.session.scalar(
            select(Receita).where(
                Receita.nome_normalizado == normalizado, Receita.deleted_em.is_(None)
            )
        )

    def por_nome(self, nome: str) -> Receita | None:
        return self._por_nome(normalizar(nome))

    def _ingredientes(self, receita_id: int, entradas: Sequence[IngredienteEntrada]) -> None:
        produtos = ProdutoService(self.session)
        for ordem, e in enumerate(entradas):
            produto: Produto
            if e.produto_id is not None:
                produto = produtos.get(e.produto_id)
            else:
                assert e.produto_nome is not None
                produto = produtos.obter_ou_criar(e.produto_nome)
            self.session.add(
                ReceitaIngrediente(
                    receita_id=receita_id,
                    produto_id=produto.id,
                    quantidade=e.quantidade,
                    unidade=UnidadeMedida(e.unidade),
                    observacao=e.observacao,
                    ordem=ordem,
                )
            )
