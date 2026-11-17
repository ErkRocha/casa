"""Refeições e sessões de preparo, pelo id (D-30)."""

import uuid
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from compras.deps import QuemDep, SessionDep
from compras.schemas import PassoFeitoLeitura
from compras.schemas_cardapio import (
    PessoaPorcao,
    RefeicaoAtualizar,
    RefeicaoLeitura,
    SessaoAtualizar,
    SessaoLeitura,
)
from compras.services.passos_feitos import PassoFeitoService
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


class MarcarFeito(BaseModel):
    id_cliente: uuid.UUID


@router.put(
    "/sessoes/{sessao_id}/passos/{receita_id}/feito",
    response_model=PassoFeitoLeitura,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"description": "Já estava feito (ou o mesmo `id_cliente`): o que existe"}},
)
def marcar_feito(
    sessao_id: int,
    receita_id: int,
    payload: MarcarFeito,
    response: Response,
    session: SessionDep,
    quem: QuemDep,
) -> Any:
    """Marca o passo do roteiro como feito, por quem pede e agora. Já feito: vale o primeiro."""
    passo, marcado = PassoFeitoService(session, quem).marcar(
        sessao_id, receita_id, payload.id_cliente
    )
    session.commit()
    if not marcado:
        response.status_code = status.HTTP_200_OK
    return PassoFeitoLeitura.de(passo)


@router.delete(
    "/sessoes/{sessao_id}/passos/{receita_id}/feito", response_model=PassoFeitoLeitura | None
)
def desfazer_feito(sessao_id: int, receita_id: int, session: SessionDep, quem: QuemDep) -> Any:
    """Desfaz (soft delete) e devolve a linha com `deleted_em`. Não estava feito: 200 e `null`."""
    passo = PassoFeitoService(session, quem).desfazer(sessao_id, receita_id)
    session.commit()
    return None if passo is None else PassoFeitoLeitura.de(passo)
