"""Direct logical folder-size differ with hierarchy support."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from windows_folder_sizes_diff.analysis.models import DirectoryDiff, ScanDiffReport, ScanDiffSummary
from windows_folder_sizes_diff.db.models import Directory, DirectoryObservation, Scan
from windows_folder_sizes_diff.db.time import utc_now

COMPARABLE_STATUSES = {"complete", "complete_with_warnings"}
HIERARCHY_COMPLETE_STATUSES = {"complete", "partial"}


class ScanDiffer:
    """Compare directory observations from two scans with hierarchy support."""

    def validate_compatible(self, session: Session, previous_scan_id: int, current_scan_id: int) -> bool:
        previous = session.get(Scan, previous_scan_id)
        current = session.get(Scan, current_scan_id)
        if previous is None or current is None:
            return False
        return (
            previous.measurement_algorithm_version == current.measurement_algorithm_version == 2
            and previous.normalized_target_path == current.normalized_target_path
            and previous.configuration_hash == current.configuration_hash
        )

    def compare(
        self,
        session: Session,
        previous_scan_id: int,
        current_scan_id: int,
        *,
        force: bool = False,
    ) -> ScanDiffReport:
        if not force and not self.validate_compatible(session, previous_scan_id, current_scan_id):
            raise ValueError("Scans are not compatible for automatic comparison.")

        previous = _load_observations(session, previous_scan_id)
        current = _load_observations(session, current_scan_id)
        directory_ids = set(previous) | set(current)

        # Check if inclusive comparison is available
        inclusive_available = self._inclusive_comparison_available(
            session, previous_scan_id, current_scan_id
        )

        diffs = [
            _diff_directory(
                directory_id,
                previous.get(directory_id),
                current.get(directory_id),
                force=force,
                inclusive_available=inclusive_available,
            )
            for directory_id in directory_ids
        ]
        summary = _summary(previous_scan_id, current_scan_id, diffs, inclusive_available)
        diffs.sort(
            key=lambda diff: diff.direct_delta_bytes if diff.direct_delta_bytes is not None else -10**30,
            reverse=True,
        )
        return ScanDiffReport(summary=summary, results=diffs, generated_at=utc_now())

    def _inclusive_comparison_available(
        self, session: Session, previous_scan_id: int, current_scan_id: int
    ) -> bool:
        """Check if both scans have hierarchy data for inclusive comparison."""
        previous = session.get(Scan, previous_scan_id)
        current = session.get(Scan, current_scan_id)
        if previous is None or current is None:
            return False
        return (
            previous.hierarchy_algorithm_version >= 1
            and current.hierarchy_algorithm_version >= 1
            and previous.hierarchy_aggregation_status in ("completed", "completed_with_warnings")
            and current.hierarchy_aggregation_status in ("completed", "completed_with_warnings")
        )


def _load_observations(session: Session, scan_id: int) -> dict[int, dict]:
    statement = (
        select(
            DirectoryObservation.directory_id,
            Directory.display_path,
            Directory.parent_directory_id,
            Directory.depth,
            DirectoryObservation.direct_logical_bytes,
            DirectoryObservation.inclusive_logical_bytes,
            DirectoryObservation.measurement_status,
            DirectoryObservation.hierarchy_status,
            DirectoryObservation.warning_count,
        )
        .join(Directory, Directory.id == DirectoryObservation.directory_id)
        .where(DirectoryObservation.scan_id == scan_id)
    )
    return {
        row.directory_id: {
            "directory_id": row.directory_id,
            "path": Path(row.display_path),
            "parent_directory_id": row.parent_directory_id,
            "depth": row.depth,
            "direct_bytes": row.direct_logical_bytes,
            "inclusive_bytes": row.inclusive_logical_bytes,
            "status": row.measurement_status,
            "hierarchy_status": row.hierarchy_status,
            "warning_count": row.warning_count,
        }
        for row in session.execute(statement)
    }


def _diff_directory(
    directory_id: int,
    previous: dict | None,
    current: dict | None,
    *,
    force: bool,
    inclusive_available: bool,
) -> DirectoryDiff:
    path = Path((current or previous)["path"])
    warning_count = int((previous or {}).get("warning_count", 0)) + int((current or {}).get("warning_count", 0))
    previous_status = (previous or {}).get("status")
    current_status = (current or {}).get("status")
    previous_direct = (previous or {}).get("direct_bytes")
    current_direct = (current or {}).get("direct_bytes")
    previous_inclusive = (previous or {}).get("inclusive_bytes")
    current_inclusive = (current or {}).get("inclusive_bytes")
    parent_directory_id = (current or previous).get("parent_directory_id")
    depth = (current or previous).get("depth", 0)
    hierarchy_status = (current or {}).get("hierarchy_status")

    if previous is None:
        if _is_comparable(current_status, current_direct):
            return _complete_diff(
                directory_id, path, 0, current_direct, "new", warning_count, force,
                parent_directory_id=parent_directory_id, depth=depth,
                previous_inclusive=0, current_inclusive=current_inclusive,
                inclusive_available=inclusive_available,
                hierarchy_status=hierarchy_status,
            )
        return _incomplete_diff(
            directory_id, path, None, current_direct, previous_status, current_status, warning_count,
            parent_directory_id=parent_directory_id, depth=depth,
        )
    if current is None:
        if _is_comparable(previous_status, previous_direct):
            return _complete_diff(
                directory_id, path, previous_direct, 0, "removed", warning_count, force,
                parent_directory_id=parent_directory_id, depth=depth,
                previous_inclusive=previous_inclusive, current_inclusive=0,
                inclusive_available=inclusive_available,
                hierarchy_status=hierarchy_status,
            )
        return _incomplete_diff(
            directory_id, path, previous_direct, None, previous_status, current_status, warning_count,
            parent_directory_id=parent_directory_id, depth=depth,
        )
    if not _is_comparable(previous_status, previous_direct) or not _is_comparable(current_status, current_direct):
        return _incomplete_diff(
            directory_id, path, previous_direct, current_direct, previous_status, current_status, warning_count,
            parent_directory_id=parent_directory_id, depth=depth,
        )

    delta = current_direct - previous_direct
    if delta > 0:
        state = "grown"
    elif delta < 0:
        state = "reduced"
    else:
        state = "unchanged"
    return _complete_diff(
        directory_id, path, previous_direct, current_direct, state, warning_count, force,
        parent_directory_id=parent_directory_id, depth=depth,
        previous_inclusive=previous_inclusive, current_inclusive=current_inclusive,
        inclusive_available=inclusive_available,
        hierarchy_status=hierarchy_status,
    )


def _is_comparable(status: str | None, size: int | None) -> bool:
    return status in COMPARABLE_STATUSES and size is not None


def _complete_diff(
    directory_id: int,
    path: Path,
    previous_direct: int,
    current_direct: int,
    state: str,
    warning_count: int,
    force: bool,
    *,
    parent_directory_id: int | None = None,
    depth: int = 0,
    previous_inclusive: int | None = None,
    current_inclusive: int | None = None,
    inclusive_available: bool = False,
    hierarchy_status: str | None = None,
) -> DirectoryDiff:
    direct_confidence = "low" if force else ("medium" if warning_count else "high")
    reason_parts = []
    if force:
        reason_parts.append("Forced comparison")
    if warning_count:
        reason_parts.append("warnings present")
    if not reason_parts:
        reason_parts.append("Complete direct logical measurements")
    reason = ". ".join(reason_parts) + "."

    # Inclusive delta
    inclusive_delta = None
    inclusive_confidence = "unavailable"
    if inclusive_available and previous_inclusive is not None and current_inclusive is not None:
        inclusive_delta = current_inclusive - previous_inclusive
        if hierarchy_status == "complete":
            inclusive_confidence = "high"
        elif hierarchy_status == "partial":
            inclusive_confidence = "low"
        else:
            inclusive_confidence = "low"

    return DirectoryDiff(
        directory_id=directory_id,
        path=path,
        parent_directory_id=parent_directory_id,
        depth=depth,
        previous_direct_bytes=previous_direct,
        current_direct_bytes=current_direct,
        direct_delta_bytes=current_direct - previous_direct,
        previous_inclusive_bytes=previous_inclusive,
        current_inclusive_bytes=current_inclusive,
        inclusive_delta_bytes=inclusive_delta,
        state=state,
        direct_confidence=direct_confidence,
        inclusive_confidence=inclusive_confidence,
        confidence_reason=reason,
        warning_count=warning_count,
        hierarchy_status=hierarchy_status,
    )


def _incomplete_diff(
    directory_id: int,
    path: Path,
    previous_direct: int | None,
    current_direct: int | None,
    previous_status: str | None,
    current_status: str | None,
    warning_count: int,
    *,
    parent_directory_id: int | None = None,
    depth: int = 0,
) -> DirectoryDiff:
    return DirectoryDiff(
        directory_id=directory_id,
        path=path,
        parent_directory_id=parent_directory_id,
        depth=depth,
        previous_direct_bytes=previous_direct,
        current_direct_bytes=current_direct,
        direct_delta_bytes=None,
        previous_status=previous_status,
        current_status=current_status,
        state="incomplete",
        direct_confidence="unavailable",
        inclusive_confidence="unavailable",
        confidence_reason="One or both directory measurements are incomplete.",
        warning_count=warning_count,
    )


def _summary(
    previous_scan_id: int,
    current_scan_id: int,
    diffs: list[DirectoryDiff],
    inclusive_available: bool,
) -> ScanDiffSummary:
    comparable = [diff for diff in diffs if diff.direct_delta_bytes is not None]
    partial_count = sum(1 for diff in diffs if diff.hierarchy_status == "partial")
    warning_count = sum(1 for diff in diffs if diff.hierarchy_status in ("orphaned", "invalid_parent", "cycle_detected"))

    summary = ScanDiffSummary(
        previous_scan_id=previous_scan_id,
        current_scan_id=current_scan_id,
        directories_compared=len(comparable),
        directories_grown=sum(1 for diff in comparable if diff.state == "grown"),
        directories_reduced=sum(1 for diff in comparable if diff.state == "reduced"),
        directories_unchanged=sum(1 for diff in comparable if diff.state == "unchanged"),
        directories_new=sum(1 for diff in comparable if diff.state == "new"),
        directories_removed=sum(1 for diff in comparable if diff.state == "removed"),
        directories_incomplete=sum(1 for diff in diffs if diff.state == "incomplete"),
        total_positive_growth_bytes=sum(diff.direct_delta_bytes for diff in comparable if diff.direct_delta_bytes and diff.direct_delta_bytes > 0),
        total_reduction_bytes=abs(sum(diff.direct_delta_bytes for diff in comparable if diff.direct_delta_bytes and diff.direct_delta_bytes < 0)),
        net_change_bytes=sum(diff.direct_delta_bytes for diff in comparable if diff.direct_delta_bytes is not None),
        partial_hierarchy_count=partial_count,
        hierarchy_warning_count=warning_count,
        inclusive_comparison_available=inclusive_available,
    )

    return summary
