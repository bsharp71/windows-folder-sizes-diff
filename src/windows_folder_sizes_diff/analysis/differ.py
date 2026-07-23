"""Direct logical folder-size differ."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from windows_folder_sizes_diff.analysis.models import DirectoryDiff, ScanDiffReport, ScanDiffSummary
from windows_folder_sizes_diff.db.models import Directory, DirectoryObservation, Scan
from windows_folder_sizes_diff.db.time import utc_now

COMPARABLE_STATUSES = {"complete", "complete_with_warnings"}


class ScanDiffer:
    """Compare directory observations from two scans."""

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
        diffs = [
            _diff_directory(directory_id, previous.get(directory_id), current.get(directory_id), force=force)
            for directory_id in directory_ids
        ]
        summary = _summary(previous_scan_id, current_scan_id, diffs)
        diffs.sort(key=lambda diff: diff.delta_bytes if diff.delta_bytes is not None else -10**30, reverse=True)
        return ScanDiffReport(summary=summary, results=diffs, generated_at=utc_now())


def _load_observations(session: Session, scan_id: int) -> dict[int, dict]:
    statement = (
        select(
            DirectoryObservation.directory_id,
            Directory.display_path,
            DirectoryObservation.direct_logical_bytes,
            DirectoryObservation.measurement_status,
            DirectoryObservation.warning_count,
        )
        .join(Directory, Directory.id == DirectoryObservation.directory_id)
        .where(DirectoryObservation.scan_id == scan_id)
    )
    return {
        row.directory_id: {
            "directory_id": row.directory_id,
            "path": Path(row.display_path),
            "bytes": row.direct_logical_bytes,
            "status": row.measurement_status,
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
) -> DirectoryDiff:
    path = Path((current or previous)["path"])
    warning_count = int((previous or {}).get("warning_count", 0)) + int((current or {}).get("warning_count", 0))
    previous_status = (previous or {}).get("status")
    current_status = (current or {}).get("status")
    previous_bytes = (previous or {}).get("bytes")
    current_bytes = (current or {}).get("bytes")

    if previous is None:
        if _is_comparable(current_status, current_bytes):
            return _complete_diff(directory_id, path, 0, current_bytes, "new", warning_count, force)
        return _incomplete_diff(directory_id, path, None, current_bytes, previous_status, current_status, warning_count)
    if current is None:
        if _is_comparable(previous_status, previous_bytes):
            return _complete_diff(directory_id, path, previous_bytes, 0, "removed", warning_count, force)
        return _incomplete_diff(directory_id, path, previous_bytes, None, previous_status, current_status, warning_count)
    if not _is_comparable(previous_status, previous_bytes) or not _is_comparable(current_status, current_bytes):
        return _incomplete_diff(directory_id, path, previous_bytes, current_bytes, previous_status, current_status, warning_count)

    delta = current_bytes - previous_bytes
    if delta > 0:
        state = "grown"
    elif delta < 0:
        state = "reduced"
    else:
        state = "unchanged"
    return _complete_diff(directory_id, path, previous_bytes, current_bytes, state, warning_count, force)


def _is_comparable(status: str | None, size: int | None) -> bool:
    return status in COMPARABLE_STATUSES and size is not None


def _complete_diff(
    directory_id: int,
    path: Path,
    previous_bytes: int,
    current_bytes: int,
    state: str,
    warning_count: int,
    force: bool,
) -> DirectoryDiff:
    confidence = "low" if force else ("medium" if warning_count else "high")
    reason = "Forced comparison." if force else ("Path-based identity with warnings." if warning_count else "Complete direct logical measurements.")
    return DirectoryDiff(
        directory_id=directory_id,
        path=path,
        previous_bytes=previous_bytes,
        current_bytes=current_bytes,
        delta_bytes=current_bytes - previous_bytes,
        state=state,
        confidence=confidence,
        confidence_reason=reason,
        warning_count=warning_count,
    )


def _incomplete_diff(
    directory_id: int,
    path: Path,
    previous_bytes: int | None,
    current_bytes: int | None,
    previous_status: str | None,
    current_status: str | None,
    warning_count: int,
) -> DirectoryDiff:
    return DirectoryDiff(
        directory_id=directory_id,
        path=path,
        previous_bytes=previous_bytes,
        current_bytes=current_bytes,
        delta_bytes=None,
        previous_status=previous_status,
        current_status=current_status,
        state="incomplete",
        confidence="unavailable",
        confidence_reason="One or both directory measurements are incomplete.",
        warning_count=warning_count,
    )


def _summary(previous_scan_id: int, current_scan_id: int, diffs: list[DirectoryDiff]) -> ScanDiffSummary:
    comparable = [diff for diff in diffs if diff.delta_bytes is not None]
    return ScanDiffSummary(
        previous_scan_id=previous_scan_id,
        current_scan_id=current_scan_id,
        directories_compared=len(comparable),
        directories_grown=sum(1 for diff in comparable if diff.state == "grown"),
        directories_reduced=sum(1 for diff in comparable if diff.state == "reduced"),
        directories_unchanged=sum(1 for diff in comparable if diff.state == "unchanged"),
        directories_new=sum(1 for diff in comparable if diff.state == "new"),
        directories_removed=sum(1 for diff in comparable if diff.state == "removed"),
        directories_incomplete=sum(1 for diff in diffs if diff.state == "incomplete"),
        total_positive_growth_bytes=sum(diff.delta_bytes for diff in comparable if diff.delta_bytes > 0),
        total_reduction_bytes=abs(sum(diff.delta_bytes for diff in comparable if diff.delta_bytes < 0)),
        net_change_bytes=sum(diff.delta_bytes for diff in comparable),
    )
