from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.analysis.models import (
    DirectoryDiff,
    ScanDiffReport,
    ScanDiffSummary,
)
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.models import Scan, ScanWarningRecord
from windows_folder_sizes_diff.db.persistence import ScanPersistenceCoordinator
from windows_folder_sizes_diff.db.repositories import ScanRepository, WarningRepository
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.gui import actions as actions_module
from windows_folder_sizes_diff.gui.actions import ApplicationActions, filter_diffs
from windows_folder_sizes_diff.gui.menu_bar import ApplicationMenuBar
from windows_folder_sizes_diff.gui.state import ApplicationState, ComparisonViewFilters
from windows_folder_sizes_diff.scanner.events import FolderObserved, ScanCompleted, ScanWarning
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest


class DummyActions:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.filters: ComparisonViewFilters | None = None

    def run_scan(self) -> None:
        self.calls.append("run_scan")

    def open_logs_folder(self) -> None:
        self.calls.append("open_logs_folder")

    def exit_application(self) -> None:
        self.calls.append("exit_application")

    def show_recent_scans(self) -> None:
        self.calls.append("show_recent_scans")

    def show_latest_comparison(self) -> None:
        self.calls.append("show_latest_comparison")

    def show_scan_details(self) -> None:
        self.calls.append("show_scan_details")

    def show_scan_warnings(self) -> None:
        self.calls.append("show_scan_warnings")

    def refresh_current_view(self) -> None:
        self.calls.append("refresh_current_view")

    def show_measurement_explanation(self) -> None:
        self.calls.append("show_measurement_explanation")

    def open_application_log(self) -> None:
        self.calls.append("open_application_log")

    def show_about(self) -> None:
        self.calls.append("show_about")

    def update_filters(self, filters: ComparisonViewFilters) -> None:
        self.filters = filters


class FakeController:
    def __init__(self) -> None:
        self.started = 0
        self.cancelled = 0

    def start_scan(self) -> None:
        self.started += 1

    def cancel_scan(self) -> None:
        self.cancelled += 1


class FakeActionView:
    def __init__(self) -> None:
        self._controller = FakeController()
        self.threshold = "0"
        self.results: list[DirectoryDiff] = []
        self.statuses: list[str] = []
        self.destroyed = False
        self.updated = 0

    def clear_results(self) -> None:
        self.results.clear()

    def append_diff_result(self, diff: DirectoryDiff) -> None:
        self.results.append(diff)

    def set_result_view_mode(self, mode: str) -> None:
        self.view_mode = mode

    def set_status(self, message: str) -> None:
        self.statuses.append(message)

    def get_threshold_mb(self) -> str:
        return self.threshold

    def update_command_states(self) -> None:
        self.updated += 1

    def after(self, _milliseconds: int, callback):
        return callback()

    def destroy(self) -> None:
        self.destroyed = True


class FakeBooleanVar:
    def __init__(self, master=None, value=False) -> None:
        self.value = value

    def get(self) -> bool:
        return self.value

    def set(self, value: bool) -> None:
        self.value = value


class FakeStringVar:
    def __init__(self, master=None, value="") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeMenu:
    def __init__(self, master=None, tearoff=False) -> None:
        self.master = master
        self.tearoff = tearoff
        self.entries: list[dict] = []

    def add_command(self, **kwargs) -> None:
        self.entries.append({"type": "command", "state": "normal", **kwargs})

    def add_checkbutton(self, **kwargs) -> None:
        self.entries.append({"type": "checkbutton", "state": "normal", **kwargs})

    def add_radiobutton(self, **kwargs) -> None:
        self.entries.append({"type": "radiobutton", "state": "normal", **kwargs})

    def add_separator(self) -> None:
        self.entries.append({"type": "separator"})

    def add_cascade(self, **kwargs) -> None:
        self.entries.append({"type": "cascade", "state": "normal", **kwargs})

    def index(self, index) -> int | None:
        if index == "end":
            return len(self.entries) - 1 if self.entries else None
        return int(index)

    def type(self, index: int) -> str:
        return self.entries[index]["type"]

    def entrycget(self, index, option: str):
        return self._entry(index).get(option)

    def entryconfigure(self, index, **kwargs) -> None:
        self._entry(index).update(kwargs)

    def _entry(self, index):
        if isinstance(index, str):
            for entry in self.entries:
                if entry.get("label") == index:
                    return entry
            raise KeyError(index)
        return self.entries[index]


