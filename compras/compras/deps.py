"""Dependências dos routers: sessão, "quem" (`X-Quem`) e as peças da nota fiscal."""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from compras.config import get_settings
from compras.db import definir_autor, get_session
from compras.financas import Financas, FinancasHttp
from compras.nfce.consulta import ConsultaPublica, ConsultaSefazRs
from compras.nfce.leitor import LeitorNota
from compras.nfce.leitor_svrs import LeitorSvrsHtml
from compras.services.identidades import IdentidadeService, nome_do_tailscale, normalizar_login

SessionDep = Annotated[Session, Depends(get_session)]

#: Tamanho máximo do nome em `X-Quem`.
QUEM_MAX = 60


@dataclass(frozen=True, slots=True)
class Identidade:
    """Quem pede, e de onde veio a informação."""

    #: O nome que vai para "adicionou", "pegou" e a auditoria; nulo sem nada.
    quem: str | None
    #: "tailscale" (posto pelo `tailscale serve`) ou "aparelho" (o `X-Quem`).
    origem: Literal["tailscale", "aparelho"] | None
    login: str | None = None
    #: O login tem nome cadastrado em `identidades_tailscale`?
    cadastrado: bool = False


def identidade(
    session: SessionDep,
    x_quem: Annotated[
        str | None,
        Header(
            alias="X-Quem",
            description=(
                "Quem está usando o aparelho, guardado nele. Ignorado quando a "
                "requisição chega pelo Tailscale com identidade."
            ),
        ),
    ] = None,
    tailscale_login: Annotated[
        str | None,
        Header(
            alias="Tailscale-User-Login",
            description="Posto pelo `tailscale serve`, que apaga o que o cliente mandar.",
        ),
    ] = None,
    tailscale_nome: Annotated[str | None, Header(alias="Tailscale-User-Name")] = None,
) -> Identidade:
    """A identidade do Tailscale vence o `X-Quem` (roadmap, Lista de compras, 3)."""
    login = (tailscale_login or "").strip()
    if login:
        cadastrada = IdentidadeService(session).por_login(login)
        nome = (
            (cadastrada.nome if cadastrada else None) or nome_do_tailscale(tailscale_nome) or login
        )
        return Identidade(
            quem=nome[:QUEM_MAX],
            origem="tailscale",
            login=normalizar_login(login),
            cadastrado=cadastrada is not None,
        )
    valor = (x_quem or "").strip()
    return Identidade(quem=valor or None, origem="aparelho" if valor else None)


IdentidadeDep = Annotated[Identidade, Depends(identidade)]


def quem(session: SessionDep, ident: IdentidadeDep) -> str:
    """Toda escrita exige alguém (api.md). Ele vira o autor da auditoria."""
    if not ident.quem:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Informe quem está usando no cabeçalho X-Quem.",
        )
    if len(ident.quem) > QUEM_MAX:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"X-Quem passa de {QUEM_MAX} caracteres.")
    definir_autor(session, ident.quem)
    return ident.quem


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
