"""Engine, sessão e a base declarativa do schema `compras`.

Nunca há `create_all()`: o schema é das migrations do próprio serviço.
"""

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, MetaData, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from compras.config import SCHEMA, get_settings


def pg_enum(enum_cls: type, name: str) -> Enum:
    """Enum nativo do Postgres no schema `compras`, gravando o valor."""
    return Enum(
        enum_cls,
        name=name,
        schema=SCHEMA,
        native_enum=True,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)


class Comum:
    """Id, timestamps e soft delete de toda tabela editável.

    `atualizado_em` nasce no INSERT e o trigger o renova em todo UPDATE: é o
    relógio do `GET /mudancas` (modelo-dados.md, Convenções). Diferente de
    finanças, onde ele fica nulo até o primeiro UPDATE.
    """

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deleted_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def definir_autor(session: Session, autor: str) -> None:
    """Quem a auditoria registra nesta conexão (`app.autor`)."""
    session.execute(text("SELECT set_config('app.autor', :autor, false)"), {"autor": autor})


def get_session() -> Iterator[Session]:
    """Uma sessão por requisição, com o autor padrão até o `X-Quem` trocar."""
    with SessionLocal() as session:
        definir_autor(session, _settings.autor_padrao)
        yield session