class FakeRoot:
    def __init__(self) -> None:
        self.configured = {}
        self.bindings = {}

    def configure(self, **kwargs) -> None:
        self.configured.update(kwargs)

    def bind(self, sequence: str, callback) -> None:
        self.bindings[sequence] = callback


def install_fake_tk(monkeypatch) -> None:
    import windows_folder_sizes_diff.gui.menu_bar as menu_bar_module

    monkeypatch.setattr(menu_bar_module.tk, "Menu", FakeMenu)
    monkeypatch.setattr(menu_bar_module.tk, "BooleanVar", FakeBooleanVar)
    monkeypatch.setattr(menu_bar_module.tk, "StringVar", FakeStringVar)


def menu_labels(menu: FakeMenu) -> list[str]:
    labels = []
    end = menu.index("end")
    if end is None:
        return labels
    for index in range(end + 1):
        if menu.type(index) == "separator":
            continue
        labels.append(menu.entrycget(index, "label"))
    return labels


def make_diff(state: str, delta: int | None) -> DirectoryDiff:
    return DirectoryDiff(
        directory_id=len(state),
        path=Path(f"C:/{state}"),
        previous_direct_bytes=0 if delta is not None else None,
        current_direct_bytes=delta if delta is not None else None,
        direct_delta_bytes=delta,
        state=state,
        direct_confidence="high",
    )


def persist_observation(session_factory, scan_id: int, target: Path, size: int) -> None:
    now = utc_now()
    coordinator = ScanPersistenceCoordinator(
        scan_id=scan_id,
        session_factory=session_factory,
        lifecycle_service=ScanLifecycleService(session_factory),
    )
    coordinator.handle_event(
        FolderObserved(
            scan_id=scan_id,
            observation=FolderObservation(
                path=target,
                matching_bytes=0,
                direct_file_count=1,
                matched_file_count=0,
                direct_logical_bytes=size,
                files_examined=1,
                scanned_at=now,
                measurement_status="complete",
            ),
        )
    )
    coordinator.handle_event(
        ScanCompleted(
            scan_id=scan_id,
            started_at=now,
            completed_at=now,
            cancelled=False,
            folders_scanned=1,
            folders_matched=0,
            warning_count=0,
            results=[],
        )
    )


def test_menu_structure_and_states(monkeypatch) -> None:
    install_fake_tk(monkeypatch)
    root = FakeRoot()
    actions = DummyActions()
    filters = ComparisonViewFilters()
    menu_bar = ApplicationMenuBar(root, actions, filters)

    assert menu_labels(menu_bar.menu_bar) == ["File", "History", "View", "Help"]
    assert menu_labels(menu_bar.menus["File"]) == ["Run Scan", "Open Logs Folder", "Exit"]
    assert "Cancel Scan" not in menu_labels(menu_bar.menus["File"])
    assert menu_labels(menu_bar.menus["History"]) == [
        "Recent Scans…",
        "Latest Comparison",
        "Scan Details…",
        "Scan Warnings…",
    ]
    assert menu_labels(menu_bar.menus["View"]) == [
        "Direct Growth View",
        "Folder Tree View",
        "Show Growth",
        "Show Reductions",
        "Show New and Removed Folders",
        "Show Incomplete Comparisons",
        "Refresh",
    ]
    assert menu_labels(menu_bar.menus["Help"]) == [
        "Measurement Explanation",
        "Open Application Log",
        "About",
    ]

    state = ApplicationState(scan_active=True, has_scans=False)
    menu_bar.update_state(state, has_result_view=False)

    assert menu_bar.menus["File"].entrycget("Run Scan", "state") == "disabled"
    assert menu_bar.menus["History"].entrycget("Recent Scans…", "state") == "disabled"
    assert menu_bar.menus["View"].entrycget("Direct Growth View", "state") == "disabled"
    assert menu_bar.menus["View"].entrycget("Show Growth", "state") == "disabled"

    state.scan_active = False
    state.has_scans = True
    state.has_completed_comparison = True
    state.current_scan_warning_count = 1
    menu_bar.update_state(state, has_result_view=True)

    assert menu_bar.menus["File"].entrycget("Run Scan", "state") == "normal"
    assert menu_bar.menus["History"].entrycget("Latest Comparison", "state") == "normal"
    assert menu_bar.menus["History"].entrycget("Scan Warnings…", "state") == "normal"
    assert menu_bar.menus["View"].entrycget("Folder Tree View", "state") == "normal"
    assert menu_bar.menus["View"].entrycget("Show Growth", "state") == "normal"


