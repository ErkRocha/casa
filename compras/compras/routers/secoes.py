"""Seções do mercado, na ordem do percurso."""

from typing import Any

from fastapi import APIRouter, status

from compras.deps import FinancasDep, QuemDep, SessionDep
from compras.schemas import SecaoAtualizar, SecaoCriar, SecaoLeitura, SecoesOrdem
from compras.services.secoes import SecaoService

router = APIRouter(prefix="/secoes", tags=["seções"])


@router.get("", response_model=list[SecaoLeitura])
def listar(session: SessionDep) -> Any:
    """Todas, na ordem do percurso."""
    return [SecaoLeitura.de(s) for s in SecaoService(session).listar()]


@router.post("", response_model=SecaoLeitura, status_code=status.HTTP_201_CREATED)
def criar(payload: SecaoCriar, session: SessionDep, _quem: QuemDep) -> Any:
    """Entra no fim do percurso, antes de "Sem seção"."""
    secao = SecaoService(session).criar(payload.nome)
    session.commit()
    return SecaoLeitura.de(secao)


@router.put("/ordem", response_model=list[SecaoLeitura])
def reordenar(payload: SecoesOrdem, session: SessionDep, _quem: QuemDep) -> Any:
    """Recebe todos os ids na ordem nova; reordena numa transação."""
    secoes = SecaoService(session).reordenar(payload.ids)
    session.commit()
    return [SecaoLeitura.de(s) for s in secoes]


@router.patch("/{id_}", response_model=SecaoLeitura)
def atualizar(
    id_: int,
    payload: SecaoAtualizar,
    session: SessionDep,
    _quem: QuemDep,
    financas: FinancasDep,
) -> Any:
    """Renomeia e/ou define a categoria de finanças sugerida para os itens da
    seção (D-33). Só o que veio muda; `categoria_id_financas: null` limpa. A
    categoria precisa ser de despesa em finanças (422 se não for)."""
    campos = payload.model_dump(exclude_unset=True)
    secao = SecaoService(session).atualizar(id_, campos, financas)
    session.commit()
    return SecaoLeitura.de(secao)


@router.delete("/{id_}", response_model=SecaoLeitura)
def remover(id_: int, session: SessionDep, _quem: QuemDep) -> Any:
    """Soft delete; os produtos dela vão para "Sem seção"."""
    secao = SecaoService(session).remover(id_)
    session.commit()
    return SecaoLeitura.de(secao)
