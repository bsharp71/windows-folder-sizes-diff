"""Timestamp-based folder scanner."""

from __future__ import annotations

import logging
import os
import stat
import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from windows_folder_sizes_diff.scanner.events import (
    FolderMatched,
    FolderObserved,
    ScanCompleted,
    ScanEvent,
    ScanProgress,
    ScanStarted,
    ScanWarning,
)
from windows_folder_sizes_diff.scanner.models import FolderObservation, ScanRequest

LOGGER = logging.getLogger(__name__)


class FolderScanner:
    """Measure direct logical folder sizes on a worker thread."""

    def __init__(
        self,
        request: ScanRequest,
        event_sink: Callable[[ScanEvent], None],
        scan_id: int = 0,
    ) -> None:
        self._request = request
        self._event_sink = event_sink
        self._scan_id = scan_id
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._warning_count = 0

    def start(self) -> None:
        """Start scanning in the scanner-owned worker thread."""

        LOGGER.info("Starting scan for %s", self._request.target_directory)
        self._thread.start()

    def stop(self) -> None:
        """Request cancellation."""

        LOGGER.info("Scan cancellation requested for %s", self._request.target_directory)
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return self._thread.is_alive()

    def wait(self, timeout: float | None = None) -> None:
        """Wait for the worker thread. Intended for tests and orderly shutdown."""

        self._thread.join(timeout)

    def _emit(self, event: ScanEvent) -> None:
        self._event_sink(event)

    def _emit_warning(self, path: Path, operation: str, exc: BaseException) -> None:
        self._warning_count += 1
        warning = ScanWarning(
            scan_id=self._scan_id,
            path=path,
            operation=operation,
            error_type=type(exc).__name__,
            message=str(exc),
        )
        LOGGER.warning(
            "%s failed for %s: %s: %s",
            operation,
            path,
            warning.error_type,
            warning.message,
        )
        self._emit(warning)

    def _run(self) -> None:
        started_at = datetime.now()
        results: list[FolderMatched] = []
        folders_scanned = 0
        completed = False
        self._emit(
            ScanStarted(
                scan_id=self._scan_id,
                started_at=started_at,
                target_directory=self._request.target_directory,
            )
        )

        try:
            folders = self._discover_folders(started_at)
            folders_scanned, results = self._analyze_folders(folders, started_at)
        except Exception:
            LOGGER.exception("Unexpected scanner failure")
            raise
        finally:
            if not completed:
                completion = ScanCompleted(
                    scan_id=self._scan_id,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    cancelled=self._stop_event.is_set(),
                    folders_scanned=folders_scanned,
                    folders_matched=len(results),
                    warning_count=self._warning_count,
                    results=results,
                )
                LOGGER.info(
                    "Scan completed for %s: cancelled=%s folders_scanned=%s matched=%s warnings=%s",
                    self._request.target_directory,
                    completion.cancelled,
                    completion.folders_scanned,
                    completion.folders_matched,
                    completion.warning_count,
                )
                self._emit(completion)
                completed = True

    def _discover_folders(self, started_at: datetime) -> list[Path]:
        folders: list[Path] = [self._request.target_directory]
        pending: deque[Path] = deque([self._request.target_directory])

        while pending:
            if self._stop_event.is_set():
                break

            current = pending.popleft()
            try:
                entries = os.scandir(current)
                try:
                    for entry in entries:
                        if self._stop_event.is_set():
                            break
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                child = Path(entry.path)
                                pending.append(child)
                                folders.append(child)
                        except (PermissionError, FileNotFoundError, OSError) as exc:
                            self._emit_warning(Path(entry.path), "enumerate_directory", exc)
                finally:
                    close = getattr(entries, "close", None)
                    if close is not None:
                        close()
            except (PermissionError, FileNotFoundError, OSError) as exc:
                self._emit_warning(current, "enumerate_directory", exc)

            self._emit(
                ScanProgress(
                    scan_id=self._scan_id,
                    phase="build_folder_list",
                    current=len(folders),
                    folders_found=len(folders),
                    elapsed_seconds=self._elapsed_seconds(started_at),
                    current_path=current,
                )
            )

        return folders

    def _analyze_folders(
        self,
        folders: list[Path],
        started_at: datetime,
    ) -> tuple[int, list[FolderMatched]]:
        results: list[FolderMatched] = []
        cutoff_timestamp = (datetime.now() - timedelta(days=self._request.history_days)).timestamp()
        total = len(folders)
        folders_scanned = 0

        for index, folder in enumerate(folders, 1):
            if self._stop_event.is_set():
                break

            self._emit(
                ScanProgress(
                    scan_id=self._scan_id,
                    phase="analyze_folders",
                    current=index,
                    total=total,
                    folders_found=total,
                    elapsed_seconds=self._elapsed_seconds(started_at),
                    current_path=folder,
                )
            )

            try:
                observation = self._analyze_folder(folder, cutoff_timestamp)
            except (PermissionError, FileNotFoundError, OSError) as exc:
                folders_scanned += 1
                self._emit_warning(folder, "analyze_folder", exc)
                self._emit(
                    FolderObserved(
                        scan_id=self._scan_id,
                        observation=FolderObservation(
                            path=folder,
                            matching_bytes=0,
                            direct_file_count=0,
                            matched_file_count=0,
                            direct_logical_bytes=None,
                            files_examined=0,
                            measurement_status=_measurement_status_for_error(exc),
                            measurement_started_at=datetime.now(),
                            measurement_completed_at=datetime.now(),
                            scanned_at=datetime.now(),
                            status=_observation_status_for_error(exc),
                            warning_count=1,
                        ),
                    )
                )
                continue

            folders_scanned += 1
            self._emit(FolderObserved(scan_id=self._scan_id, observation=observation))

            if observation.matching_bytes >= self._request.growth_threshold_bytes:
                matched = FolderMatched(
                    scan_id=self._scan_id,
                    folder=folder,
                    matching_bytes=observation.matching_bytes,
                    history_days=self._request.history_days,
                )
                results.append(matched)
                self._emit(matched)

        return folders_scanned, results

    def _analyze_folder(self, folder: Path, cutoff_timestamp: float) -> FolderObservation:
        matching_bytes = 0
        direct_logical_bytes = 0
        direct_file_count = 0
        matched_file_count = 0
        files_examined = 0
        warning_count = 0
        measurement_started_at = datetime.now()

        entries = os.scandir(folder)
        try:
            for entry in entries:
                if self._stop_event.is_set():
                    break

                entry_path = Path(entry.path)
                try:
                    stat_result = entry.stat(follow_symlinks=False)
                except (PermissionError, FileNotFoundError, OSError) as exc:
                    warning_count += 1
                    self._emit_warning(entry_path, "stat_file", exc)
                    continue

                if not stat.S_ISREG(stat_result.st_mode):
                    continue

                files_examined += 1
                direct_file_count += 1
                direct_logical_bytes += stat_result.st_size
                is_recent = max(stat_result.st_mtime, stat_result.st_ctime) > cutoff_timestamp
                if is_recent:
                    matching_bytes += stat_result.st_size
                    matched_file_count += 1
        finally:
            close = getattr(entries, "close", None)
            if close is not None:
                close()

        return FolderObservation(
            path=folder,
            matching_bytes=matching_bytes,
            direct_file_count=direct_file_count,
            matched_file_count=matched_file_count,
            direct_logical_bytes=direct_logical_bytes,
            files_examined=files_examined,
            measurement_status="partial" if warning_count else "complete",
            measurement_started_at=measurement_started_at,
            measurement_completed_at=datetime.now(),
            scanned_at=datetime.now(),
            status="observed_with_warnings" if warning_count else "observed",
            warning_count=warning_count,
        )

    @staticmethod
    def _elapsed_seconds(started_at: datetime) -> int:
        return int((datetime.now() - started_at).total_seconds())


def _observation_status_for_error(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return "inaccessible"
    if isinstance(exc, FileNotFoundError):
        return "disappeared"
    return "enumeration_failed"


def _measurement_status_for_error(exc: BaseException) -> str:
    if isinstance(exc, PermissionError):
        return "inaccessible"
    if isinstance(exc, FileNotFoundError):
        return "disappeared"
    return "failed"
