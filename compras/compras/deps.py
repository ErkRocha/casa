"""Dependências dos routers: sessão, "quem" (`X-Quem`) e as peças da nota fiscal."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from compras.config import get_settings
from compras.db import definir_autor, get_session
from compras.financas import Financas, FinancasHttp
from compras.nfce.consulta import ConsultaPublica, ConsultaSefazRs
from compras.nfce.leitor import LeitorNota
from compras.nfce.leitor_svrs import LeitorSvrsHtml

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


# --- Nota fiscal: as peças que falam com fora, trocáveis nos testes -----------


def consulta_publica() -> ConsultaPublica:
    """A consulta da SEFAZ-RS. Os testes trocam por uma falsa
    (`app.dependency_overrides`): nenhum teste fala com a SEFAZ."""
    return ConsultaSefazRs(get_settings().sefaz_tempo_limite_s)


def leitor_nota() -> LeitorNota:
    return LeitorSvrsHtml()


def financas() -> Financas:
    return FinancasHttp(get_settings().financas_url)


ConsultaDep = Annotated[ConsultaPublica, Depends(consulta_publica)]
LeitorDep = Annotated[LeitorNota, Depends(leitor_nota)]
FinancasDep = Annotated[Financas, Depends(financas)]
