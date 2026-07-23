"""Shared GUI actions used by buttons, menus, shortcuts, and dialogs."""

from __future__ import annotations

import logging
import os
from importlib import metadata
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.analysis.differ import ScanDiffer
from windows_folder_sizes_diff.analysis.models import DirectoryDiff, ScanDiffReport
from windows_folder_sizes_diff.constants import (
    APPLICATION_LOG_PATH,
    APP_VERSION,
    LOGS_DIR,
)
from windows_folder_sizes_diff.db.engine import resolve_database_path
from windows_folder_sizes_diff.db.models import Scan
from windows_folder_sizes_diff.db.repositories import ScanRepository, WarningRepository
from windows_folder_sizes_diff.gui.dialogs import (
    AboutDialog,
    MeasurementExplanationDialog,
    RecentScansDialog,
    ScanDetailsDialog,
    ScanWarningsDialog,
    ask_yes_no,
    show_error,
    show_info,
)
from windows_folder_sizes_diff.gui.state import ApplicationState, ComparisonViewFilters

LOGGER = logging.getLogger(__name__)


class ActionView(Protocol):
    """Main-window surface required by application actions."""

    _controller: object

    def clear_results(self) -> None: ...

    def append_diff_result(self, diff: DirectoryDiff) -> None: ...

    def set_result_view_mode(self, mode: str) -> None: ...

    def set_status(self, message: str) -> None: ...

    def get_threshold_mb(self) -> str: ...

    def update_command_states(self) -> None: ...

    def after(self, milliseconds: int, callback) -> object: ...

    def destroy(self) -> None: ...


