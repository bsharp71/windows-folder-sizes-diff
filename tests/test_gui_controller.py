from datetime import datetime
from pathlib import Path

from windows_folder_sizes_diff.gui import scan_controller as scan_controller_module
from windows_folder_sizes_diff.gui.scan_controller import ScanController
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.models import DirectoryObservation, Scan
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import FolderMatched, FolderObserved, ScanCompleted
from windows_folder_sizes_diff.scanner.models import FolderObservation
from sqlalchemy import select


class FakeView:
    def __init__(self, target: Path) -> None:
        self.target = str(target)
        self.threshold = "1"
        self.history_days = "2"
        self.statuses: list[str] = []
        self.results: list[tuple[Path, float, int]] = []
        self.diff_results = []
        self.running: list[bool] = []
        self.cancellation_requested: list[bool] = []
        self.log_path: Path | None = None
        self.scheduled = 0
        self.cleared = False

    def get_target_directory(self) -> str:
        return self.target

    def get_threshold_mb(self) -> str:
        return self.threshold

    def get_history_days(self) -> str:
        return self.history_days

    def clear_results(self) -> None:
        self.cleared = True

    def append_result(self, folder: Path, megabytes: float, history_days: int) -> None:
        self.results.append((folder, megabytes, history_days))

    def append_diff_result(self, diff) -> None:
        self.diff_results.append(diff)

    def display_diff_report(self, diff_report) -> None:
        self.diff_results.extend(diff_report.results)

    def set_status(self, message: str) -> None:
        self.statuses.append(message)

    def set_running(self, running: bool) -> None:
        self.running.append(running)

    def set_cancellation_requested(self, requested: bool) -> None:
        self.cancellation_requested.append(requested)

    def set_log_path(self, path: Path | None) -> None:
        self.log_path = path

    def schedule_after(self, milliseconds: int, callback) -> None:
        self.scheduled += 1


class FakeScanner:
    instances: list["FakeScanner"] = []

    def __init__(self, request, event_sink, scan_id=0) -> None:
        self.request = request
        self.event_sink = event_sink
        self.scan_id = scan_id
        self.stopped = False
        FakeScanner.instances.append(self)

    def start(self) -> None:
        self.event_sink(
            FolderMatched(
                folder=self.request.target_directory,
                matching_bytes=2 * 1024 * 1024,
                history_days=self.request.history_days,
            )
        )

    def stop(self) -> None:
        self.stopped = True


class FakeReportWriter:
    def __init__(self, report_path: Path) -> None:
        self.report_path = report_path
        self.calls = []

    def write(self, request, completion, **kwargs) -> Path:
        self.calls.append((request, completion))
        self.report_path.write_text("report", encoding="utf-8")
        return self.report_path


def test_start_scan_creates_request_and_updates_result(tmp_path: Path, monkeypatch) -> None:
    FakeScanner.instances = []
    view = FakeView(tmp_path)
    monkeypatch.setattr(scan_controller_module, "save_settings", lambda settings: None)
    controller = ScanController(
        view,
        report_writer=FakeReportWriter(tmp_path / "scan.log"),
        scanner_factory=FakeScanner,
    )

    controller.start_scan()
    controller.process_pending_events()

    scanner = FakeScanner.instances[0]
    assert scanner.request.target_directory == tmp_path
    assert scanner.request.growth_threshold_mb == 1
    assert scanner.request.history_days == 2
    assert view.cleared is True
    assert view.results == []


def test_completion_triggers_report_and_idle_state(tmp_path: Path, monkeypatch) -> None:
    FakeScanner.instances = []
    view = FakeView(tmp_path)
    writer = FakeReportWriter(tmp_path / "scan.log")
    monkeypatch.setattr(scan_controller_module, "save_settings", lambda settings: None)
    controller = ScanController(view, report_writer=writer, scanner_factory=FakeScanner)

    controller.start_scan()
    FakeScanner.instances[0].event_sink(
        ScanCompleted(
            started_at=datetime(2026, 7, 23, 10, 0, 0),
            completed_at=datetime(2026, 7, 23, 10, 1, 0),
            cancelled=False,
            folders_scanned=1,
            folders_matched=1,
            warning_count=0,
            results=[],
        )
    )
    controller.process_pending_events()

    assert writer.calls
    assert view.log_path == tmp_path / "scan.log"
    assert view.running[-1] is False
    assert "Done. 1 folder(s) found out of 1 scanned." in view.statuses[-1]


def test_cancellation_delegates_to_scanner(tmp_path: Path, monkeypatch) -> None:
    FakeScanner.instances = []
    view = FakeView(tmp_path)
    monkeypatch.setattr(scan_controller_module, "save_settings", lambda settings: None)
    controller = ScanController(
        view,
        report_writer=FakeReportWriter(tmp_path / "scan.log"),
        scanner_factory=FakeScanner,
    )

    controller.start_scan()
    controller.cancel_scan()

    assert FakeScanner.instances[0].stopped is True
    assert view.cancellation_requested[-1] is True
    assert view.statuses[-1] == "Cancelling…"


def test_controller_persists_scan_events(
    migrated_session_factory, tmp_path: Path, monkeypatch
) -> None:
    FakeScanner.instances = []
    view = FakeView(tmp_path)
    writer = FakeReportWriter(tmp_path / "scan.log")
    monkeypatch.setattr(scan_controller_module, "save_settings", lambda settings: None)
    lifecycle = ScanLifecycleService(migrated_session_factory)
    controller = ScanController(
        view,
        report_writer=writer,
        scanner_factory=FakeScanner,
        session_factory=migrated_session_factory,
        lifecycle_service=lifecycle,
        database_path=tmp_path / "folder_sizes.db",
    )

    controller.start_scan()
    scanner = FakeScanner.instances[0]
    scanner.event_sink(
        FolderObserved(
            scan_id=scanner.scan_id,
            observation=FolderObservation(
                path=tmp_path,
                matching_bytes=0,
                direct_file_count=1,
                matched_file_count=0,
                scanned_at=utc_now(),
            ),
        )
    )
    scanner.event_sink(
        ScanCompleted(
            scan_id=scanner.scan_id,
            started_at=utc_now(),
            completed_at=utc_now(),
            cancelled=False,
            folders_scanned=1,
            folders_matched=0,
            warning_count=0,
            results=[],
        )
    )
    controller.process_pending_events()

    with migrated_session_factory() as session:
        scan = session.get(Scan, scanner.scan_id)
        observations = list(session.scalars(select(DirectoryObservation)))

    assert scanner.scan_id != 0
    assert scan.status == "completed"
    assert len(observations) == 1
    assert writer.calls[0][1].scan_id == scanner.scan_id
