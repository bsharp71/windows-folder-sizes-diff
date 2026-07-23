import shutil
from pathlib import Path

from sqlalchemy import select, update

from windows_folder_sizes_diff.analysis.baseline import BaselineSelector
from windows_folder_sizes_diff.analysis.differ import ScanDiffer
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.models import DirectoryObservation, Scan
from windows_folder_sizes_diff.db.persistence import ScanPersistenceCoordinator
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import ScanCompleted
from windows_folder_sizes_diff.scanner.folder_scanner import FolderScanner
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest


def write_file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def run_persisted_scan(
    session_factory,
    target: Path,
    *,
    threshold_mb: int = 0,
    cancelled: bool = False,
) -> int:
    lifecycle = ScanLifecycleService(session_factory)
    request = ScanRequest(target_directory=target, growth_threshold_mb=threshold_mb, history_days=1)
    record = lifecycle.create_scan(request)
    lifecycle.mark_running(record.id)
    coordinator = ScanPersistenceCoordinator(
        scan_id=record.id,
        session_factory=session_factory,
        lifecycle_service=lifecycle,
        batch_size=10,
    )
    if cancelled:
        now = utc_now()
        coordinator.handle_event(
            ScanCompleted(
                scan_id=record.id,
                started_at=now,
                completed_at=now,
                cancelled=True,
                folders_scanned=0,
                folders_matched=0,
                warning_count=0,
                results=[],
            )
        )
        return record.id

    scanner = FolderScanner(request=request, event_sink=coordinator.handle_event, scan_id=record.id)
    scanner.start()
    scanner.wait(5)
    assert not scanner.is_running
    return record.id


def diff_by_path(session_factory, previous_id: int, current_id: int):
    with session_factory() as session:
        report = ScanDiffer().compare(session, previous_id, current_id)
    return {str(diff.path): diff for diff in report.results}, report


def test_scanner_stores_direct_logical_size_independent_of_timestamps(
    migrated_session_factory, tmp_path: Path
) -> None:
    target = tmp_path / "target"
    write_file(target / "file.bin", 100)
    scan_id = run_persisted_scan(migrated_session_factory, target)

    with migrated_session_factory() as session:
        observation = session.scalar(select(DirectoryObservation))
        scan = session.get(Scan, scan_id)

    assert observation.direct_logical_bytes == 100
    assert observation.measurement_status == "complete"
    assert observation.files_examined == 1
    assert scan.comparison_status == "baseline_created"