class ApplicationActions:
    """Coordinate user-visible commands without duplicating scan business logic."""

    def __init__(
        self,
        view: ActionView,
        *,
        filters: ComparisonViewFilters,
        state: ApplicationState,
        session_factory: sessionmaker[Session] | None,
        database_path: Path,
    ) -> None:
        self._view = view
        self._filters = filters
        self._state = state
        self._session_factory = session_factory
        self._database_path = database_path
        self._scans = ScanRepository()
        self._warnings = WarningRepository()
        self._selected_scan_id: int | None = None
        self._current_report: ScanDiffReport | None = None
        self._current_scan_id: int | None = None
        self._current_baseline_scan_id: int | None = None

    @property
    def selected_scan_id(self) -> int | None:
        return self._selected_scan_id

    @property
    def current_report(self) -> ScanDiffReport | None:
        return self._current_report

    def run_scan(self) -> None:
        LOGGER.info("menu command invoked: run scan")
        if self._state.scan_active or self._state.cancellation_requested or self._state.shutting_down:
            return
        LOGGER.info("scan started from menu")
        self._view._controller.start_scan()

    def cancel_scan(self) -> None:
        LOGGER.info("menu command invoked: cancel scan")
        if not self._state.scan_active or self._state.cancellation_requested:
            return
        self._state.cancellation_requested = True
        self._view.update_command_states()
        self._view._controller.cancel_scan()

    def open_logs_folder(self) -> None:
        LOGGER.info("menu command invoked: open logs folder")
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            _open_path(LOGS_DIR)
            LOGGER.info("log folder opened: %s", LOGS_DIR)
        except OSError as exc:
            LOGGER.exception("Failed to open logs folder")
            show_error(self._view, "Open Logs Folder", f"Could not open the logs folder:\n{exc}")

    def open_application_log(self) -> None:
        LOGGER.info("menu command invoked: open application log")
        if not APPLICATION_LOG_PATH.exists():
            show_info(self._view, "Open Application Log", "No application log has been created yet.")
            return
        try:
            _open_path(APPLICATION_LOG_PATH)
            LOGGER.info("application log opened: %s", APPLICATION_LOG_PATH)
        except OSError as exc:
            LOGGER.exception("Failed to open application log")
            show_error(
                self._view,
                "Open Application Log",
                f"Could not open the application log:\n{exc}",
            )

    def show_recent_scans(self) -> None:
        LOGGER.info("menu command invoked: recent scans")
        try:
            rows = self._list_recent_scans()
        except Exception as exc:
            LOGGER.exception("Failed to load recent scans")
            show_error(self._view, "Recent Scans", f"Could not load scan history:\n{exc}")
            return
        LOGGER.info("history dialog opened")
        RecentScansDialog(
            self._view,
            rows,
            on_select_scan=self.select_scan,
            on_open_details=self.show_scan_details,
            on_open_warnings=self.show_scan_warnings,
            on_open_comparison=self.show_comparison_for_scan,
        )

    def show_latest_comparison(self) -> None:
        LOGGER.info("menu command invoked: latest comparison")
        try:
            scan = self._latest_completed_comparison()
            if scan is None:
                self._show_no_comparison()
                return
            self._load_comparison(scan)
            LOGGER.info("latest comparison loaded: scan_id=%s", scan.id)
        except Exception as exc:
            LOGGER.exception("Failed to load latest comparison")
            show_error(
                self._view,
                "Latest Comparison",
                f"Could not load the latest comparison:\n{exc}",
            )

    def show_comparison_for_scan(self, scan_id: int) -> None:
        try:
            scan = self._get_scan(scan_id)
            if scan is None or scan.baseline_scan_id is None:
                self._show_no_comparison()
                return
            if scan.comparison_status not in {"completed", "completed_with_warnings"}:
                self._show_no_comparison()
                return
            self._load_comparison(scan)
        except Exception as exc:
            LOGGER.exception("Failed to load comparison for scan %s", scan_id)
            show_error(self._view, "Scan Comparison", f"Could not load the comparison:\n{exc}")

    def show_scan_details(self, scan_id: int | None = None) -> None:
        LOGGER.info("menu command invoked: scan details")
        try:
            scan = self._resolve_scan(scan_id)
            if scan is None:
                show_info(self._view, "Scan Details", "No scans have been recorded yet.")
                return
            self._selected_scan_id = scan.id
            LOGGER.info("scan details opened: scan_id=%s", scan.id)
            ScanDetailsDialog(self._view, scan)
            self.refresh_application_state()
        except Exception as exc:
            LOGGER.exception("Failed to open scan details")
            show_error(self._view, "Scan Details", f"Could not load scan details:\n{exc}")

    def show_scan_warnings(self, scan_id: int | None = None) -> None:
        LOGGER.info("menu command invoked: scan warnings")
        try:
            scan = self._resolve_scan(scan_id)
            if scan is None:
                show_info(self._view, "Scan Warnings", "No scans have been recorded yet.")
                return
            self._selected_scan_id = scan.id
            warnings = self._list_warnings(scan.id)
            LOGGER.info("scan warnings opened: scan_id=%s", scan.id)
            ScanWarningsDialog(self._view, scan_id=scan.id, warnings=warnings)
            self.refresh_application_state()
        except Exception as exc:
            LOGGER.exception("Failed to open scan warnings")
            show_error(self._view, "Scan Warnings", f"Could not load scan warnings:\n{exc}")

    def refresh_current_view(self) -> None:
        LOGGER.info("menu command invoked: refresh")
        LOGGER.info("refresh requested")
        if self._current_scan_id is None:
            self.refresh_application_state()
            self._view.set_status("No comparison is currently displayed.")
            return
        try:
            scan = self._get_scan(self._current_scan_id)
            if scan is None or scan.baseline_scan_id is None:
                show_info(self._view, "Refresh", "The current comparison is no longer available.")
                self._current_report = None
                self._render_filtered_results()
                return
            self._load_comparison(scan)
        except Exception as exc:
            LOGGER.exception("Failed to refresh current view")
            show_error(self._view, "Refresh", f"Could not refresh the current view:\n{exc}")

    def show_measurement_explanation(self) -> None:
        LOGGER.info("menu command invoked: measurement explanation")
        MeasurementExplanationDialog(self._view)

    def show_about(self) -> None:
        LOGGER.info("menu command invoked: about")
        AboutDialog(
            self._view,
            application_name="Folder Growth Scanner",
            version=_application_version(),
            python_requirement=">=3.12",
            schema_revision="0003_phase_3",
            measurement_mode=(
                "Direct logical folder-size snapshots with inclusive hierarchy aggregation"
            ),
            database_path=str(resolve_database_path(self._database_path)),
        )

    def exit_application(self) -> None:
        LOGGER.info("menu command invoked: exit")
        LOGGER.info("exit requested")
        if self._state.shutting_down:
            return
        if self._state.scan_active:
            should_exit = ask_yes_no(
                self._view,
                "Exit",
                "A scan is currently running.\n\nCancel the scan and exit?",
                yes_label="Cancel Scan and Exit",
                no_label="Keep Running",
            )
            if not should_exit:
                LOGGER.info("exit cancelled by user")
                return
            self._state.shutting_down = True
            self.cancel_scan()
            self._wait_for_scan_then_destroy()
            return
        self._state.shutting_down = True
        self._view.destroy()

    def select_scan(self, scan_id: int) -> None:
        self._selected_scan_id = scan_id
        self.refresh_application_state()

    def update_filters(self, filters: ComparisonViewFilters) -> None:
        self._filters.show_growth = filters.show_growth
        self._filters.show_reductions = filters.show_reductions
        self._filters.show_new_removed = filters.show_new_removed
        self._filters.show_incomplete = filters.show_incomplete
        self._filters.view_mode = filters.view_mode
        LOGGER.info("view filter changed")
        self._render_filtered_results()

    def display_comparison_report(self, report: ScanDiffReport) -> None:
        self._current_report = report
        self._current_scan_id = report.summary.current_scan_id
        self._current_baseline_scan_id = report.summary.previous_scan_id
        self._selected_scan_id = report.summary.current_scan_id
        self._render_filtered_results()
        self.refresh_application_state()

    def refresh_application_state(self) -> None:
        try:
            if self._session_factory is None:
                self._state.has_scans = False
                self._state.has_completed_comparison = False
                self._state.current_scan_warning_count = 0
                self._view.update_command_states()
                return
            with self._session_factory() as session:
                self._state.has_scans = self._scans.count(session) > 0
                self._state.has_completed_comparison = self._scans.has_completed_comparison(session)
                selected = self._selected_scan_id or self._current_scan_id
                if selected is None:
                    latest = self._scans.latest(session)
                    selected = latest.id if latest is not None else None
                self._state.current_scan_id = selected
                self._state.current_scan_warning_count = (
                    self._warnings.count_for_scan(session, selected) if selected is not None else 0
                )
        except Exception:
            LOGGER.exception("Failed to refresh application command state")
        finally:
            self._view.update_command_states()

    def _list_recent_scans(self) -> list[Scan]:
        if self._session_factory is None:
            return []
        with self._session_factory() as session:
            return self._scans.list(session, limit=100)

    def _latest_completed_comparison(self) -> Scan | None:
        if self._session_factory is None:
            return None
        with self._session_factory() as session:
            return self._scans.latest_completed_comparison(session)

    def _get_scan(self, scan_id: int) -> Scan | None:
        if self._session_factory is None:
            return None
        with self._session_factory() as session:
            return self._scans.get(session, scan_id)

    def _resolve_scan(self, scan_id: int | None) -> Scan | None:
        if self._session_factory is None:
            return None
        with self._session_factory() as session:
            if scan_id is not None:
                return self._scans.get(session, scan_id)
            if self._selected_scan_id is not None:
                selected = self._scans.get(session, self._selected_scan_id)
                if selected is not None:
                    return selected
            if self._current_scan_id is not None:
                current = self._scans.get(session, self._current_scan_id)
                if current is not None:
                    return current
            return self._scans.latest(session)

    def _list_warnings(self, scan_id: int):
        if self._session_factory is None:
            return []
        with self._session_factory() as session:
            return self._warnings.list_for_scan(session, scan_id=scan_id, limit=500)

    def _load_comparison(self, scan: Scan) -> None:
        if scan.baseline_scan_id is None:
            self._show_no_comparison()
            return
        if self._session_factory is None:
            self._show_no_comparison()
            return
        with self._session_factory() as session:
            report = ScanDiffer().compare(
                session,
                previous_scan_id=scan.baseline_scan_id,
                current_scan_id=scan.id,
            )
        self._current_report = report
        self._current_scan_id = scan.id
        self._current_baseline_scan_id = scan.baseline_scan_id
        self._selected_scan_id = scan.id
        self._render_filtered_results()
        self.refresh_application_state()

    def _render_filtered_results(self) -> None:
        self._view.clear_results()
        if self._current_report is None:
            self._view.update_command_states()
            return
        self._view.set_result_view_mode(self._filters.view_mode)
        rows = filter_diffs(self._current_report.results, self._filters)
        if self._filters.view_mode == "tree":
            rows = tree_order_diffs(rows)
        threshold_bytes = self._threshold_bytes()
        shown = 0
        for diff in rows:
            if _is_below_threshold(diff, threshold_bytes, self._filters.view_mode):
                continue
            self._view.append_diff_result(diff)
            shown += 1
        summary = self._current_report.summary
        mode_label = "folder tree" if self._filters.view_mode == "tree" else "direct growth"
        self._view.set_status(
            f"Comparison {summary.previous_scan_id} -> {summary.current_scan_id}: "
            f"{shown} row(s) shown in {mode_label} view."
        )
        self._view.update_command_states()

    def _threshold_bytes(self) -> int:
        try:
            return int(self._view.get_threshold_mb().strip()) * 1024 * 1024
        except ValueError:
            return 0

    def _show_no_comparison(self) -> None:
        show_info(
            self._view,
            "Latest Comparison",
            "No completed comparison is available.\n\n"
            "The first compatible scan creates a baseline. Run another scan to calculate changes.",
        )

    def _wait_for_scan_then_destroy(self) -> None:
        if not self._state.scan_active:
            self._view.destroy()
            return
        self._view.after(100, self._wait_for_scan_then_destroy)


