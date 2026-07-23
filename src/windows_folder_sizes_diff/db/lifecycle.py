"""Durable scan lifecycle service."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.db.configuration import scan_configuration_hash
from windows_folder_sizes_diff.db.pathing import normalize_windows_path
from windows_folder_sizes_diff.db.repositories import ScanRepository, VolumeObservationRepository
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import ScanCompleted
from windows_folder_sizes_diff.scanner.models import ScanRequest


class ScanStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


ALLOWED_TRANSITIONS = {
    ScanStatus.PENDING: {ScanStatus.RUNNING, ScanStatus.CANCELLED, ScanStatus.FAILED, ScanStatus.INTERRUPTED},
    ScanStatus.RUNNING: {
        ScanStatus.COMPLETED,
        ScanStatus.COMPLETED_WITH_WARNINGS,
        ScanStatus.CANCELLED,
        ScanStatus.FAILED,
        ScanStatus.INTERRUPTED,
    },
}


@dataclass(frozen=True)
class ScanRecord:
    id: int
    scan_uuid: str
    status: str


class InvalidScanStatusTransition(ValueError):
    """Raised when a scan status transition is invalid."""


class ScanLifecycleService:
    """Own scan status transitions and volume lifecycle metadata."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._scans = ScanRepository()
        self._volumes = VolumeObservationRepository()

    def create_scan(self, request: ScanRequest) -> ScanRecord:
        now = utc_now()
        scan_uuid = str(uuid.uuid4())
        with self._session_factory() as session:
            scan = self._scans.create(
                session,
                {
                    "scan_uuid": scan_uuid,
                    "target_path": str(request.target_directory),
                    "normalized_target_path": normalize_windows_path(request.target_directory),
                    "started_at": now,
                    "completed_at": None,
                    "status": ScanStatus.PENDING.value,
                    "history_days": request.history_days,
                    "growth_threshold_mb": request.growth_threshold_mb,
                    "configuration_hash": scan_configuration_hash(request),
                    "folders_discovered": 0,
                    "folders_analyzed": 0,
                    "folders_matched": 0,
                    "files_examined": 0,
                    "warning_count": 0,
                    "cancel_requested": False,
                    "failure_message": None,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            self._capture_volume_before(session, scan.id, request.target_directory)
            session.commit()
            return ScanRecord(id=scan.id, scan_uuid=scan.scan_uuid, status=scan.status)

    def mark_running(self, scan_id: int) -> None:
        self._transition(scan_id, ScanStatus.RUNNING)

    def update_progress(
        self,
        scan_id: int,
        *,
        folders_discovered: int | None = None,
        folders_analyzed: int | None = None,
        folders_matched: int | None = None,
        files_examined: int | None = None,
        warning_count: int | None = None,
    ) -> None:
        values = {
            key: value
            for key, value in {
                "folders_discovered": folders_discovered,
                "folders_analyzed": folders_analyzed,
                "folders_matched": folders_matched,
                "files_examined": files_examined,
                "warning_count": warning_count,
            }.items()
            if value is not None
        }
        if not values:
            return
        with self._session_factory() as session:
            self._scans.update_values(session, scan_id, values)
            session.commit()

    def mark_completed(self, scan_id: int, completion: ScanCompleted, *, files_examined: int) -> None:
        status = (
            ScanStatus.COMPLETED_WITH_WARNINGS
            if completion.warning_count
            else ScanStatus.COMPLETED
        )
        self._finalize(scan_id, completion, status, files_examined=files_examined)

    def mark_cancelled(self, scan_id: int, completion: ScanCompleted, *, files_examined: int) -> None:
        self._finalize(scan_id, completion, ScanStatus.CANCELLED, files_examined=files_examined)

    def mark_failed(self, scan_id: int, message: str) -> None:
        self._transition(
            scan_id,
            ScanStatus.FAILED,
            extra={"completed_at": utc_now(), "failure_message": message},
        )

    def recover_stale_scans(self) -> int:
        now = utc_now()
        with self._session_factory() as session:
            count = self._scans.recover_stale(session, now)
            session.commit()
            return count

    def _finalize(
        self,
        scan_id: int,
        completion: ScanCompleted,
        status: ScanStatus,
        *,
        files_examined: int,
    ) -> None:
        with self._session_factory() as session:
            self._ensure_transition(session, scan_id, status)
            self._capture_volume_after(session, scan_id)
            self._scans.update_values(
                session,
                scan_id,
                {
                    "status": status.value,
                    "completed_at": completion.completed_at,
                    "folders_analyzed": completion.folders_scanned,
                    "folders_matched": completion.folders_matched,
                    "files_examined": files_examined,
                    "warning_count": completion.warning_count,
                    "cancel_requested": completion.cancelled,
                },
            )
            session.commit()

    def _transition(
        self,
        scan_id: int,
        status: ScanStatus,
        *,
        extra: dict | None = None,
    ) -> None:
        with self._session_factory() as session:
            self._ensure_transition(session, scan_id, status)
            values = {"status": status.value}
            if extra:
                values.update(extra)
            self._scans.update_values(session, scan_id, values)
            session.commit()

    def _ensure_transition(self, session: Session, scan_id: int, target_status: ScanStatus) -> None:
        scan = self._scans.get(session, scan_id)
        if scan is None:
            raise ValueError(f"Scan {scan_id} does not exist.")
        current = ScanStatus(scan.status)
        if current == target_status:
            return
        if target_status not in ALLOWED_TRANSITIONS.get(current, set()):
            raise InvalidScanStatusTransition(
                f"Cannot transition scan {scan_id} from {current.value} to {target_status.value}."
            )

    def _capture_volume_before(self, session: Session, scan_id: int, root_path: Path) -> None:
        total, free, captured_at, status, error_message = _capture_disk_usage(root_path)
        self._volumes.create_before(
            session,
            scan_id=scan_id,
            root_path=root_path,
            total_bytes=total,
            free_bytes_before=free,
            captured_before_at=captured_at,
            status=status,
            error_message=error_message,
        )

    def _capture_volume_after(self, session: Session, scan_id: int) -> None:
        scan = self._scans.get(session, scan_id)
        if scan is None:
            raise ValueError(f"Scan {scan_id} does not exist.")
        total, free, captured_at, status, error_message = _capture_disk_usage(Path(scan.target_path))
        existing_status = scan.volume_observation.status if scan.volume_observation else status
        final_status = _merge_volume_status(existing_status, status)
        self._volumes.update_after(
            session,
            scan_id=scan_id,
            total_bytes=total,
            free_bytes_after=free,
            captured_after_at=captured_at,
            status=final_status,
            error_message=error_message or (scan.volume_observation.error_message if scan.volume_observation else None),
        )


def _capture_disk_usage(root_path: Path) -> tuple[int | None, int | None, datetime | None, str, str | None]:
    try:
        usage = shutil.disk_usage(root_path)
        return usage.total, usage.free, utc_now(), "partial", None
    except OSError as exc:
        return None, None, None, "unavailable", str(exc)


def _merge_volume_status(before_status: str, after_status: str) -> str:
    if before_status == "partial" and after_status == "partial":
        return "complete"
    if before_status == "unavailable" and after_status == "unavailable":
        return "unavailable"
    return "partial"