def test_same_size_rewrite_produces_zero_delta(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    file_path = target / "file.bin"
    write_file(file_path, 100)
    baseline_id = run_persisted_scan(migrated_session_factory, target)
    write_file(file_path, 100)
    current_id = run_persisted_scan(migrated_session_factory, target)

    diffs, report = diff_by_path(migrated_session_factory, baseline_id, current_id)

    assert diffs[str(target)].direct_delta_bytes == 0
    assert diffs[str(target)].state == "unchanged"
    assert report.summary.net_change_bytes == 0


def test_file_growth_shrink_and_delete_deltas(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    file_path = target / "file.bin"
    write_file(file_path, 100)
    first = run_persisted_scan(migrated_session_factory, target)
    write_file(file_path, 150)
    second = run_persisted_scan(migrated_session_factory, target)
    write_file(file_path, 75)
    third = run_persisted_scan(migrated_session_factory, target)
    file_path.unlink()
    fourth = run_persisted_scan(migrated_session_factory, target)

    second_diffs, _ = diff_by_path(migrated_session_factory, first, second)
    third_diffs, _ = diff_by_path(migrated_session_factory, second, third)
    fourth_diffs, _ = diff_by_path(migrated_session_factory, third, fourth)

    assert second_diffs[str(target)].direct_delta_bytes == 50
    assert second_diffs[str(target)].state == "grown"
    assert third_diffs[str(target)].direct_delta_bytes == -75
    assert third_diffs[str(target)].state == "reduced"
    assert fourth_diffs[str(target)].direct_delta_bytes == -75


def test_file_move_offsets_net_change(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    folder_a = target / "A"
    folder_b = target / "B"
    write_file(folder_a / "file.bin", 100)
    folder_b.mkdir()
    baseline_id = run_persisted_scan(migrated_session_factory, target)
    shutil.move(str(folder_a / "file.bin"), str(folder_b / "file.bin"))
    current_id = run_persisted_scan(migrated_session_factory, target)

    diffs, report = diff_by_path(migrated_session_factory, baseline_id, current_id)

    assert diffs[str(folder_a)].direct_delta_bytes == -100
    assert diffs[str(folder_b)].direct_delta_bytes == 100
    assert report.summary.net_change_bytes == 0


def test_new_and_removed_folders(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    empty_removed = target / "empty-removed"
    removed = target / "removed"
    empty_removed.mkdir(parents=True)
    write_file(removed / "file.bin", 100)
    baseline_id = run_persisted_scan(migrated_session_factory, target)
    shutil.rmtree(removed)
    empty_removed.rmdir()
    (target / "empty-new").mkdir()
    write_file(target / "new" / "file.bin", 100)
    current_id = run_persisted_scan(migrated_session_factory, target)

    diffs, _ = diff_by_path(migrated_session_factory, baseline_id, current_id)

    assert diffs[str(target / "new")].state == "new"
    assert diffs[str(target / "new")].direct_delta_bytes == 100
    assert diffs[str(target / "empty-new")].state == "new"
    assert diffs[str(target / "empty-new")].direct_delta_bytes == 0
    assert diffs[str(removed)].state == "removed"
    assert diffs[str(removed)].direct_delta_bytes == -100
    assert diffs[str(empty_removed)].state == "removed"
    assert diffs[str(empty_removed)].direct_delta_bytes == 0


def test_cancelled_scan_is_excluded_as_baseline(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_file(target / "file.bin", 100)
    first = run_persisted_scan(migrated_session_factory, target)
    run_persisted_scan(migrated_session_factory, target, cancelled=True)
    write_file(target / "file.bin", 150)
    current = run_persisted_scan(migrated_session_factory, target)

    with migrated_session_factory() as session:
        current_scan = session.get(Scan, current)

    assert current_scan.baseline_scan_id == first


def test_threshold_change_does_not_break_comparability(migrated_session_factory, tmp_path: Path) -> None:
    target = tmp_path / "target"
    write_file(target / "file.bin", 100)
    first = run_persisted_scan(migrated_session_factory, target, threshold_mb=1)
    write_file(target / "file.bin", 200)
    current = run_persisted_scan(migrated_session_factory, target, threshold_mb=500)

    with migrated_session_factory() as session:
        selection = BaselineSelector().find_previous_comparable_scan(session, current)

    assert selection.baseline_scan_id == first


def test_phase_1_timestamp_only_scan_is_not_selected_as_baseline(
    migrated_session_factory, tmp_path: Path
) -> None:
    target = tmp_path / "target"
    write_file(target / "file.bin", 100)
    old_scan = run_persisted_scan(migrated_session_factory, target)
    with migrated_session_factory() as session:
        session.execute(
            update(Scan)
            .where(Scan.id == old_scan)
            .values(measurement_algorithm_version=1)
        )
        session.commit()
    write_file(target / "file.bin", 200)
    current = run_persisted_scan(migrated_session_factory, target)

    with migrated_session_factory() as session:
        current_scan = session.get(Scan, current)

    assert current_scan.baseline_scan_id is None
    assert current_scan.comparison_status == "baseline_created"


def test_comparison_failure_does_not_invalidate_completed_scan(
    migrated_session_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    target = tmp_path / "target"
    write_file(target / "file.bin", 100)
    run_persisted_scan(migrated_session_factory, target)
    write_file(target / "file.bin", 200)

    def fail_compare(self, session, previous_scan_id, current_scan_id, *, force=False):
        raise RuntimeError("comparison failed")

    monkeypatch.setattr("windows_folder_sizes_diff.db.persistence.ScanDiffer.compare", fail_compare)
    current = run_persisted_scan(migrated_session_factory, target)

    with migrated_session_factory() as session:
        current_scan = session.get(Scan, current)
        observations = list(
            session.scalars(
                select(DirectoryObservation).where(DirectoryObservation.scan_id == current)
            )
        )

    assert current_scan.status == "completed"
    assert current_scan.comparison_status == "failed"
    assert current_scan.comparison_failure_message == "comparison failed"
    assert observations


def test_incomplete_measurement_has_unknown_delta(migrated_session_factory, tmp_path: Path) -> None:
    lifecycle = ScanLifecycleService(migrated_session_factory)
    target = tmp_path / "target"
    target.mkdir()
    request = ScanRequest(target_directory=target, growth_threshold_mb=0, history_days=1)
    baseline = lifecycle.create_scan(request)
    current = lifecycle.create_scan(request)
    lifecycle.mark_running(baseline.id)
    lifecycle.mark_running(current.id)
    now = utc_now()
    baseline_completion = ScanCompleted(
        scan_id=baseline.id,
        started_at=now,
        completed_at=now,
        cancelled=False,
        folders_scanned=1,
        folders_matched=0,
        warning_count=0,
        results=[],
    )
    current_completion = baseline_completion.model_copy(update={"scan_id": current.id})
    baseline_coordinator = ScanPersistenceCoordinator(
        scan_id=baseline.id,
        session_factory=migrated_session_factory,
        lifecycle_service=lifecycle,
    )
    current_coordinator = ScanPersistenceCoordinator(
        scan_id=current.id,
        session_factory=migrated_session_factory,
        lifecycle_service=lifecycle,
    )
    from windows_folder_sizes_diff.scanner.events import FolderObserved

    baseline_coordinator.handle_event(
        FolderObserved(
            scan_id=baseline.id,
            observation=FolderObservation(
                path=target,
                matching_bytes=0,
                direct_logical_bytes=100,
                direct_file_count=1,
                files_examined=1,
                matched_file_count=0,
                scanned_at=now,
                measurement_status="complete",
            ),
        )
    )
    baseline_coordinator.handle_event(baseline_completion)
    current_coordinator.handle_event(
        FolderObserved(
            scan_id=current.id,
            observation=FolderObservation(
                path=target,
                matching_bytes=0,
                direct_logical_bytes=None,
                direct_file_count=0,
                files_examined=0,
                matched_file_count=0,
                scanned_at=now,
                measurement_status="inaccessible",
                status="inaccessible",
            ),
        )
    )
    current_coordinator.handle_event(current_completion)

    diffs, _ = diff_by_path(migrated_session_factory, baseline.id, current.id)

    assert diffs[str(target)].state == "incomplete"
    assert diffs[str(target)].direct_delta_bytes is None
