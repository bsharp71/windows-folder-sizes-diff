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
    tree: bool = typer.Option(False, "--tree", help="Display as hierarchical tree view"),
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
    if tree:
        _print_tree_report(
            report,
            threshold_bytes=threshold * 1024 * 1024,
            reductions=reductions,
            include_unchanged=include_unchanged,
            include_incomplete=include_incomplete,
            limit=limit,
        )
    else:
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
    tree: bool = typer.Option(False, "--tree", help="Display as hierarchical tree view"),
    direct_only: bool = typer.Option(False, "--direct-only", help="Show only direct growth (no inclusive columns)"),
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
    if tree:
        _print_tree_report(
            diff_report,
            threshold_bytes=threshold * 1024 * 1024,
            reductions=reductions,
            include_unchanged=include_unchanged,
            include_incomplete=include_incomplete,
            limit=limit,
        )
    else:
        _print_diff_report(
            diff_report,
            threshold_bytes=threshold * 1024 * 1024,
            reductions=reductions,
            include_unchanged=include_unchanged,
            include_incomplete=include_incomplete,
            limit=limit,
            direct_only=direct_only,
        )


def _print_diff_report(
    report: ScanDiffReport,
    *,
    threshold_bytes: int,
    reductions: bool,
    include_unchanged: bool,
    include_incomplete: bool,
    limit: int,
    direct_only: bool = False,
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
    summary_table.add_row("Total direct growth", _format_bytes(summary.total_positive_growth_bytes))
    summary_table.add_row("Total direct reduction", _format_bytes(summary.total_reduction_bytes))
    summary_table.add_row("Net direct change", _format_signed_bytes(summary.net_change_bytes))
    if summary.inclusive_comparison_available:
        summary_table.add_row("Inclusive comparison", "Available")
        summary_table.add_row("Partial hierarchies", str(summary.partial_hierarchy_count))
        summary_table.add_row("Hierarchy warnings", str(summary.hierarchy_warning_count))
        summary_table.add_row(
            "Inclusive totals",
            "Not summed; inclusive rows overlap across ancestors and descendants",
        )
    else:
        summary_table.add_row("Inclusive comparison", "Unavailable (baseline predates hierarchy)")
    console.print(summary_table)

    rows = []
    for diff in report.results:
        if diff.direct_delta_bytes is None:
            if include_incomplete:
                rows.append(diff)
            continue
        if diff.state == "unchanged" and not include_unchanged:
            continue
        if reductions:
            if diff.direct_delta_bytes > -threshold_bytes:
                continue
        elif diff.direct_delta_bytes < threshold_bytes:
            continue
        rows.append(diff)
        if len(rows) >= limit:
            break

    if direct_only:
        table = Table(title="Directory Differences (Direct Only)")
        for column in ["Path", "Direct Δ", "Current Direct", "State", "Confidence"]:
            table.add_column(column)
        for diff in rows:
            table.add_row(
                str(diff.path),
                _format_signed_bytes(diff.direct_delta_bytes),
                _format_bytes(diff.current_direct_bytes),
                diff.state,
                diff.direct_confidence,
            )
    else:
        table = Table(title="Directory Differences")
        for column in ["Path", "Direct Δ", "Inclusive Δ", "Current Direct", "State", "Direct Conf", "Incl Conf"]:
            table.add_column(column)
        for diff in rows:
            table.add_row(
                str(diff.path),
                _format_signed_bytes(diff.direct_delta_bytes),
                _format_signed_bytes(diff.inclusive_delta_bytes),
                _format_bytes(diff.current_direct_bytes),
                diff.state,
                diff.direct_confidence,
                diff.inclusive_confidence,
            )
    console.print(table)


def _print_tree_report(
    report: ScanDiffReport,
    *,
    threshold_bytes: int,
    reductions: bool,
    include_unchanged: bool,
    include_incomplete: bool,
    limit: int,
) -> None:
    """Print a hierarchical tree view of the comparison."""
    summary = report.summary
    console.print(f"[bold]Tree View: Scan {summary.previous_scan_id} → {summary.current_scan_id}[/bold]")
    console.print(f"Direct growth: {_format_bytes(summary.total_positive_growth_bytes)}")
    console.print(f"Net direct change: {_format_signed_bytes(summary.net_change_bytes)}")
    if summary.inclusive_comparison_available:
        console.print("[dim]Inclusive values overlap — they are not summed.[/dim]")
    else:
        console.print("[dim]Inclusive comparison unavailable.[/dim]")
    console.print("─" * 60)

    # Build a tree from diffs
    diffs_by_parent: dict[int | None, list] = {}
    for diff in report.results:
        parent = diff.parent_directory_id
        if parent not in diffs_by_parent:
            diffs_by_parent[parent] = []
        diffs_by_parent[parent].append(diff)

    shown = 0

    def _print_node(diff, indent: int = 0):
        nonlocal shown
        if shown >= limit:
            return
        prefix = "  " * indent + ("├─ " if indent > 0 else "")
        direct = _format_signed_bytes(diff.direct_delta_bytes)
        inclusive = _format_signed_bytes(diff.inclusive_delta_bytes) if diff.inclusive_delta_bytes is not None else "N/A"
        console.print(
            f"{prefix}{diff.path}  "
            f"[bold]direct Δ: {direct}[/bold]  "
            f"inclusive Δ: {inclusive}  "
            f"[dim]{diff.state} [{diff.direct_confidence}][/dim]"
        )
        shown += 1
        children = diffs_by_parent.get(diff.directory_id, [])
        children.sort(key=lambda d: abs(d.direct_delta_bytes or 0), reverse=True)
        for child in children:
            if shown >= limit:
                return
            _print_node(child, indent + 1)

    # Print root-level nodes (parent_directory_id is None)
    roots = diffs_by_parent.get(None, [])
    roots.sort(key=lambda d: abs(d.direct_delta_bytes or 0), reverse=True)
    for root_diff in roots:
        if shown >= limit:
            break
        _print_node(root_diff, 0)

    console.print("─" * 60)
    console.print("[dim]Inclusive values overlap across parent and child folders and are not summed.[/dim]")


@app.command("folder-show")
def folder_show(
    path: str = typer.Argument(..., help="Folder path to show detail for"),
    scan_id: int | None = typer.Option(None, help="Current scan ID (default: latest completed comparison)"),
) -> None:
    """Display direct and inclusive history for a folder in the current comparison."""
    _, session_factory = _session_factory()
    from windows_folder_sizes_diff.db.pathing import normalize_windows_path

    with session_factory() as session:
        if scan_id is None:
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
            scan_id = newest.id
            baseline_id = newest.baseline_scan_id
        else:
            scan = session.get(Scan, scan_id)
            if scan is None or scan.baseline_scan_id is None:
                console.print("Scan not found or has no baseline.")
                return
            baseline_id = scan.baseline_scan_id

        report = ScanDiffer().compare(session, previous_scan_id=baseline_id, current_scan_id=scan_id)

    normalized = normalize_windows_path(path)
    for diff in report.results:
        if normalize_windows_path(str(diff.path)) == normalized:
            table = Table(title=f"Folder Detail: {diff.path}")
            table.add_column("Field")
            table.add_column("Value")
            table.add_row("Path", str(diff.path))
            table.add_row("Depth", str(diff.depth))
            table.add_row("State", diff.state)
            table.add_row("Previous direct size", _format_bytes(diff.previous_direct_bytes))
            table.add_row("Current direct size", _format_bytes(diff.current_direct_bytes))
            table.add_row("Direct delta", _format_signed_bytes(diff.direct_delta_bytes))
            table.add_row("Direct confidence", diff.direct_confidence)
            table.add_row("Previous inclusive size", _format_bytes(diff.previous_inclusive_bytes))
            table.add_row("Current inclusive size", _format_bytes(diff.current_inclusive_bytes))
            table.add_row("Inclusive delta", _format_signed_bytes(diff.inclusive_delta_bytes))
            table.add_row("Inclusive confidence", diff.inclusive_confidence)
            table.add_row("Hierarchy status", diff.hierarchy_status or "unknown")
            table.add_row("Warnings", str(diff.warning_count))
            console.print(table)
            return

    console.print(f"Folder not found in comparison: {path}")


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
