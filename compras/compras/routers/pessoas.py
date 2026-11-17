"""Pessoas do cardápio (D-30)."""

from typing import Any

from fastapi import APIRouter, status

from compras.deps import QuemDep, SessionDep
from compras.schemas_cardapio import PessoaAtualizar, PessoaCriar, PessoaLeitura
from compras.services.pessoas import PessoaService, leitura

router = APIRouter(prefix="/pessoas", tags=["cardápio: pessoas"])


@router.get("", response_model=list[PessoaLeitura])
def listar(session: SessionDep) -> Any:
    """As vivas, com a porção padrão e o login ligado (quando há)."""
    return [leitura(p) for p in PessoaService(session).listar()]


@router.post("", response_model=PessoaLeitura, status_code=status.HTTP_201_CREATED)
def criar(payload: PessoaCriar, session: SessionDep, quem: QuemDep) -> Any:
    """Nome repetido ou login já ligado a outra pessoa: 409."""
    pessoa = PessoaService(session, quem).criar(
        payload.nome, payload.porcao_padrao, payload.identidade_id
    )
    session.commit()
    return leitura(pessoa)


@router.patch("/{id_}", response_model=PessoaLeitura)
def atualizar(id_: int, payload: PessoaAtualizar, session: SessionDep, quem: QuemDep) -> Any:
    pessoa = PessoaService(session, quem).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return leitura(pessoa)


@router.delete("/{id_}", response_model=PessoaLeitura)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Soft delete. Some das refeições de hoje em diante; as passadas mantêm a linha."""
    pessoa = PessoaService(session, quem).remover(id_)
    session.commit()
    return leitura(pessoa)
