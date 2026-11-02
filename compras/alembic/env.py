"""Alembic do serviço `compras`: tabela de versão no schema `compras` (D-25).

A tabela de versão de finanças fica em `public.alembic_version`; esta em
`compras.alembic_version`. Os dois históricos de migration não se cruzam.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Importado pelo efeito colateral de registrar os models no metadata.
from compras import models  # noqa: F401
from compras.config import SCHEMA, get_settings, url_para_alembic
from compras.db import Base

config = context.config
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", url_para_alembic(get_settings().database_url))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_name(name, type_, parent_names) -> bool:  # type: ignore[no-untyped-def]
    """O autogenerate só olha o schema `compras`, nunca o de finanças."""
    if type_ == "schema":
        return name == SCHEMA
    return True


def _opcoes() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "version_table_schema": SCHEMA,
        "include_schemas": True,
        "include_name": include_name,
        "compare_type": True,
    }


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_opcoes(),  # type: ignore[arg-type]
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
        context.configure(connection=connection, **_opcoes())  # type: ignore[arg-type]
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
