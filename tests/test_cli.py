from pathlib import Path

from typer.testing import CliRunner

from windows_folder_sizes_diff.cli import app
from windows_folder_sizes_diff.config import AppSettings
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.models import ScanRequest


def test_cli_commands_inspect_database(
    migrated_database_path: Path, migrated_session_factory, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "windows_folder_sizes_diff.cli.load_settings",
        lambda: AppSettings(
            target_directory=tmp_path,
            growth_threshold_mb=1,
            history_days=1,
            database_path=migrated_database_path,
        ),
    )
    lifecycle = ScanLifecycleService(migrated_session_factory)
    scan = lifecycle.create_scan(
        ScanRequest(target_directory=tmp_path, growth_threshold_mb=1, history_days=1)
    )
    lifecycle.mark_running(scan.id)
    lifecycle.mark_completed(
        scan.id,
        __import__("windows_folder_sizes_diff.scanner.events", fromlist=["ScanCompleted"]).ScanCompleted(
            scan_id=scan.id,
            started_at=utc_now(),
            completed_at=utc_now(),
            cancelled=False,
            folders_scanned=0,
            folders_matched=0,
            warning_count=0,
            results=[],
        ),
        files_examined=0,
    )

    runner = CliRunner()
    db_info = runner.invoke(app, ["db-info"])
    scans = runner.invoke(app, ["scans"])
    scan_show = runner.invoke(app, ["scan-show", str(scan.id)])
    warnings = runner.invoke(app, ["warnings", "--scan-id", str(scan.id)])

    assert db_info.exit_code == 0
    assert str(migrated_database_path) in db_info.output
    assert scans.exit_code == 0
    assert str(scan.id) in scans.output
    assert scan_show.exit_code == 0
    assert "History days" in scan_show.output
    assert warnings.exit_code == 0
    assert f"Warnings for Scan {scan.id}" in warnings.output


def test_cli_missing_scan_id_returns_clear_error(
    migrated_database_path: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        "windows_folder_sizes_diff.cli.load_settings",
        lambda: AppSettings(database_path=migrated_database_path),
    )

    result = CliRunner().invoke(app, ["scan-show", "999"])

    assert result.exit_code != 0
    assert "Scan 999 was not found" in result.output
