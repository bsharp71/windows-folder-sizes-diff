from __future__ import annotations

import os
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from windows_folder_sizes_diff.db.base import Base
from windows_folder_sizes_diff.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return os.environ.get(
        "FOLDER_DIFF_DATABASE_URL",
        config.get_main_option("sqlalchemy.url"),
    )


def _ensure_sqlite_parent_directory(url: str) -> None:
    parsed = make_url(url)
    if parsed.drivername != "sqlite" or parsed.database in {None, "", ":memory:"}:
        return
    Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


def run_migrations_offline() -> None:
    url = _database_url()
    _ensure_sqlite_parent_directory(url)
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    _ensure_sqlite_parent_directory(configuration["sqlalchemy.url"])
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
