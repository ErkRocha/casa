"""Dependências dos routers: sessão e "quem" (`X-Quem`)."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from compras.db import definir_autor, get_session

SessionDep = Annotated[Session, Depends(get_session)]

#: Tamanho máximo do nome em `X-Quem`.
QUEM_MAX = 60


def quem(
    session: SessionDep,
    x_quem: Annotated[
        str | None,
        Header(
            alias="X-Quem",
            description=(
                "Quem está usando o aparelho. Hoje o nome que ele guardou; na fase "
                "compartilhada, a identidade do Tailscale posta pelo proxy (D-25)."
            ),
        ),
    ] = None,
) -> str:
    """Toda escrita exige `X-Quem` (api.md). Ele vira o autor da auditoria."""
    valor = (x_quem or "").strip()
    if not valor:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Informe quem está usando no cabeçalho X-Quem.",
        )
    if len(valor) > QUEM_MAX:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"X-Quem passa de {QUEM_MAX} caracteres.")
    definir_autor(session, valor)
    return valor


QuemDep = Annotated[str, Depends(quem)]
