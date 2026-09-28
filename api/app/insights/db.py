"""Sessão read-only do agente de insights (D-11).

Engine separada da do app de propósito. Reusar `app.db.SessionLocal` seria
mais curto e desfaria a garantia: a role do painel escreve, e o dia em que uma
tool de insights chamasse `session.add()` por engano ninguém perceberia — a
escrita simplesmente funcionaria.

Aqui a permissão vem antes do código. Se uma tool tentar escrever, o Postgres
recusa com `42501`, e o erro aparece no teste, não em produção.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_settings = get_settings()

#: `postgresql_readonly` põe a própria transação em READ ONLY. É redundante
#: com a permissão da role — e é assim que se quer: as duas travas falham por
#: motivos diferentes, então uma configuração errada não derruba as duas.
engine_insights = create_engine(
    _settings.insights_database_url,
    pool_pre_ping=True,
    execution_options={"postgresql_readonly": True},
)

SessionInsights = sessionmaker(bind=engine_insights, autoflush=False, expire_on_commit=False)


@contextmanager
def sessao_leitura() -> Iterator[Session]:
    """Uma sessão read-only, sempre encerrada com rollback.

    Nunca `commit()`: não há nada para confirmar, e o rollback explícito
    deixa claro no código que esta sessão não é caminho de escrita.
    """
    sessao = SessionInsights()
    try:
        yield sessao
    finally:
        sessao.rollback()
        sessao.close()
