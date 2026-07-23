"""Human-readable scan report writer."""

from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.constants import LOGS_DIR
from windows_folder_sizes_diff.analysis.models import ScanDiffReport
from windows_folder_sizes_diff.scanner.events import ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest


class TextScanReportWriter:
    """Write timestamped scan result reports."""

    def __init__(self, logs_dir: Path = LOGS_DIR) -> None:
        self._logs_dir = logs_dir

    def write(
        self,
        request: ScanRequest,
        completion: ScanCompleted,
        *,
        diff_report: ScanDiffReport | None = None,
    ) -> Path:
        """Write a UTF-8 report and return its path."""

        self._logs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = self._logs_dir / f"scan_{timestamp}.log"

        if diff_report is not None:
            lines = _diff_report_lines(request, completion, diff_report)
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return log_path
        if completion.comparison_status == "baseline_created":
            lines = [
                "Folder Size Difference Report",
                "",
                f"Current scan: {completion.scan_id}",
                "Baseline scan: none",
                f"Target: {request.target_directory}",
                "Measurement: Direct logical size",
                "",
                "Baseline scan created.",
                "No previous comparable scan exists. Run another scan to calculate folder-size changes.",
                "",
                "These values represent logical file-size differences between snapshots.",
                "They do not yet represent physical allocated disk-space differences.",
            ]
            log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return log_path

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


def _diff_report_lines(
    request: ScanRequest,
    completion: ScanCompleted,
    diff_report: ScanDiffReport,
) -> list[str]:
    summary = diff_report.summary
    lines = [
        "Folder Size Difference Report",
        "",
        f"Current scan: {summary.current_scan_id}",
        f"Baseline scan: {summary.previous_scan_id}",
        f"Target: {request.target_directory}",
        "Measurement: Direct logical size",
        f"Database status: {completion.database_status or 'completed'}",
        "",
        "COMPARISON SUMMARY",
        "─" * 60,
        f"Folders compared: {summary.directories_compared}",
        f"Folders grown: {summary.directories_grown}",
        f"Folders reduced: {summary.directories_reduced}",
        f"New folders: {summary.directories_new}",
        f"Removed folders: {summary.directories_removed}",
        f"Incomplete comparisons: {summary.directories_incomplete}",
        "",
        f"Total positive growth: {_format_signed_bytes(summary.total_positive_growth_bytes)}",
        f"Total reductions: {_format_bytes(summary.total_reduction_bytes)}",
        f"Net logical change: {_format_signed_bytes(summary.net_change_bytes)}",
        "",
        "These values represent logical file-size differences between snapshots.",
        "They do not yet represent physical allocated disk-space differences.",
        "",
        "RESULTS",
        "─" * 60,
    ]
    threshold = request.growth_threshold_bytes
    for diff in diff_report.results:
        if diff.delta_bytes is None or abs(diff.delta_bytes) < threshold or diff.state == "unchanged":
            continue
        lines.extend(
            [
                str(diff.path),
                f"    Previous direct size: {_format_bytes(diff.previous_bytes)}",
                f"    Current direct size: {_format_bytes(diff.current_bytes)}",
                f"    Net change: {_format_signed_bytes(diff.delta_bytes)}",
                f"    State: {diff.state}",
                f"    Confidence: {diff.confidence}",
                "",
            ]
        )
    return lines


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{round(value / 1024 / 1024, 2)} MB"


def _format_signed_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    sign = "+" if value > 0 else ""
    return f"{sign}{round(value / 1024 / 1024, 2)} MB"
