"""GUI scan orchestration without filesystem traversal logic."""

from __future__ import annotations

import logging
from pathlib import Path
from queue import Empty, Queue
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.config import AppSettings, save_settings
from windows_folder_sizes_diff.analysis.models import DirectoryDiff
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService, ScanRecord
from windows_folder_sizes_diff.db.persistence import ScanPersistenceCoordinator
from windows_folder_sizes_diff.reporting.text_log import TextScanReportWriter
from windows_folder_sizes_diff.scanner.events import (
    FolderMatched,
    ScanCompleted,
    ScanEvent,
    ScanProgress,
    ScanStarted,
    ScanWarning,
)
from windows_folder_sizes_diff.scanner.folder_scanner import FolderScanner
from windows_folder_sizes_diff.scanner.models import ScanRequest

LOGGER = logging.getLogger(__name__)


class ScanView(Protocol):
    """Minimal view protocol implemented by the CustomTkinter window."""

    def get_target_directory(self) -> str: ...

    def get_threshold_mb(self) -> str: ...

    def get_history_days(self) -> str: ...

    def clear_results(self) -> None: ...

    def append_result(self, folder: Path, megabytes: float, history_days: int) -> None: ...

    def append_diff_result(self, diff: DirectoryDiff) -> None: ...

    def display_diff_report(self, diff_report) -> None: ...

    def set_status(self, message: str) -> None: ...

    def set_running(self, running: bool) -> None: ...

    def set_cancellation_requested(self, requested: bool) -> None: ...

    def set_log_path(self, path: Path | None) -> None: ...

    def schedule_after(self, milliseconds: int, callback) -> None: ...


