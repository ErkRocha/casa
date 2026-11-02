"""Quem é quem: `GET /eu` e o cadastro dos logins do Tailscale."""

from typing import Any

from fastapi import APIRouter, status

from compras.deps import IdentidadeDep, QuemDep, SessionDep
from compras.schemas import Eu, IdentidadeAtualizar, IdentidadeCriar, IdentidadeLeitura
from compras.services.identidades import IdentidadeService

router = APIRouter(tags=["identidade"])


@router.get("/eu", response_model=Eu)
def eu(ident: IdentidadeDep) -> Any:
    """Quem o serviço vê. Pelo Tailscale (`origem = tailscale`), o nome vem da
    tailnet e o aparelho não pergunta nada; sem ele, o aparelho pergunta
    "quem é você?" uma vez e manda no `X-Quem`."""
    return Eu(quem=ident.quem, origem=ident.origem, login=ident.login, cadastrado=ident.cadastrado)


@router.get("/identidades", response_model=list[IdentidadeLeitura])
def listar(session: SessionDep) -> Any:
    return [IdentidadeLeitura.de(i) for i in IdentidadeService(session).listar()]


@router.post("/identidades", response_model=IdentidadeLeitura, status_code=status.HTTP_201_CREATED)
def criar(payload: IdentidadeCriar, session: SessionDep, _quem: QuemDep) -> Any:
    """Liga um login da tailnet ao nome exibido ("erik@exemplo.com" -> "Erik").
    Login já cadastrado: 409."""
    linha = IdentidadeService(session).criar(payload.login, payload.nome)
    session.commit()
    return IdentidadeLeitura.de(linha)


@router.patch("/identidades/{id_}", response_model=IdentidadeLeitura)
def atualizar(id_: int, payload: IdentidadeAtualizar, session: SessionDep, _quem: QuemDep) -> Any:
    linha = IdentidadeService(session).atualizar(id_, payload.model_dump())
    session.commit()
    session.refresh(linha)
    return IdentidadeLeitura.de(linha)


@router.delete("/identidades/{id_}", response_model=IdentidadeLeitura)
def remover(id_: int, session: SessionDep, _quem: QuemDep) -> Any:
    """Soft delete: o login volta a aparecer com o nome que o Tailscale manda."""
    linha = IdentidadeService(session).remover(id_)
    session.commit()
    return IdentidadeLeitura.de(linha)
