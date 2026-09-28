"""Engine, sessão e a base declarativa.

Nunca há `create_all()` fora de teste: o schema é do Alembic (regra 4).
"""

from collections.abc import Iterator
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, MetaData, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.config import get_settings


def pg_enum(enum_cls: type, name: str) -> Enum:
    """Enum nativo do Postgres, gravando o *valor* e não o nome do membro.

    Usado tanto pelos models quanto pela declaração Core das views. As duas
    pontas precisam do mesmo tipo: comparar uma coluna `tipo_transacao` com
    um `varchar` não tem operador no Postgres e estoura em runtime.

    ``create_type=False``: quem cria o tipo é a migration.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        create_type=False,
        values_callable=lambda e: [m.value for m in e],
    )


#: Convenção de nomes para o autogenerate do Alembic gerar constraint com
#: nome estável, em vez de deixar o Postgres inventar.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """`criado_em` / `atualizado_em` de toda tabela.

    `atualizado_em` é preenchido por trigger, não por aplicação — agentes
    escrevem por caminhos diferentes e nem todos passam pelo ORM (D-06).
    """

    criado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    atualizado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SoftDeleteMixin:
    """Remoção é sempre `deleted_em = now()` (regra 2)."""

    deleted_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


_settings = get_settings()

engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI: uma sessão por request.

    Fixa `app.autor` na sessão do Postgres — é de lá que o trigger de
    auditoria tira quem fez a escrita.
    """
    with SessionLocal() as session:
        session.execute(
            text("SELECT set_config('app.autor', :autor, false)"),
            {"autor": _settings.app_autor_padrao},
        )
        yield session
