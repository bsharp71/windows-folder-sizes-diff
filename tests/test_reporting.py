import re
from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.analysis.models import DirectoryDiff, ScanDiffReport, ScanDiffSummary
from windows_folder_sizes_diff.reporting.text_log import TextScanReportWriter
from windows_folder_sizes_diff.scanner.events import FolderMatched, ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest
from windows_folder_sizes_diff.db.time import utc_now


def test_report_writer_creates_logs_directory_and_writes_report(tmp_path: Path) -> None:
    logs_dir = tmp_path / "logs"
    writer = TextScanReportWriter(logs_dir=logs_dir)
    request = ScanRequest(
        target_directory=tmp_path / "target with spaces",
        growth_threshold_mb=5,
        history_days=2,
    )
    completion = ScanCompleted(
        started_at=datetime(2026, 7, 23, 10, 0, 0),
        completed_at=datetime(2026, 7, 23, 10, 1, 0),
        cancelled=True,
        folders_scanned=3,
        folders_matched=1,
        warning_count=2,
        results=[
            FolderMatched(
                folder=tmp_path / "unicod\u00e9 folder",
                matching_bytes=6 * 1024 * 1024,
                history_days=2,
            )
        ],
    )

    report_path = writer.write(request, completion)
    contents = report_path.read_text(encoding="utf-8")

    assert logs_dir.exists()
    assert re.match(r"scan_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log", report_path.name)
    assert f"Target: {request.target_directory}" in contents
    assert "Threshold: 5 MB" in contents
    assert "History: 2 day(s)" in contents
    assert "Cancelled: True" in contents
    assert "Warnings: 2" in contents
    assert "unicod\u00e9 folder" in contents


def test_diff_report_does_not_write_summed_inclusive_totals(tmp_path: Path) -> None:
    writer = TextScanReportWriter(logs_dir=tmp_path / "logs")
    request = ScanRequest(target_directory=tmp_path, growth_threshold_mb=0, history_days=1)
    completion = ScanCompleted(
        scan_id=2,
        started_at=datetime(2026, 7, 23, 10, 0, 0),
        completed_at=datetime(2026, 7, 23, 10, 1, 0),
        cancelled=False,
        folders_scanned=2,
        folders_matched=1,
        warning_count=0,
        results=[],
    )
    report = ScanDiffReport(
        summary=ScanDiffSummary(
            previous_scan_id=1,
            current_scan_id=2,
            directories_compared=1,
            directories_grown=1,
            directories_reduced=0,
            directories_unchanged=0,
            directories_new=0,
            directories_removed=0,
            directories_incomplete=0,
            total_positive_growth_bytes=100,
            total_reduction_bytes=0,
            net_change_bytes=100,
            inclusive_comparison_available=True,
        ),
        results=[
            DirectoryDiff(
                directory_id=1,
                path=tmp_path,
                previous_direct_bytes=0,
                current_direct_bytes=100,
                direct_delta_bytes=100,
                previous_inclusive_bytes=0,
                current_inclusive_bytes=100,
                inclusive_delta_bytes=100,
                state="grown",
                direct_confidence="high",
                inclusive_confidence="high",
            )
        ],
        generated_at=utc_now(),
    )

    contents = writer.write(request, completion, diff_report=report).read_text(encoding="utf-8")

    assert "Total positive inclusive growth" not in contents
    assert "Total inclusive reduction" not in contents
    assert "Inclusive values overlap across parent and child folders." in contents
