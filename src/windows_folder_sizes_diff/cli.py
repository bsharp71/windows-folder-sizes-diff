"""Typer CLI for Phase 1 database inspection."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import func, select

from windows_folder_sizes_diff.config import load_settings
from windows_folder_sizes_diff.analysis.differ import ScanDiffer
from windows_folder_sizes_diff.analysis.models import ScanDiffReport
from windows_folder_sizes_diff.db.engine import (
    create_database_engine,
    create_session_factory,
    resolve_database_path,
)
from windows_folder_sizes_diff.db.models import (
    Directory,
    DirectoryObservation,
    Scan,
    ScanWarningRecord,
    VolumeObservation,
)
from windows_folder_sizes_diff.db.repositories import ObservationRepository, ScanRepository, WarningRepository
from windows_folder_sizes_diff.db.schema import assert_schema_current

app = typer.Typer(help="Inspect the folder diff scan database.")
console = Console(width=200)


def _session_factory():
    settings = load_settings()
    engine = create_database_engine(settings.database_path)
    assert_schema_current(engine, settings.database_path)
    return settings, create_session_factory(engine)


@app.command("db-info")
def db_info() -> None:
    """Show database path and high-level counts."""

    settings, session_factory = _session_factory()
    database_path = resolve_database_path(settings.database_path)
    with session_factory() as session:
        newest_scan = session.scalar(select(func.max(Scan.started_at)))
        table = Table(title="Database Info")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Path", str(database_path))
        table.add_row("Size", str(database_path.stat().st_size if database_path.exists() else 0))
        table.add_row("Total scans", str(session.scalar(select(func.count()).select_from(Scan)) or 0))
        table.add_row(
            "Total directories",
            str(session.scalar(select(func.count()).select_from(Directory)) or 0),
        )
        table.add_row(
            "Total observations",
            str(session.scalar(select(func.count()).select_from(DirectoryObservation)) or 0),
        )
        table.add_row(
            "Total warnings",
            str(session.scalar(select(func.count()).select_from(ScanWarningRecord)) or 0),
        )
        table.add_row("Newest scan", str(newest_scan) if newest_scan else "none")
    console.print(table)


@app.command("scans")
def scans(
    limit: int = typer.Option(20, min=1),
    status: str | None = typer.Option(None),
    target: str | None = typer.Option(None),
) -> None:
    """List scan history."""

    _, session_factory = _session_factory()
    repository = ScanRepository()
    with session_factory() as session:
        rows = repository.list(session, limit=limit, status=status, target=target)

    table = Table(title="Scans")
    for column in ["ID", "Started", "Completed", "Target", "Status", "Folders", "Matched", "Warnings"]:
        table.add_column(column)
    for scan in rows:
        table.add_row(
            str(scan.id),
            str(scan.started_at),
            str(scan.completed_at or ""),
            scan.target_path,
            scan.status,
            str(scan.folders_analyzed),
            str(scan.folders_matched),
            str(scan.warning_count),
        )
    console.print(table)


@app.command("scan-show")
def scan_show(scan_id: int) -> None:
    """Show metadata and top observations for one scan."""

    _, session_factory = _session_factory()
    observations = ObservationRepository()
    with session_factory() as session:
        scan = session.get(Scan, scan_id)
        if scan is None:
            raise typer.BadParameter(f"Scan {scan_id} was not found.")

        table = Table(title=f"Scan {scan.id}")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("UUID", scan.scan_uuid)
        table.add_row("Target", scan.target_path)
        table.add_row("Status", scan.status)
        table.add_row("Started", str(scan.started_at))
        table.add_row("Completed", str(scan.completed_at or ""))
        table.add_row("History days", str(scan.history_days))
        table.add_row("Threshold MB", str(scan.growth_threshold_mb))
        table.add_row("Measurement algorithm version", str(scan.measurement_algorithm_version))
        table.add_row("Baseline scan ID", str(scan.baseline_scan_id or "none"))
        table.add_row("Comparison status", scan.comparison_status)
        table.add_row("Configuration hash", scan.configuration_hash)
        table.add_row("Folders discovered", str(scan.folders_discovered))
        table.add_row("Folders analyzed", str(scan.folders_analyzed))
        table.add_row("Files examined", str(scan.files_examined))
        table.add_row("Warnings", str(scan.warning_count))
        volume = session.scalar(
            select(VolumeObservation).where(VolumeObservation.scan_id == scan_id)
        )
        if volume is not None:
            table.add_row("Volume status", volume.status)
            table.add_row("Free before", str(volume.free_bytes_before))
            table.add_row("Free after", str(volume.free_bytes_after))
        console.print(table)

        top_rows = observations.top_for_scan(session, scan_id, limit=10)
        top_table = Table(title="Top Matching Observations")
        top_table.add_column("Directory ID")
        top_table.add_column("Matching bytes")
        top_table.add_column("Status")
        for observation in top_rows:
            top_table.add_row(
                str(observation.directory_id),
                str(observation.matching_bytes),
                observation.status,
            )
        console.print(top_table)


@app.command("warnings")
def warnings(
    scan_id: int = typer.Option(...),
    limit: int = typer.Option(50, min=1),
) -> None:
    """List persisted warnings for a scan."""

    _, session_factory = _session_factory()
    repository = WarningRepository()
    with session_factory() as session:
        rows = repository.list_for_scan(session, scan_id=scan_id, limit=limit)

    table = Table(title=f"Warnings for Scan {scan_id}")
    for column in ["ID", "Path", "Operation", "Error", "Message"]:
        table.add_column(column)
    for warning in rows:
        table.add_row(
            str(warning.id),
            warning.path,
            warning.operation,
            warning.error_type,
            warning.message,
        )
    console.print(table)


@app.command("compare")
def compare(
    current_scan_id: int,
    previous_scan_id: int,
    force: bool = typer.Option(False),
    threshold_mb: int | None = typer.Option(None),
    reductions: bool = typer.Option(False),
    include_unchanged: bool = typer.Option(False),
    include_incomplete: bool = typer.Option(False),
    limit: int = typer.Option(20, min=1),
) -> None:
    """Compare two scans and display direct logical-size deltas."""

    settings, session_factory = _session_factory()
    threshold = settings.growth_threshold_mb if threshold_mb is None else threshold_mb
    with session_factory() as session:
        report = ScanDiffer().compare(
            session,
            previous_scan_id=previous_scan_id,
            current_scan_id=current_scan_id,
            force=force,
        )
    _print_diff_report(
        report,
        threshold_bytes=threshold * 1024 * 1024,
        reductions=reductions,
        include_unchanged=include_unchanged,
        include_incomplete=include_incomplete,
        limit=limit,
    )


@app.command("report")
def report(
    reductions: bool = typer.Option(False),
    include_unchanged: bool = typer.Option(False),
    include_incomplete: bool = typer.Option(False),
    limit: int = typer.Option(20, min=1),
    threshold_mb: int | None = typer.Option(None),
) -> None:
    """Display the newest completed comparison report."""

    settings, session_factory = _session_factory()
    threshold = settings.growth_threshold_mb if threshold_mb is None else threshold_mb
    with session_factory() as session:
        newest = session.scalar(
            select(Scan)
            .where(
                Scan.comparison_status.in_(["completed", "completed_with_warnings"]),
                Scan.baseline_scan_id.is_not(None),
            )
            .order_by(Scan.completed_at.desc())
            .limit(1)
        )
        if newest is None or newest.baseline_scan_id is None:
            console.print("No completed comparison is available.")
            return
        diff_report = ScanDiffer().compare(
            session,
            previous_scan_id=newest.baseline_scan_id,
            current_scan_id=newest.id,
        )
    _print_diff_report(
        diff_report,
        threshold_bytes=threshold * 1024 * 1024,
        reductions=reductions,
        include_unchanged=include_unchanged,
        include_incomplete=include_incomplete,
        limit=limit,
    )


def _print_diff_report(
    report: ScanDiffReport,
    *,
    threshold_bytes: int,
    reductions: bool,
    include_unchanged: bool,
    include_incomplete: bool,
    limit: int,
) -> None:
    summary = report.summary
    summary_table = Table(title="Comparison Summary")
    summary_table.add_column("Field")
    summary_table.add_column("Value")
    summary_table.add_row("Current scan", str(summary.current_scan_id))
    summary_table.add_row("Baseline scan", str(summary.previous_scan_id))
    summary_table.add_row("Folders compared", str(summary.directories_compared))
    summary_table.add_row("Folders grown", str(summary.directories_grown))
    summary_table.add_row("Folders reduced", str(summary.directories_reduced))
    summary_table.add_row("New folders", str(summary.directories_new))
    summary_table.add_row("Removed folders", str(summary.directories_removed))
    summary_table.add_row("Incomplete", str(summary.directories_incomplete))
    summary_table.add_row("Total positive growth", _format_bytes(summary.total_positive_growth_bytes))
    summary_table.add_row("Total reductions", _format_bytes(summary.total_reduction_bytes))
    summary_table.add_row("Net logical change", _format_signed_bytes(summary.net_change_bytes))
    console.print(summary_table)

    rows = []
    for diff in report.results:
        if diff.delta_bytes is None:
            if include_incomplete:
                rows.append(diff)
            continue
        if diff.state == "unchanged" and not include_unchanged:
            continue
        if reductions:
            if diff.delta_bytes > -threshold_bytes:
                continue
        elif diff.delta_bytes < threshold_bytes:
            continue
        rows.append(diff)
        if len(rows) >= limit:
            break

    table = Table(title="Directory Differences")
    for column in ["Path", "Previous Size", "Current Size", "Net Change", "State", "Confidence"]:
        table.add_column(column)
    for diff in rows:
        table.add_row(
            str(diff.path),
            _format_bytes(diff.previous_bytes),
            _format_bytes(diff.current_bytes),
            _format_signed_bytes(diff.delta_bytes),
            diff.state,
            diff.confidence,
        )
    console.print(table)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    return f"{round(value / 1024 / 1024, 2)} MB"


def _format_signed_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    sign = "+" if value > 0 else ""
    return f"{sign}{round(value / 1024 / 1024, 2)} MB"


if __name__ == "__main__":
    app()
