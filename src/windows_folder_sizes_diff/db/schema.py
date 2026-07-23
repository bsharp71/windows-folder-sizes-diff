"""Alembic schema verification helpers."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from windows_folder_sizes_diff.constants import PROJECT_ROOT
from windows_folder_sizes_diff.db.engine import database_url_from_path


class DatabaseSchemaError(RuntimeError):
    """Raised when the configured database has not been migrated."""


def make_alembic_config(database_path: Path | str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url_from_path(database_path))
    return config


def assert_schema_current(engine: Engine, database_path: Path | str) -> None:
    expected_head = ScriptDirectory.from_config(make_alembic_config(database_path)).get_current_head()
    with engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())
        if "alembic_version" not in table_names:
            raise DatabaseSchemaError(
                "Database schema is not initialized. Run: uv run alembic upgrade head"
            )
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision != expected_head:
        raise DatabaseSchemaError(
            "Database schema is not current. Run: uv run alembic upgrade head"
        )
