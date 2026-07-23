"""Human-readable scan report writer."""

from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.constants import LOGS_DIR
from windows_folder_sizes_diff.scanner.events import ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest


class TextScanReportWriter:
    """Write timestamped scan result reports."""

    def __init__(self, logs_dir: Path = LOGS_DIR) -> None:
        self._logs_dir = logs_dir

    def write(self, request: ScanRequest, completion: ScanCompleted) -> Path:
        """Write a UTF-8 report and return its path."""

        self._logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = self._logs_dir / f"scan_{timestamp}.log"

        lines = [
            f"Scan ID: {completion.scan_id if completion.scan_id else 'not persisted'}",
            f"Scan UUID: {completion.scan_uuid or 'not persisted'}",
            f"Database status: {completion.database_status or 'not persisted'}",
            f"Scan run: {completion.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Completed: {completion.completed_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Final scan status: {completion.database_status or ('cancelled' if completion.cancelled else 'completed')}",
            f"Target: {request.target_directory}",
            f"Threshold: {request.growth_threshold_mb} MB",
            f"History: {request.history_days} day(s)",
            "Metric: Recent file bytes matching the selected history window",
            f"Cancelled: {completion.cancelled}",
            f"Warnings: {completion.warning_count}",
            "─" * 60,
        ]

        if completion.results:
            for result in completion.results:
                lines.append(
                    f"{result.folder}  →  {result.matching_megabytes} MB "
                    f"in last {result.history_days} day(s)"
                )
        else:
            lines.append("No folders matched the configured threshold.")

        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return log_path