class ScanController:
    """Coordinate settings, scanner events, reporting, and GUI updates."""

    def __init__(
        self,
        view: ScanView,
        *,
        report_writer: TextScanReportWriter | None = None,
        scanner_factory=FolderScanner,
        session_factory: sessionmaker[Session] | None = None,
        lifecycle_service: ScanLifecycleService | None = None,
        database_path: Path | None = None,
    ) -> None:
        self._view = view
        self._report_writer = report_writer or TextScanReportWriter()
        self._scanner_factory = scanner_factory
        self._session_factory = session_factory
        self._lifecycle_service = lifecycle_service
        self._database_path = database_path
        self._scanner: FolderScanner | None = None
        self._event_queue: Queue[ScanEvent] | None = None
        self._request: ScanRequest | None = None
        self._scan_record: ScanRecord | None = None
        self._persistence: ScanPersistenceCoordinator | None = None
        self._polling = False
        self._cancellation_requested = False

    @property
    def is_running(self) -> bool:
        return self._scanner is not None

    def start_scan(self) -> None:
        if self._scanner is not None:
            return
        try:
            request = self._create_request()
        except (ValueError, ValidationError) as exc:
            self._view.set_status(f"Invalid settings: {exc}")
            return

        settings = AppSettings(
            target_directory=request.target_directory,
            growth_threshold_mb=request.growth_threshold_mb,
            history_days=request.history_days,
            database_path=self._database_path or AppSettings().database_path,
        )
        try:
            save_settings(settings)
        except OSError as exc:
            LOGGER.exception("Failed to save settings")
            self._view.set_status(f"Could not save settings: {exc}")
            return

        self._request = request
        self._event_queue = Queue()
        scan_id = 0
        if self._session_factory is not None and self._lifecycle_service is not None:
            try:
                self._scan_record = self._lifecycle_service.create_scan(request)
                self._lifecycle_service.mark_running(self._scan_record.id)
                self._persistence = ScanPersistenceCoordinator(
                    scan_id=self._scan_record.id,
                    session_factory=self._session_factory,
                    lifecycle_service=self._lifecycle_service,
                )
                scan_id = self._scan_record.id
            except Exception as exc:
                LOGGER.exception("Failed to create durable scan")
                self._view.set_status(f"Could not create database scan record: {exc}")
                return

        self._scanner = self._scanner_factory(
            request=request,
            event_sink=self._event_queue.put,
            scan_id=scan_id,
        )
        self._cancellation_requested = False
        self._view.clear_results()
        self._view.set_log_path(None)
        self._view.set_running(True)
        self._view.set_cancellation_requested(False)
        if self._scan_record is not None:
            self._view.set_status(f"Scan {self._scan_record.id} started.")
        else:
            self._view.set_status("Starting scan...")
        self._polling = True
        self._scanner.start()
        self._view.schedule_after(100, self.process_pending_events)

    def cancel_scan(self) -> None:
        if self._scanner is None:
            return
        if self._cancellation_requested:
            return
        self._cancellation_requested = True
        self._scanner.stop()
        self._view.set_cancellation_requested(True)
        self._view.set_status("Cancelling…")

    def process_pending_events(self) -> None:
        queue = self._event_queue
        if queue is None:
            return

        while True:
            try:
                event = queue.get_nowait()
            except Empty:
                break
            self._persist_event(event)
            self._handle_event(event)

        if self._polling:
            self._view.schedule_after(100, self.process_pending_events)

    def _create_request(self) -> ScanRequest:
        threshold = int(self._view.get_threshold_mb().strip())
        history_days = int(self._view.get_history_days().strip())
        target = self._view.get_target_directory().strip()
        return ScanRequest(
            target_directory=Path(target),
            growth_threshold_mb=threshold,
            history_days=history_days,
        )

    def _handle_event(self, event: ScanEvent) -> None:
        if isinstance(event, ScanStarted):
            self._view.set_status(f"Building folder list... (0 found)  0s")
        elif isinstance(event, ScanProgress):
            self._handle_progress(event)
        elif isinstance(event, FolderMatched):
            return
        elif isinstance(event, ScanWarning):
            LOGGER.warning(
                "%s warning for %s: %s: %s",
                event.operation,
                event.path,
                event.error_type,
                event.message,
            )
        elif isinstance(event, ScanCompleted):
            self._handle_completion(event)

    def _handle_progress(self, event: ScanProgress) -> None:
        if event.phase == "build_folder_list":
            self._view.set_status(
                f"Building folder list... ({event.folders_found} found)  {event.elapsed_seconds}s"
            )
        else:
            total = event.total if event.total is not None else "?"
            self._view.set_status(f"Analyzing {event.current} of {total}  {event.elapsed_seconds}s")

    def _handle_completion(self, event: ScanCompleted) -> None:
        self._polling = False
        self._scanner = None
        self._cancellation_requested = False
        self._view.set_running(False)
        self._view.set_cancellation_requested(False)

        suffix = ""
        if self._request is not None:
            try:
                report_event = self._completion_with_database_metadata(event)
                diff_report = self._persistence.diff_report if self._persistence else None
                self._display_diff_results(diff_report)
                report_path = self._report_writer.write(
                    self._request,
                    report_event,
                    diff_report=diff_report,
                )
                self._view.set_log_path(report_path)
                suffix = f"  Log: {report_path.name}"
                LOGGER.info("Report file created: %s", report_path)
            except OSError as exc:
                LOGGER.exception("Failed to write scan report")
                self._view.set_log_path(None)
                suffix = f"  Report write failed: {exc}"

        warning_suffix = ""
        if event.warning_count:
            warning_suffix = f" Scan completed with {event.warning_count} warning(s)."

        if event.cancelled:
            if self._scan_record is not None:
                self._view.set_status(
                    f"Scan {self._scan_record.id} was cancelled. "
                    f"Partial observations were retained.{warning_suffix}{suffix}"
                )
            else:
                self._view.set_status(f"Scan stopped.{warning_suffix}{suffix}")
        else:
            if self._scan_record is not None:
                comparison_status = self._persistence.comparison_status if self._persistence else None
                if comparison_status == "baseline_created":
                    self._view.set_status(
                        "Baseline scan completed. Run another scan to calculate "
                        f"folder-size changes.{suffix}"
                    )
                elif event.warning_count:
                    self._view.set_status(
                        f"Scan {self._scan_record.id} completed with "
                        f"{event.warning_count} warning(s).{suffix}"
                    )
                else:
                    self._view.set_status(
                        f"Scan {self._scan_record.id} completed and was saved "
                        f"to the database.{suffix}"
                    )
            else:
                self._view.set_status(
                    f"Done. {event.folders_matched} folder(s) found out of "
                    f"{event.folders_scanned} scanned.{warning_suffix}{suffix}"
                )

        self._scan_record = None
        self._persistence = None

    def _persist_event(self, event: ScanEvent) -> None:
        if self._persistence is None:
            return
        try:
            self._persistence.handle_event(event)
        except Exception as exc:
            LOGGER.exception("Failed to persist scan event")
            if self._scan_record is not None and self._lifecycle_service is not None:
                self._lifecycle_service.mark_failed(self._scan_record.id, str(exc))
            self._view.set_status("Scan persistence failed. See the application log.")
            self._persistence = None

    def _completion_with_database_metadata(self, event: ScanCompleted) -> ScanCompleted:
        if self._scan_record is None:
            return event
        status = self._persistence.final_status if self._persistence else None
        return event.model_copy(
            update={
                "scan_id": self._scan_record.id,
                "scan_uuid": self._scan_record.scan_uuid,
                "database_status": status,
                "comparison_status": self._persistence.comparison_status if self._persistence else None,
                "baseline_scan_id": (
                    self._persistence.diff_report.summary.previous_scan_id
                    if self._persistence and self._persistence.diff_report
                    else None
                ),
            }
        )

    def _display_diff_results(self, diff_report) -> None:
        if diff_report is None:
            return
        self._view.display_diff_report(diff_report)
