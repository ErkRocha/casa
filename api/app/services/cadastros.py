"""Services dos cadastros do v1."""

from __future__ import annotations

import unicodedata
from datetime import date
from typing import Any

from sqlalchemy import select

from app.models import Categoria, Conta, FormaPagamento, Local, Orcamento, Pessoa
from app.schemas.common import Paginacao
from app.services.base import CrudService, RegraViolada


def normalizar_nome(nome: str) -> str:
    """Upper sem acento — é a chave de matching de local na ingestão.

    "Pão de Açúcar" -> "PAO DE ACUCAR"
    """
    sem_acento = unicodedata.normalize("NFKD", nome)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def primeiro_dia_do_mes(d: date) -> date:
    """Competência é sempre o dia 1º do mês de referência (D-02)."""
    return d.replace(day=1)


class PessoaService(CrudService[Pessoa]):
    model = Pessoa
    nome_recurso = "pessoa"


class ContaService(CrudService[Conta]):
    model = Conta
    nome_recurso = "conta"


class FormaPagamentoService(CrudService[FormaPagamento]):
    model = FormaPagamento
    nome_recurso = "forma de pagamento"


class CategoriaService(CrudService[Categoria]):
    model = Categoria
    nome_recurso = "categoria"

    def criar(self, dados: dict[str, Any]) -> Categoria:
        self._checa_pai(dados.get("categoria_pai_id"))
        return super().criar(dados)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Categoria:
        if "categoria_pai_id" in dados:
            self._checa_pai(dados["categoria_pai_id"], filho_id=id_)
        return super().atualizar(id_, dados)

    def _checa_pai(self, pai_id: int | None, filho_id: int | None = None) -> None:
        """Máximo 2 níveis, e nada de ciclo.

        O banco tem trigger para isso; aqui o erro sai como 422 legível em vez
        de exceção crua do Postgres.
        """
        if pai_id is None:
            return
        if filho_id is not None and pai_id == filho_id:
            raise RegraViolada("Uma categoria não pode ser pai de si mesma.")

        pai = self.session.get(Categoria, pai_id)
        if pai is None or pai.deleted_em is not None:
            raise RegraViolada(f"Categoria pai {pai_id} não existe.")
        if pai.categoria_pai_id is not None:
            raise RegraViolada(
                "A hierarquia de categorias tem no máximo 2 níveis — "
                f"'{pai.nome}' já é uma subcategoria."
            )

    def arvore(self) -> list[tuple[Categoria, list[Categoria]]]:
        """Raízes com as filhas, na ordem em que a tela de filtro mostra."""
        todas = list(
            self.session.scalars(
                select(Categoria).where(Categoria.deleted_em.is_(None)).order_by(Categoria.id)
            )
        )
        raizes = [c for c in todas if c.categoria_pai_id is None]
        por_pai: dict[int, list[Categoria]] = {}
        for cat in todas:
            if cat.categoria_pai_id is not None:
                por_pai.setdefault(cat.categoria_pai_id, []).append(cat)

        return [(raiz, por_pai.get(raiz.id, [])) for raiz in raizes]


class LocalService(CrudService[Local]):
    model = Local
    nome_recurso = "local"

    def criar(self, dados: dict[str, Any]) -> Local:
        dados["nome_normalizado"] = normalizar_nome(dados["nome"])
        return super().criar(dados)

    def atualizar(self, id_: int, dados: dict[str, Any]) -> Local:
        if "nome" in dados and dados["nome"] is not None:
            dados["nome_normalizado"] = normalizar_nome(dados["nome"])
        return super().atualizar(id_, dados)

    def buscar_ou_criar(self, nome: str) -> Local:
        """Usado pelo lançamento manual: o usuário digita o local livre.

        Casa pelo nome normalizado, então "Pão de Açúcar" e "PAO DE ACUCAR"
        convergem para a mesma linha em vez de criar duas.
        """
        normalizado = normalizar_nome(nome)
        existente = self.session.scalar(
            select(Local).where(Local.nome_normalizado == normalizado, Local.deleted_em.is_(None))
        )
        if existente is not None:
            return existente
        return self.criar({"nome": nome.strip()})


class OrcamentoService(CrudService[Orcamento]):
    model = Orcamento
    nome_recurso = "orçamento"

    def criar(self, dados: dict[str, Any]) -> Orcamento:
        dados["competencia"] = primeiro_dia_do_mes(dados["competencia"])
        self._checa_categoria_raiz(dados["categoria_id"])
        return super().criar(dados)

    def listar_por_competencia(
        self, competencia: date, paginacao: Paginacao
    ) -> tuple[list[Orcamento], int]:
        competencia = primeiro_dia_do_mes(competencia)
        query = self._base_query().where(Orcamento.competencia == competencia)
        itens = list(
            self.session.scalars(
                query.order_by(Orcamento.id).limit(paginacao.limit).offset(paginacao.offset)
            )
        )
        total = len(
            list(
                self.session.scalars(self._base_query().where(Orcamento.competencia == competencia))
            )
        )
        return itens, total

    def _checa_categoria_raiz(self, categoria_id: int) -> None:
        """Orçamento é por categoria raiz.

        Meta em subcategoria com meta no pai contaria o mesmo gasto duas vezes
        na tela de orçamento.
        """
        categoria = self.session.get(Categoria, categoria_id)
        if categoria is None or categoria.deleted_em is not None:
            raise RegraViolada(f"Categoria {categoria_id} não existe.")
        if categoria.categoria_pai_id is not None:
            raise RegraViolada(
                f"Orçamento é por categoria raiz — '{categoria.nome}' é subcategoria de outra."
            )
