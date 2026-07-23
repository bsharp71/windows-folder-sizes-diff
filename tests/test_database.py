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
    assert current == "0003_phase_3"
    assert_schema_current(engine, database_path)


def test_phase2_rows_upgrade_with_unavailable_hierarchy(tmp_path: Path) -> None:
    database_path = tmp_path / "folder_sizes.db"
    config = make_alembic_config(database_path)
    command.upgrade(config, "0002_phase_2")

    engine = create_database_engine(database_path)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO scans (
                    id, scan_uuid, target_path, normalized_target_path,
                    started_at, completed_at, status, history_days,
                    growth_threshold_mb, configuration_hash, folders_discovered,
                    folders_analyzed, folders_matched, files_examined,
                    warning_count, cancel_requested, failure_message,
                    measurement_algorithm_version, baseline_scan_id,
                    comparison_status, comparison_failure_message,
                    created_at, updated_at
                )
                VALUES (
                    1, '00000000-0000-0000-0000-000000000001',
                    'C:\\Root', 'c:\\root',
                    '2026-07-23 10:00:00', '2026-07-23 10:01:00',
                    'completed', 1, 0, 'hash',
                    1, 1, 0, 1, 0, 0, NULL,
                    2, NULL, 'baseline_created', NULL,
                    '2026-07-23 10:00:00', '2026-07-23 10:01:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO directories (
                    id, normalized_path, display_path, parent_normalized_path,
                    first_seen_scan_id, last_seen_scan_id, created_at, updated_at
                )
                VALUES (
                    1, 'c:\\root', 'C:\\Root', NULL,
                    1, 1, '2026-07-23 10:00:00', '2026-07-23 10:01:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO directory_observations (
                    id, scan_id, directory_id, matching_bytes, direct_file_count,
                    matched_file_count, observed_at, status, warning_count,
                    direct_logical_bytes, measurement_status, files_examined
                )
                VALUES (
                    1, 1, 1, 0, 1, 0,
                    '2026-07-23 10:01:00', 'observed', 0,
                    123, 'complete', 1
                )
                """
            )
        )

    command.upgrade(config, "head")

    with engine.connect() as connection:
        scan = connection.execute(
            text(
                "SELECT direct_measurement_status, hierarchy_aggregation_status "
                "FROM scans WHERE id = 1"
            )
        ).one()
        observation = connection.execute(
            text(
                "SELECT direct_logical_bytes, inclusive_logical_bytes, hierarchy_status "
                "FROM directory_observations WHERE id = 1"
            )
        ).one()

    assert scan.direct_measurement_status == "completed"
    assert scan.hierarchy_aggregation_status == "unavailable"
    assert observation.direct_logical_bytes == 123
    assert observation.inclusive_logical_bytes is None
    assert observation.hierarchy_status == "unavailable"
