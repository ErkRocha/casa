from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importado pelo efeito colateral de registrar os models no metadata.
from app import models  # noqa: F401
from app.config import get_settings, url_para_alembic
from app.db import Base

config = context.config
config.set_main_option("sqlalchemy.url", url_para_alembic(get_settings().database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

#: Views são criadas por SQL na migration e não vivem no metadata. Sem esta
#: lista o autogenerate tenta dropar tudo que não conhece.
VIEWS = frozenset({"vw_transacoes_completa", "vw_gasto_por_pessoa", "vw_orcamento_mes"})


def include_object(obj, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """Mantém as views fora do autogenerate.

    Elas são criadas por SQL na migration; sem isso o Alembic tenta dropar
    tudo que não conhece.
    """
    return not (type_ == "table" and name in VIEWS)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
