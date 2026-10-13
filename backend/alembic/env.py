"""Alembic environment for V-Base.

The connection string always comes from ``DATABASE_URL`` (through
``nexus.core.config.settings``); ``alembic.ini`` deliberately holds no
credentials. Both async (normal) and offline (SQL script) modes are supported.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Importing the models package registers every table on Base.metadata.
import nexus.database.models  # noqa: F401
from nexus.core.config import settings
from nexus.core.db import build_connect_args
from nexus.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure_url() -> None:
    """Inject the DSN plus the asyncpg connect args into the Alembic config."""
    url, connect_args = build_connect_args(settings.database_url)
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url
    # escape the % that ConfigParser would otherwise treat as interpolation
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["connect_args"] = connect_args


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting (``alembic upgrade head --sql``)."""
    _configure_url()
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include the search_vector GIN indexes and trigram operator classes in
        # autogenerate diffs; without this they are silently skipped.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    _configure_url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=config.attributes.get("connect_args", {}),
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
