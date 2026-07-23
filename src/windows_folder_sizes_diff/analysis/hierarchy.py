"""Hierarchy aggregation service for Phase 3.

Calculates inclusive (subtree) measurements from direct measurements
using bottom-up iterative aggregation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from windows_folder_sizes_diff.db.models import Directory, DirectoryObservation, Scan, ScanWarningRecord
from windows_folder_sizes_diff.db.time import utc_now

LOGGER = logging.getLogger(__name__)

# Hierarchy status values
HIERARCHY_PENDING = "pending"
HIERARCHY_COMPLETE = "complete"
HIERARCHY_PARTIAL = "partial"
HIERARCHY_ORPHANED = "orphaned"
HIERARCHY_INVALID_PARENT = "invalid_parent"
HIERARCHY_CYCLE_DETECTED = "cycle_detected"
HIERARCHY_UNAVAILABLE = "unavailable"

# Aggregation status values
AGG_NOT_STARTED = "not_started"
AGG_RUNNING = "running"
AGG_COMPLETED = "completed"
AGG_COMPLETED_WITH_WARNINGS = "completed_with_warnings"
AGG_FAILED = "failed"
AGG_UNAVAILABLE = "unavailable"

BATCH_SIZE = 1000


@dataclass
class HierarchyNode:
    """Lightweight node for aggregation."""

    observation_id: int
    directory_id: int
    path: str
    parent_directory_id: int | None
    depth: int
    direct_logical_bytes: int
    direct_file_count: int
    direct_child_count: int
    measurement_status: str
    warning_count: int


@dataclass
class HierarchyAggregationResult:
    """Result of hierarchy aggregation for a scan."""

    scan_id: int
    directories_processed: int
    complete_directories: int
    partial_directories: int
    orphaned_directories: int
    cycle_count: int
    status: str
    started_at: datetime
    completed_at: datetime
    warnings: list[str] = field(default_factory=list)


class HierarchyAggregator:
    """Calculate inclusive measurements from direct measurements bottom-up."""

    def aggregate_scan(self, session: Session, scan_id: int) -> HierarchyAggregationResult:
        """Run hierarchy aggregation for a completed scan.

        Returns a result describing what happened. Updates the database
        with inclusive measurements and hierarchy statuses.
        """
        started_at = utc_now()
        warnings: list[str] = []

        # Mark aggregation as running
        self._set_aggregation_status(session, scan_id, AGG_RUNNING)

        try:
            # Load nodes
            nodes = self._load_nodes(session, scan_id)
            if not nodes:
                result = HierarchyAggregationResult(
                    scan_id=scan_id,
                    directories_processed=0,
                    complete_directories=0,
                    partial_directories=0,
                    orphaned_directories=0,
                    cycle_count=0,
                    status=AGG_COMPLETED,
                    started_at=started_at,
                    completed_at=utc_now(),
                )
                self._set_aggregation_status(session, scan_id, AGG_COMPLETED)
                return result

            # Build lookup maps
            node_by_dir: dict[int, HierarchyNode] = {n.directory_id: n for n in nodes}
            dir_id_to_obs_id: dict[int, int] = {n.directory_id: n.observation_id for n in nodes}

            # Validate hierarchy
            orphans, cycles = self._validate_hierarchy(nodes, node_by_dir)
            if cycles:
                warnings.append(f"Detected {len(cycles)} hierarchy cycle(s).")
            if orphans:
                warnings.append(f"Detected {len(orphans)} orphaned directories.")
            self._persist_hierarchy_warnings(session, scan_id, node_by_dir, orphans, cycles)

            # Initialize aggregates
            inclusive_bytes: dict[int, int] = {}
            inclusive_files: dict[int, int] = {}
            descendant_counts: dict[int, int] = {}
            hierarchy_status: dict[int, str] = {}

            for node in nodes:
                inclusive_bytes[node.directory_id] = node.direct_logical_bytes
                inclusive_files[node.directory_id] = node.direct_file_count
                descendant_counts[node.directory_id] = 0

                if node.directory_id in cycles:
                    hierarchy_status[node.directory_id] = HIERARCHY_CYCLE_DETECTED
                elif node.directory_id in orphans:
                    hierarchy_status[node.directory_id] = HIERARCHY_ORPHANED
                elif node.measurement_status not in ("complete",):
                    hierarchy_status[node.directory_id] = HIERARCHY_PARTIAL
                else:
                    hierarchy_status[node.directory_id] = HIERARCHY_COMPLETE

            # Sort by depth descending for bottom-up aggregation
            sorted_nodes = sorted(nodes, key=lambda n: n.depth, reverse=True)

            # Aggregate bottom-up
            for node in sorted_nodes:
                if node.directory_id in cycles:
                    continue

                parent_id = node.parent_directory_id
                if parent_id is not None and parent_id in node_by_dir:
                    # Skip aggregation into cycle parents
                    if parent_id in cycles:
                        continue

                    inclusive_bytes[parent_id] = inclusive_bytes.get(parent_id, 0) + inclusive_bytes[node.directory_id]
                    inclusive_files[parent_id] = inclusive_files.get(parent_id, 0) + inclusive_files[node.directory_id]
                    descendant_counts[parent_id] = descendant_counts.get(parent_id, 0) + 1 + descendant_counts[node.directory_id]

                    # Propagate partial status upward
                    if hierarchy_status[node.directory_id] in (HIERARCHY_PARTIAL, HIERARCHY_ORPHANED, HIERARCHY_CYCLE_DETECTED):
                        if hierarchy_status.get(parent_id) == HIERARCHY_COMPLETE:
                            hierarchy_status[parent_id] = HIERARCHY_PARTIAL

            # Persist results in batches
            self._persist_results(
                session,
                dir_id_to_obs_id,
                inclusive_bytes,
                inclusive_files,
                descendant_counts,
                hierarchy_status,
            )

            # Count results
            complete = sum(1 for s in hierarchy_status.values() if s == HIERARCHY_COMPLETE)
            partial = sum(1 for s in hierarchy_status.values() if s == HIERARCHY_PARTIAL)
            orphaned = sum(1 for s in hierarchy_status.values() if s == HIERARCHY_ORPHANED)

            status = AGG_COMPLETED
            if warnings:
                status = AGG_COMPLETED_WITH_WARNINGS

            result = HierarchyAggregationResult(
                scan_id=scan_id,
                directories_processed=len(nodes),
                complete_directories=complete,
                partial_directories=partial,
                orphaned_directories=orphaned,
                cycle_count=len(cycles),
                status=status,
                started_at=started_at,
                completed_at=utc_now(),
                warnings=warnings,
            )
            self._set_aggregation_status(session, scan_id, status)
            return result

        except Exception:
            LOGGER.exception("Hierarchy aggregation failed for scan %s", scan_id)
            self._set_aggregation_status(session, scan_id, AGG_FAILED)
            raise

    def _load_nodes(self, session: Session, scan_id: int) -> list[HierarchyNode]:
        """Load directory observations with hierarchy info for a scan."""
        statement = (
            select(
                DirectoryObservation.id,
                DirectoryObservation.directory_id,
                Directory.display_path,
                Directory.parent_directory_id,
                Directory.depth,
                DirectoryObservation.direct_logical_bytes,
                DirectoryObservation.direct_file_count,
                DirectoryObservation.direct_child_count,
                DirectoryObservation.measurement_status,
                DirectoryObservation.warning_count,
            )
            .join(Directory, Directory.id == DirectoryObservation.directory_id)
            .where(DirectoryObservation.scan_id == scan_id)
        )
        rows = session.execute(statement).all()
        return [
            HierarchyNode(
                observation_id=row.id,
                directory_id=row.directory_id,
                path=row.display_path,
                parent_directory_id=row.parent_directory_id,
                depth=row.depth,
                direct_logical_bytes=row.direct_logical_bytes or 0,
                direct_file_count=row.direct_file_count,
                direct_child_count=row.direct_child_count,
                measurement_status=row.measurement_status,
                warning_count=row.warning_count,
            )
            for row in rows
        ]

    def _validate_hierarchy(
        self,
        nodes: list[HierarchyNode],
        node_by_dir: dict[int, HierarchyNode],
    ) -> tuple[set[int], set[int]]:
        """Validate the hierarchy and return (orphans, cycles)."""
        orphans: set[int] = set()
        cycles: set[int] = set()

        for node in nodes:
            # Root should have no parent
            if node.depth == 0 and node.parent_directory_id is not None:
                orphans.add(node.directory_id)

            # Non-root should have a known parent
            if node.depth > 0:
                if node.parent_directory_id is None:
                    orphans.add(node.directory_id)
                elif node.parent_directory_id not in node_by_dir:
                    orphans.add(node.directory_id)
                else:
                    parent = node_by_dir[node.parent_directory_id]
                    # Check depth consistency
                    if node.depth != parent.depth + 1:
                        orphans.add(node.directory_id)

            # Check for self-reference
            if node.parent_directory_id == node.directory_id:
                cycles.add(node.directory_id)

        # Detect cycles iteratively so very deep trees cannot hit recursion limits.
        if not cycles:
            cycles.update(self._detect_cycles(nodes, node_by_dir))

        return orphans, cycles

    def _detect_cycles(
        self,
        nodes: list[HierarchyNode],
        node_by_dir: dict[int, HierarchyNode],
    ) -> set[int]:
        """Detect cycles in parent chains without recursive traversal."""
        checked: set[int] = set()
        cycle_nodes: set[int] = set()

        for node in nodes:
            if node.directory_id in checked:
                continue

            path_index: dict[int, int] = {}
            path: list[int] = []
            current_id: int | None = node.directory_id
            while current_id is not None:
                if current_id in path_index:
                    cycle_nodes.update(path[path_index[current_id]:])
                    break
                if current_id in checked:
                    break
                current = node_by_dir.get(current_id)
                if current is None:
                    break
                path_index[current_id] = len(path)
                path.append(current_id)
                current_id = current.parent_directory_id

            checked.update(path)

        return cycle_nodes

    def _persist_results(
        self,
        session: Session,
        dir_id_to_obs_id: dict[int, int],
        inclusive_bytes: dict[int, int],
        inclusive_files: dict[int, int],
        descendant_counts: dict[int, int],
        hierarchy_status: dict[int, str],
    ) -> None:
        """Persist inclusive results in batches."""
        updates = []
        for dir_id, obs_id in dir_id_to_obs_id.items():
            updates.append({
                "id": obs_id,
                "inclusive_logical_bytes": inclusive_bytes.get(dir_id),
                "inclusive_file_count": inclusive_files.get(dir_id),
                "descendant_directory_count": descendant_counts.get(dir_id, 0),
                "hierarchy_status": hierarchy_status.get(dir_id, HIERARCHY_PENDING),
            })

        for batch_start in range(0, len(updates), BATCH_SIZE):
            batch = updates[batch_start:batch_start + BATCH_SIZE]
            for item in batch:
                session.execute(
                    update(DirectoryObservation)
                    .where(DirectoryObservation.id == item["id"])
                    .values(
                        inclusive_logical_bytes=item["inclusive_logical_bytes"],
                        inclusive_file_count=item["inclusive_file_count"],
                        descendant_directory_count=item["descendant_directory_count"],
                        hierarchy_status=item["hierarchy_status"],
                    )
                )
            session.flush()

    def _persist_hierarchy_warnings(
        self,
        session: Session,
        scan_id: int,
        node_by_dir: dict[int, HierarchyNode],
        orphans: set[int],
        cycles: set[int],
    ) -> None:
        """Persist structured warnings for hierarchy validation failures."""
        if not orphans and not cycles:
            return
        now = utc_now()
        rows = []
        for directory_id in sorted(orphans):
            node = node_by_dir[directory_id]
            rows.append(
                ScanWarningRecord(
                    scan_id=scan_id,
                    directory_id=directory_id,
                    path=node.path,
                    operation="hierarchy_aggregation",
                    error_type=HIERARCHY_ORPHANED,
                    error_code=None,
                    message="Directory parent relationship could not be resolved for this scan.",
                    occurred_at=now,
                )
            )
        for directory_id in sorted(cycles):
            node = node_by_dir[directory_id]
            rows.append(
                ScanWarningRecord(
                    scan_id=scan_id,
                    directory_id=directory_id,
                    path=node.path,
                    operation="hierarchy_aggregation",
                    error_type=HIERARCHY_CYCLE_DETECTED,
                    error_code=None,
                    message="Directory hierarchy cycle detected; inclusive totals are not reliable.",
                    occurred_at=now,
                )
            )
        session.add_all(rows)

    def _set_aggregation_status(self, session: Session, scan_id: int, status: str) -> None:
        """Update the scan's hierarchy aggregation status."""
        session.execute(
            update(Scan)
            .where(Scan.id == scan_id)
            .values(hierarchy_aggregation_status=status, updated_at=utc_now())
        )
        session.flush()
