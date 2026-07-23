from pathlib import Path

from sqlalchemy import select

from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.models import DirectoryObservation, Scan, ScanWarningRecord
from windows_folder_sizes_diff.db.persistence import ScanPersistenceCoordinator
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import FolderObserved, ScanCompleted, ScanWarning
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest


def test_persistence_coordinator_batches_observations_and_warnings(
    migrated_session_factory, tmp_path: Path
) -> None:
    lifecycle = ScanLifecycleService(migrated_session_factory)
    record = lifecycle.create_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )
    lifecycle.mark_running(record.id)
    coordinator = ScanPersistenceCoordinator(
        scan_id=record.id,
        session_factory=migrated_session_factory,
        lifecycle_service=lifecycle,
        batch_size=2,
    )

    coordinator.handle_event(
        FolderObserved(
            scan_id=record.id,
            observation=FolderObservation(
                path=tmp_path,
                matching_bytes=0,
                direct_file_count=1,
                matched_file_count=0,
                scanned_at=utc_now(),
            ),
        )
    )
    coordinator.handle_event(
        FolderObserved(
            scan_id=record.id,
            observation=FolderObservation(
                path=tmp_path / "child",
                matching_bytes=10,
                direct_file_count=1,
                matched_file_count=1,
                scanned_at=utc_now(),
            ),
        )
    )
    coordinator.handle_event(
        ScanWarning(
            scan_id=record.id,
            path=tmp_path / "missing.txt",
            operation="stat_file",
            error_type="FileNotFoundError",
            message="gone",
        )
    )
    now = utc_now()
    coordinator.handle_event(
        ScanCompleted(
            scan_id=record.id,
            started_at=now,
            completed_at=now,
            cancelled=False,
            folders_scanned=2,
            folders_matched=1,
            warning_count=1,
            results=[],
        )
    )

    with migrated_session_factory() as session:
        scan = session.get(Scan, record.id)
        observations = list(session.scalars(select(DirectoryObservation)))
        warnings = list(session.scalars(select(ScanWarningRecord)))

    assert scan.status == "completed_with_warnings"
    assert scan.files_examined == 2
    assert len(observations) == 2
    assert len(warnings) == 1
    assert warnings[0].operation == "stat_file"


def test_cancelled_scan_retains_partial_observations(migrated_session_factory, tmp_path: Path) -> None:
    lifecycle = ScanLifecycleService(migrated_session_factory)
    record = lifecycle.create_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )
    lifecycle.mark_running(record.id)
    coordinator = ScanPersistenceCoordinator(
        scan_id=record.id,
        session_factory=migrated_session_factory,
        lifecycle_service=lifecycle,
        batch_size=10,
    )
    coordinator.handle_event(
        FolderObserved(
            scan_id=record.id,
            observation=FolderObservation(
                path=tmp_path,
                matching_bytes=0,
                direct_file_count=0,
                matched_file_count=0,
                scanned_at=utc_now(),
            ),
        )
    )
    now = utc_now()
    coordinator.handle_event(
        ScanCompleted(
            scan_id=record.id,
            started_at=now,
            completed_at=now,
            cancelled=True,
            folders_scanned=1,
            folders_matched=0,
            warning_count=0,
            results=[],
        )
    )

    with migrated_session_factory() as session:
        scan = session.get(Scan, record.id)
        observation_count = len(list(session.scalars(select(DirectoryObservation))))

    assert scan.status == "cancelled"
    assert scan.completed_at is not None
    assert observation_count == 1
