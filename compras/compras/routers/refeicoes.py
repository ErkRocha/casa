"""Refeições e sessões de preparo, pelo id (D-30)."""

from typing import Any

from fastapi import APIRouter

from compras.deps import QuemDep, SessionDep
from compras.schemas_cardapio import (
    PessoaPorcao,
    RefeicaoAtualizar,
    RefeicaoLeitura,
    SessaoAtualizar,
    SessaoLeitura,
)
from compras.services.preparo import SessaoService
from compras.services.refeicoes import RefeicaoService

router = APIRouter(tags=["cardápio: refeições"])


@router.patch("/refeicoes/{id_}", response_model=RefeicaoLeitura)
def atualizar(id_: int, payload: RefeicaoAtualizar, session: SessionDep, quem: QuemDep) -> Any:
    """Dia (dentro da semana), tipo, receita, observação, ordem."""
    servico = RefeicaoService(session, quem)
    refeicao = servico.atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return servico.leitura(refeicao)


@router.put("/refeicoes/{id_}/pessoas", response_model=RefeicaoLeitura)
def definir_pessoas(
    id_: int, payload: list[PessoaPorcao], session: SessionDep, quem: QuemDep
) -> Any:
    """Quem come e quanto. `porcoes` nulo volta ao padrão do perfil."""
    servico = RefeicaoService(session, quem)
    refeicao = servico.definir_pessoas(id_, payload)
    session.commit()
    return servico.leitura(refeicao)


@router.delete("/refeicoes/{id_}", response_model=RefeicaoLeitura)
def remover(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    servico = RefeicaoService(session, quem)
    refeicao = servico.remover(id_)
    session.commit()
    return servico.leitura(refeicao)


@router.patch("/sessoes/{id_}", response_model=SessaoLeitura)
def atualizar_sessao(id_: int, payload: SessaoAtualizar, session: SessionDep, quem: QuemDep) -> Any:
    sessao = SessaoService(session, quem).atualizar(id_, payload.model_dump(exclude_unset=True))
    session.commit()
    return SessaoLeitura.model_validate(sessao, from_attributes=True)


@router.delete("/sessoes/{id_}", response_model=SessaoLeitura)
def remover_sessao(id_: int, session: SessionDep, quem: QuemDep) -> Any:
    """Soft delete; as refeições dela vão para a sessão anterior ou para "no dia"."""
    sessao = SessaoService(session, quem).remover(id_)
    session.commit()
    return SessaoLeitura.model_validate(sessao, from_attributes=True)
