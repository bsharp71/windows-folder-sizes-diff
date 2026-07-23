import re
from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.reporting.text_log import TextScanReportWriter
from windows_folder_sizes_diff.scanner.events import FolderMatched, ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest


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