def test_menu_shortcuts_call_shared_actions(monkeypatch) -> None:
    install_fake_tk(monkeypatch)
    actions = DummyActions()
    menu_bar = ApplicationMenuBar(FakeRoot(), actions, ComparisonViewFilters())

    assert menu_bar._run_scan_shortcut() == "break"
    assert menu_bar._refresh_shortcut() == "break"
    assert actions.calls == ["run_scan", "refresh_current_view"]


def test_filter_defaults_hide_reductions_and_keep_incomplete() -> None:
    diffs = [
        make_diff("grown", 10),
        make_diff("reduced", -10),
        make_diff("new", 8),
        make_diff("removed", -8),
        make_diff("incomplete", None),
        make_diff("unchanged", 0),
    ]

    assert [diff.state for diff in filter_diffs(diffs, ComparisonViewFilters())] == [
        "grown",
        "new",
        "removed",
        "incomplete",
    ]

    filters = ComparisonViewFilters(
        show_growth=False,
        show_reductions=True,
        show_new_removed=False,
        show_incomplete=False,
    )
    assert [diff.state for diff in filter_diffs(diffs, filters)] == ["reduced"]


def test_tree_view_includes_ancestors_with_inclusive_growth(tmp_path) -> None:
    view = FakeActionView()
    actions = ApplicationActions(
        view,
        filters=ComparisonViewFilters(),
        state=ApplicationState(),
        session_factory=None,
        database_path=tmp_path / "folder_sizes.db",
    )
    root = DirectoryDiff(
        directory_id=1,
        path=Path("C:/data"),
        previous_direct_bytes=0,
        current_direct_bytes=0,
        direct_delta_bytes=0,
        previous_inclusive_bytes=100,
        current_inclusive_bytes=150,
        inclusive_delta_bytes=50,
        state="unchanged",
        direct_confidence="high",
        inclusive_confidence="high",
    )
    child = DirectoryDiff(
        directory_id=2,
        path=Path("C:/data/cache"),
        parent_directory_id=1,
        depth=1,
        previous_direct_bytes=100,
        current_direct_bytes=150,
        direct_delta_bytes=50,
        previous_inclusive_bytes=100,
        current_inclusive_bytes=150,
        inclusive_delta_bytes=50,
        state="grown",
        direct_confidence="high",
        inclusive_confidence="high",
    )
    report = ScanDiffReport(
        summary=ScanDiffSummary(
            previous_scan_id=10,
            current_scan_id=11,
            directories_compared=2,
            directories_grown=1,
            directories_reduced=0,
            directories_unchanged=1,
            directories_new=0,
            directories_removed=0,
            directories_incomplete=0,
            total_positive_growth_bytes=50,
            total_reduction_bytes=0,
            net_change_bytes=50,
            inclusive_comparison_available=True,
        ),
        results=[child, root],
        generated_at=datetime(2026, 7, 23, 12, 0, 0),
    )

    actions.display_comparison_report(report)
    assert [diff.directory_id for diff in view.results] == [2]
    assert view.view_mode == "direct"

    actions.update_filters(ComparisonViewFilters(view_mode="tree"))

    assert [diff.directory_id for diff in view.results] == [1, 2]
    assert view.view_mode == "tree"
    assert view.statuses[-1] == "Comparison 10 -> 11: 2 row(s) shown in folder tree view."


