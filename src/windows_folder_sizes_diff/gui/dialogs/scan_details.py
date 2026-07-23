"""Scan details dialog."""

from __future__ import annotations

from windows_folder_sizes_diff.db.models import Scan
from windows_folder_sizes_diff.gui.dialogs._text import ReadOnlyTextDialog


class ScanDetailsDialog(ReadOnlyTextDialog):
    """Read-only scan metadata dialog."""

    def __init__(self, master, scan: Scan) -> None:
        fields = [
            ("Scan ID", scan.id),
            ("Scan UUID", scan.scan_uuid),
            ("Target path", scan.target_path),
            ("Normalized target path", scan.normalized_target_path),
            ("Started", scan.started_at),
            ("Completed", scan.completed_at),
            ("Status", scan.status),
            ("Baseline scan ID", scan.baseline_scan_id),
            ("Comparison status", scan.comparison_status),
            ("Measurement algorithm version", scan.measurement_algorithm_version),
            ("Configuration hash", scan.configuration_hash),
            ("Folders discovered", scan.folders_discovered),
            ("Folders analyzed", scan.folders_analyzed),
            ("Folders compared", scan.folders_matched),
            ("Folders matched or shown", scan.folders_matched),
            ("Files examined", scan.files_examined),
            ("Warning count", scan.warning_count),
            ("Cancellation requested", scan.cancel_requested),
            ("Failure message", scan.failure_message),
            ("Comparison failure message", scan.comparison_failure_message),
        ]
        text = "\n".join(f"{label}: {_format_value(value)}" for label, value in fields)
        super().__init__(master, title=f"Scan Details {scan.id}", text=text)


def _format_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
