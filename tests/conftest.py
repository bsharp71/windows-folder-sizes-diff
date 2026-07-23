from pathlib import Path

import pytest
from alembic import command

from windows_folder_sizes_diff.db.engine import create_database_engine, create_session_factory
from windows_folder_sizes_diff.db.schema import make_alembic_config


@pytest.fixture
def migrated_database_path(tmp_path: Path) -> Path:
    database_path = tmp_path / "folder_sizes.db"
    command.upgrade(make_alembic_config(database_path), "head")
    return database_path


@pytest.fixture
def migrated_session_factory(migrated_database_path: Path):
    engine = create_database_engine(migrated_database_path)
    return create_session_factory(engine)
