"""Phase 3 hierarchical sizing tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.analysis.hierarchy import (
    HierarchyAggregator,
    HierarchyAggregationResult,
    AGG_COMPLETED,
    AGG_COMPLETED_WITH_WARNINGS,
)
from windows_folder_sizes_diff.analysis.differ import ScanDiffer
from windows_folder_sizes_diff.analysis.models import DirectoryDiff, ScanDiffReport
from windows_folder_sizes_diff.db.configuration import MEASUREMENT_ALGORITHM_VERSION, HIERARCHY_ALGORITHM_VERSION
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService, ScanRecord
from windows_folder_sizes_diff.db.models import (
    Directory,
    DirectoryObservation,
    Scan,
    ScanWarningRecord,
)
from windows_folder_sizes_diff.db.pathing import normalize_windows_path
from windows_folder_sizes_diff.db.persistence import ScanPersistenceCoordinator
from windows_folder_sizes_diff.db.repositories import DirectoryRepository, ObservationRepository, ScanRepository
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import FolderObserved, ScanCompleted
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)


def _make_scan_record(lifecycle: ScanLifecycleService, target: Path) -> ScanRecord:
    request = ScanRequest(
        target_directory=target,
        growth_threshold_mb=0,
        history_days=30,
    )
    return lifecycle.create_scan(request)


def _add_observation(
    session: Session,
    scan_id: int,
    path: Path,
    direct_bytes: int,
    *,
    parent_path: Path | None = None,
    depth: int = 0,
    direct_file_count: int = 0,
    direct_child_count: int = 0,
    measurement_status: str = "complete",
) -> int:
    """Insert a directory and its observation, return directory_id."""
    dirs = DirectoryRepository()
    parent_map = {}
    depth_map = {}
    normalized = normalize_windows_path(path)
    depth_map[normalized] = depth
    if parent_path:
        parent_map[normalized] = normalize_windows_path(parent_path)
    dir_ids = dirs.ensure_many(session, [path], scan_id=scan_id, parent_map=parent_map, depth_map=depth_map)
    dir_id = dir_ids[normalized]

    # Set parent_directory_id if needed
    if parent_path:
        parent_norm = normalize_windows_path(parent_path)
        parent_dir_ids = dirs.ensure_many(session, [parent_path], scan_id=scan_id, parent_map={}, depth_map={depth - 1: depth - 1} if depth > 0 else {})
        session.execute(
            update(Directory)
            .where(Directory.id == dir_id)
            .values(parent_directory_id=parent_dir_ids.get(parent_norm))
        )

    obs = FolderObservation(
        path=path,
        parent_path=parent_path,
        depth=depth,
        matching_bytes=0,
        direct_file_count=direct_file_count,
        matched_file_count=0,
        direct_logical_bytes=direct_bytes,
        direct_child_count=direct_child_count,
        files_examined=direct_file_count,
        measurement_status=measurement_status,
        scanned_at=utc_now(),
        status="observed",
    )
    obs_repo = ObservationRepository()
    obs_repo.insert_many(session, [obs], scan_id=scan_id, directory_ids=dir_ids)
    session.commit()
    return dir_id


def _finalize_scan(session: Session, scan_id: int, status: str = "completed") -> None:
    session.execute(
        update(Scan)
        .where(Scan.id == scan_id)
        .values(
            status=status,
            completed_at=utc_now(),
            measurement_algorithm_version=MEASUREMENT_ALGORITHM_VERSION,
            hierarchy_algorithm_version=HIERARCHY_ALGORITHM_VERSION,
        )
    )
    session.commit()


# ---------------------------------------------------------------------------
# 28.1 Direct and inclusive size tests
# ---------------------------------------------------------------------------

class TestDirectAndInclusiveSizes:
    """Spec §28.1"""

    def test_simple_hierarchy(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child_a = root / "ChildA"
            child_b = root / "ChildB"
            _make_file(root / "root.bin", 100)
            _make_file(child_a / "a.bin", 250)
            _make_file(child_b / "b.bin", 150)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            record = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(record.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, record.id)
                _add_observation(session, record.id, root, 100, depth=0, direct_file_count=1, direct_child_count=2)
                _add_observation(session, record.id, child_a, 250, parent_path=root, depth=1, direct_file_count=1)
                _add_observation(session, record.id, child_b, 150, parent_path=root, depth=1, direct_file_count=1)

                agg = HierarchyAggregator()
                result = agg.aggregate_scan(session, record.id)
                session.commit()

            assert result.status in (AGG_COMPLETED, AGG_COMPLETED_WITH_WARNINGS)

            with migrated_session_factory() as session:
                obs = session.execute(
                    select(DirectoryObservation, Directory)
                    .join(Directory, Directory.id == DirectoryObservation.directory_id)
                    .where(DirectoryObservation.scan_id == record.id)
                ).all()

                by_path: dict[str, tuple[int | None, int | None]] = {}
                for row in obs:
                    by_path[row.Directory.display_path] = (
                        row.DirectoryObservation.direct_logical_bytes,
                        row.DirectoryObservation.inclusive_logical_bytes,
                    )

                assert by_path[str(root)][0] == 100  # direct
                assert by_path[str(root)][1] == 500  # inclusive
                assert by_path[str(child_a)][0] == 250
                assert by_path[str(child_a)][1] == 250
                assert by_path[str(child_b)][0] == 150
                assert by_path[str(child_b)][1] == 150


# ---------------------------------------------------------------------------
# 28.2 Nested hierarchy test
# ---------------------------------------------------------------------------

class TestNestedHierarchy:
    """Spec §28.2"""

    def test_deep_hierarchy(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            d1 = root / "L1"
            d2 = d1 / "L2"
            d3 = d2 / "L3"
            d4 = d3 / "L4"
            d5 = d4 / "L5"

            _make_file(root / "r.bin", 10)
            _make_file(d1 / "a.bin", 20)
            _make_file(d2 / "b.bin", 30)
            _make_file(d3 / "c.bin", 40)
            _make_file(d4 / "d.bin", 50)
            _make_file(d5 / "e.bin", 60)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            record = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(record.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, record.id)
                _add_observation(session, record.id, root, 10, depth=0, direct_child_count=1)
                _add_observation(session, record.id, d1, 20, parent_path=root, depth=1, direct_child_count=1)
                _add_observation(session, record.id, d2, 30, parent_path=d1, depth=2, direct_child_count=1)
                _add_observation(session, record.id, d3, 40, parent_path=d2, depth=3, direct_child_count=1)
                _add_observation(session, record.id, d4, 50, parent_path=d3, depth=4, direct_child_count=1)
                _add_observation(session, record.id, d5, 60, parent_path=d4, depth=5, direct_child_count=1)

                agg = HierarchyAggregator()
                agg.aggregate_scan(session, record.id)
                session.commit()

            expected_inclusive = {
                str(root): 210,  # 10+20+30+40+50+60
                str(d1): 200,   # 20+30+40+50+60
                str(d2): 180,
                str(d3): 150,
                str(d4): 110,
                str(d5): 60,
            }
            with migrated_session_factory() as session:
                obs = session.execute(
                    select(DirectoryObservation, Directory)
                    .join(Directory)
                    .where(DirectoryObservation.scan_id == record.id)
                ).all()
                for row in obs:
                    assert row.DirectoryObservation.inclusive_logical_bytes == expected_inclusive[row.Directory.display_path]


# ---------------------------------------------------------------------------
# 28.3 Parent/child double-count test
# ---------------------------------------------------------------------------

class TestDoubleCountPrevention:
    """Spec §28.3"""

    def test_double_count_prevention(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child = root / "Child"
            deep = child / "Deep"

            # First scan: empty
            _make_file(root / "existing.bin", 10)
            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 10, depth=0, direct_child_count=1)
                _add_observation(session, scan1.id, child, 0, parent_path=root, depth=1, direct_child_count=1)
                _add_observation(session, scan1.id, deep, 0, parent_path=child, depth=2, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            # Second scan: add 200 bytes only in deep
            _make_file(deep / "new.bin", 200)
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 10, depth=0, direct_child_count=1)
                _add_observation(session, scan2.id, child, 0, parent_path=root, depth=1, direct_child_count=1)
                _add_observation(session, scan2.id, deep, 200, parent_path=child, depth=2, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            by_path = {str(d.path): d for d in report.results}

            assert by_path[str(deep)].direct_delta_bytes == 200
            assert by_path[str(child)].direct_delta_bytes == 0
            assert by_path[str(root)].direct_delta_bytes == 0
            assert by_path[str(deep)].inclusive_delta_bytes == 200
            assert by_path[str(child)].inclusive_delta_bytes == 200
            assert by_path[str(root)].inclusive_delta_bytes == 200
            assert report.summary.net_change_bytes == 200


# ---------------------------------------------------------------------------
# 28.4 Root direct file test
# ---------------------------------------------------------------------------

class TestRootDirectFile:
    """Spec §28.4"""

    def test_root_direct_file_addition(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            _make_file(root / "big.bin", 500)
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 500, depth=0, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            root_diff = next(d for d in report.results if d.depth == 0)
            assert root_diff.direct_delta_bytes == 500
            assert root_diff.inclusive_delta_bytes == 500


# ---------------------------------------------------------------------------
# 28.5 Multiple branches test
# ---------------------------------------------------------------------------

class TestMultipleBranches:
    """Spec §28.5"""

    def test_multiple_branches(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            branch_a = root / "BranchA"
            branch_b = root / "BranchB"

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=2)
                _add_observation(session, scan1.id, branch_a, 0, parent_path=root, depth=1)
                _add_observation(session, scan1.id, branch_b, 0, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            _make_file(branch_a / "a.bin", 100)
            _make_file(branch_b / "b.bin", 200)
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 0, depth=0, direct_child_count=2)
                _add_observation(session, scan2.id, branch_a, 100, parent_path=root, depth=1)
                _add_observation(session, scan2.id, branch_b, 200, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            by_path = {str(d.path): d for d in report.results}
            assert by_path[str(branch_a)].direct_delta_bytes == 100
            assert by_path[str(branch_b)].direct_delta_bytes == 200
            assert by_path[str(root)].direct_delta_bytes == 0
            assert by_path[str(root)].inclusive_delta_bytes == 300
            assert report.summary.net_change_bytes == 300


# ---------------------------------------------------------------------------
# 28.6 File deletion test
# ---------------------------------------------------------------------------

class TestFileDeletion:
    """Spec §28.6"""

    def test_file_deletion(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child = root / "Child"
            _make_file(child / "temp.bin", 100)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=1)
                _add_observation(session, scan1.id, child, 100, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            # Delete the file
            (child / "temp.bin").unlink()
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 0, depth=0, direct_child_count=1)
                _add_observation(session, scan2.id, child, 0, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            by_path = {str(d.path): d for d in report.results}
            assert by_path[str(child)].direct_delta_bytes == -100
            assert by_path[str(root)].direct_delta_bytes == 0
            assert by_path[str(root)].inclusive_delta_bytes == -100
            assert report.summary.net_change_bytes == -100


# ---------------------------------------------------------------------------
# 28.7 Directory removal test
# ---------------------------------------------------------------------------

class TestDirectoryRemoval:
    """Spec §28.7"""

    def test_directory_removal(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child = root / "Child"
            _make_file(child / "data.bin", 75)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=1)
                _add_observation(session, scan1.id, child, 75, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            # Second scan: child does not exist
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 0, depth=0, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            by_path = {str(d.path): d for d in report.results}
            assert str(child) in by_path
            child_diff = by_path[str(child)]
            assert child_diff.state == "removed"
            assert child_diff.direct_delta_bytes == -75
            assert child_diff.previous_direct_bytes == 75
            assert child_diff.current_direct_bytes == 0


# ---------------------------------------------------------------------------
# 28.8 New directory tree test
# ---------------------------------------------------------------------------

class TestNewDirectoryTree:
    """Spec §28.8"""

    def test_new_directory_tree(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            new_parent = root / "NewParent"
            new_child = new_parent / "NewChild"
            _make_file(new_parent / "p.bin", 50)
            _make_file(new_child / "c.bin", 30)
            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 0, depth=0, direct_child_count=1)
                _add_observation(session, scan2.id, new_parent, 50, parent_path=root, depth=1, direct_child_count=1)
                _add_observation(session, scan2.id, new_child, 30, parent_path=new_parent, depth=2, direct_child_count=0)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            by_path = {str(d.path): d for d in report.results}
            assert by_path[str(new_parent)].direct_delta_bytes == 50
            assert by_path[str(new_parent)].state == "new"
            assert by_path[str(new_child)].direct_delta_bytes == 30
            assert by_path[str(new_child)].state == "new"
            assert by_path[str(root)].inclusive_delta_bytes == 80
            assert report.summary.net_change_bytes == 80


# ---------------------------------------------------------------------------
# 28.9 Inaccessible descendant test (mocked)
# ---------------------------------------------------------------------------

class TestInaccessibleDescendant:
    """Spec §28.9"""

    def test_partial_propagation(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child = root / "Child"
            restricted = child / "Restricted"
            _make_file(root / "r.bin", 10)
            _make_file(child / "c.bin", 20)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            record = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(record.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, record.id)
                _add_observation(session, record.id, root, 10, depth=0, direct_child_count=1)
                _add_observation(session, record.id, child, 20, parent_path=root, depth=1, direct_child_count=1)
                # Restricted is marked as incomplete
                _add_observation(session, record.id, restricted, None,
                               parent_path=child, depth=2, direct_child_count=0,
                               measurement_status="inaccessible")
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, record.id)
                session.commit()

            with migrated_session_factory() as session:
                obs = session.execute(
                    select(DirectoryObservation, Directory)
                    .join(Directory)
                    .where(DirectoryObservation.scan_id == record.id)
                ).all()

                by_path = {}
                for row in obs:
                    by_path[row.Directory.display_path] = row.DirectoryObservation

                # Restricted: partial/direct may be None
                assert by_path[str(restricted)].measurement_status == "inaccessible"
                # Child should have partial hierarchy
                assert by_path[str(child)].hierarchy_status in ("partial", "pending")
                # Root should have partial hierarchy
                assert by_path[str(root)].hierarchy_status in ("partial", "pending")


# ---------------------------------------------------------------------------
# 28.10 Orphan test
# ---------------------------------------------------------------------------

class TestOrphanHandling:
    """Spec §28.10"""

    def test_orphan_detection(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            orphan = root / "Orphan"

            lifecycle = ScanLifecycleService(migrated_session_factory)
            record = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(record.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, record.id)
                # Root without parent (correct)
                _add_observation(session, record.id, root, 0, depth=0, direct_child_count=0)
                # Orphan with incorrect depth (depth says 3 but parent is None)
                # We simulate by directly inserting with wrong depth
                dirs = DirectoryRepository()
                dir_ids = dirs.ensure_many(session, [orphan], scan_id=record.id,
                                          parent_map={}, depth_map={normalize_windows_path(orphan): 3})
                obs = FolderObservation(
                    path=orphan, parent_path=None, depth=3,
                    matching_bytes=0, direct_file_count=0, matched_file_count=0,
                    direct_logical_bytes=50, direct_child_count=0,
                    files_examined=0, measurement_status="complete",
                    scanned_at=utc_now(), status="observed",
                )
                ObservationRepository().insert_many(session, [obs], scan_id=record.id, directory_ids=dir_ids)
                # Manually set parent to None even at depth 3
                session.execute(
                    update(Directory)
                    .where(Directory.normalized_path == normalize_windows_path(orphan))
                    .values(parent_directory_id=None)
                )
                session.commit()

                agg = HierarchyAggregator()
                result = agg.aggregate_scan(session, record.id)
                session.commit()

            # Orphan should be detected
            assert result.orphaned_directories > 0 or len(result.warnings) > 0

            with migrated_session_factory() as session:
                warning = session.scalar(
                    select(ScanWarningRecord).where(
                        ScanWarningRecord.scan_id == record.id,
                        ScanWarningRecord.operation == "hierarchy_aggregation",
                    )
                )

            assert warning is not None
            assert warning.error_type == "orphaned"


# ---------------------------------------------------------------------------
# 28.11 Cycle test
# ---------------------------------------------------------------------------

class TestCycleDetection:
    """Spec §28.11"""

    def test_cycle_detection(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            a = root / "A"
            b = root / "B"

            lifecycle = ScanLifecycleService(migrated_session_factory)
            record = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(record.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, record.id)
                dirs = DirectoryRepository()
                dir_ids = dirs.ensure_many(session, [root, a, b], scan_id=record.id,
                                          parent_map={
                                              normalize_windows_path(a): normalize_windows_path(b),
                                              normalize_windows_path(b): normalize_windows_path(a),
                                          },
                                          depth_map={
                                              normalize_windows_path(root): 0,
                                              normalize_windows_path(a): 1,
                                              normalize_windows_path(b): 1,
                                          })
                for path, depth, parent in [(root, 0, None), (a, 1, b), (b, 1, a)]:
                    parent_norm = normalize_windows_path(parent) if parent else None
                    obs = FolderObservation(
                        path=path, parent_path=parent, depth=depth,
                        matching_bytes=0, direct_file_count=0, matched_file_count=0,
                        direct_logical_bytes=10, direct_child_count=0,
                        files_examined=0, measurement_status="complete",
                        scanned_at=utc_now(), status="observed",
                    )
                    ObservationRepository().insert_many(session, [obs], scan_id=record.id, directory_ids=dir_ids)

                # Set circular parent_directory_id
                for p, parent_p in [(a, b), (b, a)]:
                    session.execute(
                        update(Directory)
                        .where(Directory.normalized_path == normalize_windows_path(p))
                        .values(parent_directory_id=dir_ids[normalize_windows_path(parent_p)])
                    )
                session.commit()

                agg = HierarchyAggregator()
                result = agg.aggregate_scan(session, record.id)
                session.commit()

            # Cycle should be detected
            assert result.cycle_count > 0 or len(result.warnings) > 0


# ---------------------------------------------------------------------------
# 28.12 Migration test
# ---------------------------------------------------------------------------

class TestMigration:
    """Spec §28.12"""

    def test_phase2_db_upgrades(self, migrated_session_factory: sessionmaker[Session]):
        with migrated_session_factory() as session:
            tables = set(session.execute(
                text("SELECT name FROM sqlite_master WHERE type = 'table'")
            ).scalars().all())

            assert "directories" in tables
            assert "directory_observations" in tables
            assert "scans" in tables

            # Verify new columns exist by inspecting
            from sqlalchemy import inspect as sa_inspect
            inspector = sa_inspect(session.get_bind())

            dir_cols = {c["name"] for c in inspector.get_columns("directories")}
            assert "parent_directory_id" in dir_cols
            assert "depth" in dir_cols

            obs_cols = {c["name"] for c in inspector.get_columns("directory_observations")}
            assert "inclusive_logical_bytes" in obs_cols
            assert "inclusive_file_count" in obs_cols
            assert "direct_child_count" in obs_cols
            assert "descendant_directory_count" in obs_cols
            assert "hierarchy_status" in obs_cols

            scan_cols = {c["name"] for c in inspector.get_columns("scans")}
            assert "hierarchy_algorithm_version" in scan_cols
            assert "direct_measurement_status" in scan_cols
            assert "hierarchy_aggregation_status" in scan_cols


# ---------------------------------------------------------------------------
# 28.13 Report total test
# ---------------------------------------------------------------------------

class TestReportTotals:
    """Spec §28.13"""

    def test_report_totals_use_direct_only(self, migrated_session_factory: sessionmaker[Session]):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "Root"
            child_a = root / "ChildA"
            child_b = root / "ChildB"
            _make_file(child_a / "a.bin", 100)
            _make_file(child_b / "b.bin", 200)

            lifecycle = ScanLifecycleService(migrated_session_factory)
            scan1 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan1.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan1.id)
                _add_observation(session, scan1.id, root, 0, depth=0, direct_child_count=2)
                _add_observation(session, scan1.id, child_a, 0, parent_path=root, depth=1)
                _add_observation(session, scan1.id, child_b, 0, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan1.id)
                session.commit()

            scan2 = _make_scan_record(lifecycle, root)
            lifecycle.mark_running(scan2.id)

            with migrated_session_factory() as session:
                _finalize_scan(session, scan2.id)
                _add_observation(session, scan2.id, root, 0, depth=0, direct_child_count=2)
                _add_observation(session, scan2.id, child_a, 100, parent_path=root, depth=1)
                _add_observation(session, scan2.id, child_b, 200, parent_path=root, depth=1)
                agg = HierarchyAggregator()
                agg.aggregate_scan(session, scan2.id)
                session.commit()

            differ = ScanDiffer()
            with migrated_session_factory() as session:
                report = differ.compare(session, scan1.id, scan2.id, force=True)

            # Grand total must equal sum of direct deltas (300), not inclusive values (600)
            assert report.summary.net_change_bytes == 300
            assert report.summary.total_positive_growth_bytes == 300
            # sum of direct deltas = 100 + 200 = 300
            direct_deltas = [d.direct_delta_bytes for d in report.results if d.direct_delta_bytes is not None]
            assert sum(direct_deltas) == 300
