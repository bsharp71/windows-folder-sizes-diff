from pathlib import Path

import pytest
from sqlalchemy import select

from windows_folder_sizes_diff.db.lifecycle import (
    InvalidScanStatusTransition,
    ScanLifecycleService,
    ScanStatus,
)
from windows_folder_sizes_diff.db.models import Scan, VolumeObservation
from windows_folder_sizes_diff.scanner.events import ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest


def request(tmp_path: Path) -> ScanRequest:
    return ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)


def completion(tmp_path: Path, *, cancelled: bool = False, warnings: int = 0) -> ScanCompleted:
    from windows_folder_sizes_diff.db.time import utc_now

    now = utc_now()
    return ScanCompleted(
        started_at=now,
        completed_at=now,
        cancelled=cancelled,
        folders_scanned=1,
        folders_matched=0,
        warning_count=warnings,
        results=[],
    )


def test_scan_lifecycle_status_transitions(migrated_session_factory, tmp_path: Path) -> None:
    service = ScanLifecycleService(migrated_session_factory)
    scan_record = service.create_scan(request(tmp_path))

    service.mark_running(scan_record.id)
    service.mark_completed(scan_record.id, completion(tmp_path), files_examined=2)

    with migrated_session_factory() as session:
        scan = session.get(Scan, scan_record.id)
        volume = session.scalar(
            select(VolumeObservation).where(VolumeObservation.scan_id == scan_record.id)
        )

    assert scan.status == ScanStatus.COMPLETED.value
    assert scan.completed_at is not None
    assert scan.files_examined == 2
    assert volume.status == "complete"
    assert volume.free_bytes_before is not None
    assert volume.free_bytes_after is not None


def test_completed_with_warnings_and_cancelled_statuses(
    migrated_session_factory, tmp_path: Path
) -> None:
    service = ScanLifecycleService(migrated_session_factory)
    warned = service.create_scan(request(tmp_path))
    cancelled = service.create_scan(request(tmp_path))

    service.mark_running(warned.id)
    service.mark_completed(warned.id, completion(tmp_path, warnings=1), files_examined=0)
    service.mark_running(cancelled.id)
    service.mark_cancelled(
        cancelled.id,
        completion(tmp_path, cancelled=True),
        files_examined=0,
    )

    with migrated_session_factory() as session:
        warned_scan = session.get(Scan, warned.id)
        cancelled_scan = session.get(Scan, cancelled.id)

    assert warned_scan.status == ScanStatus.COMPLETED_WITH_WARNINGS.value
    assert cancelled_scan.status == ScanStatus.CANCELLED.value
    assert cancelled_scan.cancel_requested is True


def test_invalid_status_transition_is_rejected(migrated_session_factory, tmp_path: Path) -> None:
    service = ScanLifecycleService(migrated_session_factory)
    scan_record = service.create_scan(request(tmp_path))
    service.mark_running(scan_record.id)
    service.mark_completed(scan_record.id, completion(tmp_path), files_examined=0)

    with pytest.raises(InvalidScanStatusTransition):
        service.mark_running(scan_record.id)


def test_recover_stale_scans_marks_interrupted(migrated_session_factory, tmp_path: Path) -> None:
    service = ScanLifecycleService(migrated_session_factory)
    scan_record = service.create_scan(request(tmp_path))
    service.mark_running(scan_record.id)

    assert service.recover_stale_scans() == 1

    with migrated_session_factory() as session:
        scan = session.get(Scan, scan_record.id)

    assert scan.status == ScanStatus.INTERRUPTED.value
    assert scan.completed_at is not None