def filter_diffs(
    diffs: list[DirectoryDiff],
    filters: ComparisonViewFilters,
) -> list[DirectoryDiff]:
    """Return visible comparison rows for the active filter state."""

    rows: list[DirectoryDiff] = []
    for diff in diffs:
        if _matches_direct_filter(diff, filters):
            rows.append(diff)
        elif filters.view_mode == "tree" and _matches_inclusive_tree_filter(diff, filters):
            rows.append(diff)
    return rows


def tree_order_diffs(diffs: list[DirectoryDiff]) -> list[DirectoryDiff]:
    """Return rows in parent-before-child order for the folder tree view."""

    by_id = {diff.directory_id: diff for diff in diffs}
    children: dict[int | None, list[DirectoryDiff]] = {}
    for diff in diffs:
        parent_id = diff.parent_directory_id
        if parent_id not in by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(diff)

    for siblings in children.values():
        siblings.sort(key=lambda item: (item.path.as_posix().casefold(), item.directory_id))

    ordered: list[DirectoryDiff] = []
    stack = list(reversed(children.get(None, [])))
    while stack:
        diff = stack.pop()
        ordered.append(diff)
        stack.extend(reversed(children.get(diff.directory_id, [])))
    return ordered


def _matches_direct_filter(diff: DirectoryDiff, filters: ComparisonViewFilters) -> bool:
    if diff.state == "grown" and filters.show_growth:
        return True
    if diff.state == "reduced" and filters.show_reductions:
        return True
    if diff.state in {"new", "removed"} and filters.show_new_removed:
        return True
    return bool(
        (diff.state in {"incomplete", "not_comparable"} or diff.direct_delta_bytes is None)
        and filters.show_incomplete
    )


def _matches_inclusive_tree_filter(diff: DirectoryDiff, filters: ComparisonViewFilters) -> bool:
    delta = diff.inclusive_delta_bytes
    if delta is None:
        return filters.show_incomplete and diff.inclusive_confidence == "unavailable"
    if delta > 0:
        return filters.show_growth
    if delta < 0:
        return filters.show_reductions
    return False


def _is_below_threshold(diff: DirectoryDiff, threshold_bytes: int, view_mode: str) -> bool:
    if threshold_bytes <= 0:
        return False
    primary_delta = diff.inclusive_delta_bytes if view_mode == "tree" else diff.direct_delta_bytes
    return primary_delta is not None and abs(primary_delta) < threshold_bytes


def _open_path(path: Path) -> None:
    startfile = getattr(os, "startfile", None)
    if startfile is None:
        raise OSError("Opening files is only supported by this desktop build.")
    startfile(path)


def _application_version() -> str:
    try:
        return metadata.version("windows-folder-sizes-diff")
    except metadata.PackageNotFoundError:
        return APP_VERSION