def test_actions_reuse_scan_and_cancel_controller_paths(migrated_session_factory, tmp_path) -> None:
    view = FakeActionView()
    state = ApplicationState()
    actions = ApplicationActions(
        view,
        filters=ComparisonViewFilters(),
        state=state,
        session_factory=migrated_session_factory,
        database_path=tmp_path / "folder_sizes.db",
    )

    actions.run_scan()
    assert view._controller.started == 1

    state.scan_active = True
    actions.run_scan()
    assert view._controller.started == 1

    actions.cancel_scan()
    actions.cancel_scan()
    assert view._controller.cancelled == 1


def test_open_logs_folder_uses_configured_logs_dir(monkeypatch) -> None:
    opened = []
    view = FakeActionView()
    actions = ApplicationActions(
        view,
        filters=ComparisonViewFilters(),
        state=ApplicationState(),
        session_factory=None,
        database_path=Path("data/folder_sizes.db"),
    )
    monkeypatch.setattr(actions_module.os, "startfile", lambda path: opened.append(path), raising=False)

    actions.open_logs_folder()

    assert opened == [actions_module.LOGS_DIR]


def test_missing_application_log_shows_user_message(monkeypatch) -> None:
    messages = []
    view = FakeActionView()
    actions = ApplicationActions(
        view,
        filters=ComparisonViewFilters(),
        state=ApplicationState(),
        session_factory=None,
        database_path=Path("data/folder_sizes.db"),
    )
    monkeypatch.setattr(actions_module, "APPLICATION_LOG_PATH", Path("missing-application.log"))
    monkeypatch.setattr(
        actions_module,
        "show_info",
        lambda _master, title, message: messages.append((title, message)),
    )

    actions.open_application_log()

    assert messages == [("Open Application Log", "No application log has been created yet.")]


def test_repository_history_helpers_order_and_warning_count(migrated_session_factory, tmp_path) -> None:
    lifecycle = ScanLifecycleService(migrated_session_factory)
    request = ScanRequest(target_directory=tmp_path, growth_threshold_mb=0, history_days=1)
    first = lifecycle.create_scan(request)
    second = lifecycle.create_scan(request)
    lifecycle.mark_running(first.id)
    lifecycle.mark_running(second.id)
    persist_observation(migrated_session_factory, first.id, tmp_path, 100)
    persist_observation(migrated_session_factory, second.id, tmp_path, 150)

    now = utc_now()
    with migrated_session_factory() as session:
        session.add(
            ScanWarningRecord(
                scan_id=second.id,
                path=str(tmp_path),
                operation="scan",
                error_type="PermissionError",
                error_code=None,
                message="access denied",
                occurred_at=now,
            )
        )
        session.commit()

    repo = ScanRepository()
    warning_repo = WarningRepository()
    with migrated_session_factory() as session:
        rows = repo.list(session, limit=2)
        latest_comparison = repo.latest_completed_comparison(session)
        warning_count = warning_repo.count_for_scan(session, second.id)

    assert [row.id for row in rows] == [second.id, first.id]
    assert latest_comparison.id == second.id
    assert warning_count == 1


def test_latest_comparison_loads_persisted_results(migrated_session_factory, tmp_path) -> None:
    lifecycle = ScanLifecycleService(migrated_session_factory)
    request = ScanRequest(target_directory=tmp_path, growth_threshold_mb=0, history_days=1)
    first = lifecycle.create_scan(request)
    second = lifecycle.create_scan(request)
    lifecycle.mark_running(first.id)
    lifecycle.mark_running(second.id)
    persist_observation(migrated_session_factory, first.id, tmp_path, 100)
    persist_observation(migrated_session_factory, second.id, tmp_path, 150)

    with migrated_session_factory() as session:
        second_scan = session.get(Scan, second.id)
        assert second_scan.comparison_status == "completed"

    view = FakeActionView()
    actions = ApplicationActions(
        view,
        filters=ComparisonViewFilters(),
        state=ApplicationState(),
        session_factory=migrated_session_factory,
        database_path=tmp_path / "folder_sizes.db",
    )

    actions.show_latest_comparison()

    assert [diff.direct_delta_bytes for diff in view.results] == [50]
    assert (
        view.statuses[-1]
        == f"Comparison {first.id} -> {second.id}: 1 row(s) shown in direct growth view."
    )
