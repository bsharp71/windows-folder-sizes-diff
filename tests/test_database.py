from pathlib import Path

from alembic import command
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from windows_folder_sizes_diff.db.engine import create_database_engine, create_session_factory
from windows_folder_sizes_diff.db.schema import assert_schema_current, make_alembic_config


def test_engine_creates_database_and_sets_sqlite_pragmas(tmp_path: Path) -> None:
    database_path = tmp_path / "db" / "folder_sizes.db"
    engine = create_database_engine(database_path)

    with engine.connect() as connection:
        connection.execute(text("select 1"))
        foreign_keys = connection.exec_driver_sql("PRAGMA foreign_keys").scalar()
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar()
        busy_timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()

    assert database_path.exists()
    assert foreign_keys == 1
    assert journal_mode in {"wal", "delete"}
    assert busy_timeout == 5000


def test_sessions_can_open_and_close(tmp_path: Path) -> None:
    engine = create_database_engine(tmp_path / "folder_sizes.db")
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        assert session.execute(text("select 1")).scalar() == 1


def test_fresh_database_upgrades_to_head_and_has_expected_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "folder_sizes.db"
    config = make_alembic_config(database_path)

    command.upgrade(config, "head")
    command.upgrade(config, "head")

    engine = create_database_engine(database_path)
    with engine.connect() as connection:
        tables = set(inspect(connection).get_table_names())
        indexes = {
            index["name"]
            for index in inspect(connection).get_indexes("directory_observations")
        }
        current = MigrationContext.configure(connection).get_current_revision()

    assert {
        "scans",
        "directories",
        "directory_observations",
        "scan_warnings",
        "volume_observations",
        "alembic_version",
    }.issubset(tables)
    assert "ix_directory_observations_scan_directory" in indexes
    assert current == "0001_phase_1"
    assert_schema_current(engine, database_path)
