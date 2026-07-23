from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from windows_folder_sizes_diff.db.models import Directory, DirectoryObservation, Scan
from windows_folder_sizes_diff.db.repositories import DirectoryRepository, ObservationRepository
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest


def create_running_scan(session_factory, tmp_path: Path) -> int:
    service = ScanLifecycleService(session_factory)
    scan = service.create_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )
    service.mark_running(scan.id)
    return scan.id


def test_directory_identity_reuses_normalized_paths(migrated_session_factory, tmp_path: Path) -> None:
    scan_id = create_running_scan(migrated_session_factory, tmp_path)
    repo = DirectoryRepository()
    mixed_case = Path(str(tmp_path).upper())

    with migrated_session_factory() as session:
        first = repo.ensure_many(session, [tmp_path], scan_id=scan_id)
        second = repo.ensure_many(session, [mixed_case, Path(str(tmp_path) + "\\")], scan_id=scan_id)
        session.commit()
        directories = list(session.scalars(select(Directory)))

    assert len(directories) == 1
    assert set(first.values()) == set(second.values())
    assert directories[0].display_path == str(tmp_path)


def test_observations_store_below_and_above_threshold_rows(
    migrated_session_factory, tmp_path: Path
) -> None:
    scan_id = create_running_scan(migrated_session_factory, tmp_path)
    directory_repo = DirectoryRepository()
    observation_repo = ObservationRepository()
    observations = [
        FolderObservation(
            path=tmp_path,
            matching_bytes=0,
            direct_file_count=1,
            matched_file_count=0,
            scanned_at=utc_now(),
            status="observed",
        ),
        FolderObservation(
            path=tmp_path / "child",
            matching_bytes=2_000_000,
            direct_file_count=2,
            matched_file_count=1,
            scanned_at=utc_now(),
            status="observed",
        ),
    ]

    with migrated_session_factory() as session:
        directory_ids = directory_repo.ensure_many(
            session,
            [observation.path for observation in observations],
            scan_id=scan_id,
        )
        observation_repo.insert_many(
            session,
            observations,
            scan_id=scan_id,
            directory_ids=directory_ids,
        )
        session.commit()

    with migrated_session_factory() as session:
        rows = list(session.scalars(select(DirectoryObservation)))

    assert [row.matching_bytes for row in rows] == [0, 2_000_000]


def test_duplicate_observation_for_scan_and_directory_is_rejected(
    migrated_session_factory, tmp_path: Path
) -> None:
    scan_id = create_running_scan(migrated_session_factory, tmp_path)
    directory_repo = DirectoryRepository()
    observation_repo = ObservationRepository()
    observation = FolderObservation(
        path=tmp_path,
        matching_bytes=0,
        direct_file_count=0,
        matched_file_count=0,
        scanned_at=utc_now(),
        status="observed",
    )

    with migrated_session_factory() as session:
        directory_ids = directory_repo.ensure_many(session, [tmp_path], scan_id=scan_id)
        observation_repo.insert_many(
            session,
            [observation],
            scan_id=scan_id,
            directory_ids=directory_ids,
        )
        with pytest.raises(IntegrityError):
            observation_repo.insert_many(
                session,
                [observation],
                scan_id=scan_id,
                directory_ids=directory_ids,
            )
