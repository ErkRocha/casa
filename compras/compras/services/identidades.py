"""Identidade pelo Tailscale (roadmap, Lista de compras, 3).

O `tailscale serve` põe em cada requisição da tailnet o login e o nome de
quem pede (`Tailscale-User-Login`, `Tailscale-User-Name`) e apaga esses
cabeçalhos se vierem do cliente. O proxy (nginx ou Vite) repassa os dois e
põe o login no `X-Quem`. Aqui o login vira o nome exibido: o cadastrado em
`identidades_tailscale`, senão o nome que o Tailscale mandou, senão o login.
"""

from __future__ import annotations

from email.header import decode_header, make_header
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from compras.models import IdentidadeTailscale
from compras.services.base import Conflito, NaoEncontrado


def nome_do_tailscale(bruto: str | None) -> str | None:
    """O `Tailscale-User-Name` legível: nome com acento vem em RFC 2047
    ("=?utf-8?q?Ferris_B=C3=BCller?=")."""
    if not bruto or not bruto.strip():
        return None
    try:
        return str(make_header(decode_header(bruto))).strip() or None
    except (ValueError, LookupError, UnicodeDecodeError):
        return bruto.strip()


def normalizar_login(login: str) -> str:
    return login.strip().lower()


class IdentidadeService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def por_login(self, login: str) -> IdentidadeTailscale | None:
        return self.session.scalar(
            select(IdentidadeTailscale).where(
                IdentidadeTailscale.login == normalizar_login(login),
                IdentidadeTailscale.deleted_em.is_(None),
            )
        )

    def listar(self) -> list[IdentidadeTailscale]:
        return list(
            self.session.scalars(
                select(IdentidadeTailscale)
                .where(IdentidadeTailscale.deleted_em.is_(None))
                .order_by(IdentidadeTailscale.nome)
            )
        )

    def get(self, id_: int) -> IdentidadeTailscale:
        linha = self.session.scalar(
            select(IdentidadeTailscale).where(
                IdentidadeTailscale.id == id_, IdentidadeTailscale.deleted_em.is_(None)
            )
        )
        if linha is None:
            raise NaoEncontrado("identidade", id_)
        return linha

    def criar(self, login: str, nome: str) -> IdentidadeTailscale:
        linha = IdentidadeTailscale(login=normalizar_login(login), nome=nome.strip())
        try:
            with self.session.begin_nested():
                self.session.add(linha)
                self.session.flush()
        except IntegrityError as exc:
            raise Conflito(f"O login {linha.login} já está cadastrado.") from exc
        return linha

    def atualizar(self, id_: int, campos: dict[str, Any]) -> IdentidadeTailscale:
        linha = self.get(id_)
        if "nome" in campos and campos["nome"] is not None:
            linha.nome = str(campos["nome"]).strip()
        self.session.flush()
        return linha

    def remover(self, id_: int) -> IdentidadeTailscale:
        from sqlalchemy import func

        linha = self.get(id_)
        linha.deleted_em = func.now()
        self.session.flush()
        self.session.refresh(linha)
        return linha
