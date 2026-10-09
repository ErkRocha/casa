"""CRUD genérico com soft delete.

Router valida entrada e chama service; regra de negócio não mora em router
nem em model (regra 12).
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base
from app.schemas.common import Paginacao

ModelT = TypeVar("ModelT", bound=Base)


class ErroDominio(Exception):
    """Base dos erros que o router traduz em HTTP."""


class NaoEncontrado(ErroDominio):
    def __init__(self, recurso: str, id_: int) -> None:
        super().__init__(f"{recurso} {id_} não encontrado")
        self.recurso = recurso
        self.id = id_


class Conflito(ErroDominio):
    """Violação de unique, FK ou check — o banco disse não."""


class RegraViolada(ErroDominio):
    """Regra de negócio que o service checa antes de tocar no banco."""


class CrudService(Generic[ModelT]):
    """Operações comuns a todo cadastro.

    Nenhum método faz DELETE físico: remoção é `deleted_em = now()` e toda
    leitura filtra `deleted_em IS NULL` (regra 2).
    """

    model: type[ModelT]
    nome_recurso: str

    def __init__(self, session: Session) -> None:
        self.session = session

    # -- leitura ---------------------------------------------------------

    def _base_query(self) -> Any:
        return select(self.model).where(self.model.deleted_em.is_(None))  # type: ignore[attr-defined]

    def get(self, id_: int) -> ModelT:
        obj = self.session.scalar(self._base_query().where(self.model.id == id_))  # type: ignore[attr-defined]
        if obj is None:
            raise NaoEncontrado(self.nome_recurso, id_)
        return obj  # type: ignore[no-any-return]

    def listar(self, paginacao: Paginacao, apenas_ativos: bool = False) -> tuple[list[ModelT], int]:
        query = self._base_query()
        if apenas_ativos and hasattr(self.model, "ativo"):
            query = query.where(self.model.ativo.is_(True))  # type: ignore[attr-defined]

        total = self.session.scalar(select(func.count()).select_from(query.subquery()))
        itens = list(
            self.session.scalars(
                query.order_by(self.model.id).limit(paginacao.limit).offset(paginacao.offset)  # type: ignore[attr-defined]
            )
        )
        return itens, int(total or 0)

    # -- escrita ---------------------------------------------------------

    def criar(self, dados: dict[str, Any]) -> ModelT:
        obj = self.model(**dados)
        self.session.add(obj)
        self._flush()
        return obj

    def atualizar(self, id_: int, dados: dict[str, Any]) -> ModelT:
        obj = self.get(id_)
        for campo, valor in dados.items():
            setattr(obj, campo, valor)
        self._flush()
        return obj

    def remover(self, id_: int) -> None:
        """Soft delete. Idempotente: remover duas vezes não dá erro."""
        obj = self.get(id_)
        obj.deleted_em = func.now()  # type: ignore[attr-defined]
        self._flush()

    def _flush(self) -> None:
        """Empurra para o banco agora, para o erro sair no lugar certo."""
        try:
            self.session.flush()
        except IntegrityError as exc:
            self.session.rollback()
            raise Conflito(_mensagem_integridade(exc)) from exc


def _mensagem_integridade(exc: IntegrityError) -> str:
    """Traduz o erro do Postgres para algo que o usuário entenda."""
    detalhe = str((getattr(exc.orig, "diag", None) and exc.orig.diag.message_detail) or exc.orig)  # type: ignore[union-attr]
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)

    conhecidas = {
        "uq_transacoes_dedup": (
            "Já existe uma transação idêntica (mesma data, valor, descrição "
            "original, forma de pagamento e parcela)."
        ),
        "uq_orcamentos_categoria_competencia": (
            "Já existe orçamento para esta categoria nesta competência."
        ),
        "uq_categorias_raiz_nome": "Já existe uma categoria com este nome.",
        "uq_categorias_pai_nome": "Já existe uma subcategoria com este nome neste pai.",
        "ck_transacoes_valor_positivo": "O valor tem que ser positivo.",
        "ck_transacoes_transferencia_coerente": (
            "Transferência exige conta de origem e destino diferentes, e não tem categoria."
        ),
        "ck_transacoes_competencia_e_dia_primeiro": (
            "A competência tem que ser o primeiro dia do mês."
        ),
        "uq_contas_pluggy_pluggy_account_id": (
            "Esta conta da Pluggy já está mapeada. Edite o mapeamento existente "
            "ou desative-o antes de criar outro."
        ),
        "uq_categorias_pluggy_pluggy_categoria_id": (
            "Esta categoria da Pluggy já está mapeada. Edite o mapeamento existente "
            "ou desative-o antes de criar outro."
        ),
    }
    if constraint in conhecidas:
        return conhecidas[constraint]
    return f"Operação recusada pelo banco: {detalhe}"
