"""Focused repositories for Phase 1 persistence."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from windows_folder_sizes_diff.db.models import (
    Directory,
    DirectoryObservation,
    Scan,
    ScanWarningRecord,
    VolumeObservation,
)
from windows_folder_sizes_diff.db.pathing import normalize_windows_path, parent_normalized_path
from windows_folder_sizes_diff.db.time import utc_now
from windows_folder_sizes_diff.scanner.events import ScanWarning
from windows_folder_sizes_diff.scanner.models import FolderObservation


class ScanRepository:
    """Persistence operations for scan rows."""

    def create(self, session: Session, values: dict) -> Scan:
        scan = Scan(**values)
        session.add(scan)
        session.flush()
        return scan

    def get(self, session: Session, scan_id: int) -> Scan | None:
        return session.get(Scan, scan_id)

    def list(
        self,
        session: Session,
        *,
        limit: int = 20,
        status: str | None = None,
        target: str | None = None,
    ) -> list[Scan]:
        statement = select(Scan).order_by(Scan.started_at.desc()).limit(limit)
        if status:
            statement = statement.where(Scan.status == status)
        if target:
            statement = statement.where(
                Scan.normalized_target_path == normalize_windows_path(target)
            )
        return list(session.scalars(statement))

    def update_values(self, session: Session, scan_id: int, values: dict) -> None:
        values["updated_at"] = utc_now()
        session.execute(update(Scan).where(Scan.id == scan_id).values(**values))

    def recover_stale(self, session: Session, completed_at: datetime) -> int:
        result = session.execute(
            update(Scan)
            .where(Scan.status.in_(["pending", "running"]))
            .values(
                status="interrupted",
                completed_at=completed_at,
                failure_message="Recovered stale pending/running scan at startup.",
                updated_at=completed_at,
            )
        )
        return result.rowcount or 0

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(Scan)) or 0)

    def latest(self, session: Session) -> Scan | None:
        statement = select(Scan).order_by(Scan.started_at.desc()).limit(1)
        return session.scalar(statement)

    def latest_completed_comparison(self, session: Session) -> Scan | None:
        statement = (
            select(Scan)
            .where(
                Scan.comparison_status.in_(["completed", "completed_with_warnings"]),
                Scan.baseline_scan_id.is_not(None),
            )
            .order_by(Scan.completed_at.desc(), Scan.started_at.desc())
            .limit(1)
        )
        return session.scalar(statement)

    def has_completed_comparison(self, session: Session) -> bool:
        return self.latest_completed_comparison(session) is not None


class DirectoryRepository:
    """Path-based directory identity operations."""

    def ensure_many(
        self,
        session: Session,
        paths: Iterable[Path],
        *,
        scan_id: int,
    ) -> dict[str, int]:
        unique: dict[str, Path] = {
            normalize_windows_path(path): path for path in paths
        }
        if not unique:
            return {}

        existing_rows = session.execute(
            select(Directory.id, Directory.normalized_path).where(
                Directory.normalized_path.in_(unique.keys())
            )
        ).all()
        existing = {row.normalized_path: row.id for row in existing_rows}

        now = utc_now()
        missing_rows = [
            {
                "normalized_path": normalized,
                "display_path": str(path),
                "parent_normalized_path": parent_normalized_path(path),
                "first_seen_scan_id": scan_id,
                "last_seen_scan_id": scan_id,
                "created_at": now,
                "updated_at": now,
            }
            for normalized, path in unique.items()
            if normalized not in existing
        ]
        if missing_rows:
            session.execute(insert(Directory), missing_rows)
            inserted_rows = session.execute(
                select(Directory.id, Directory.normalized_path).where(
                    Directory.normalized_path.in_([row["normalized_path"] for row in missing_rows])
                )
            ).all()
            existing.update({row.normalized_path: row.id for row in inserted_rows})

        if existing:
            session.execute(
                update(Directory)
                .where(Directory.normalized_path.in_(existing.keys()))
                .values(last_seen_scan_id=scan_id, updated_at=now)
            )

        return existing

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(Directory)) or 0)


class ObservationRepository:
    """Batch insert and query directory observations."""

    def insert_many(
        self,
        session: Session,
        observations: list[FolderObservation],
        *,
        scan_id: int,
        directory_ids: dict[str, int],
    ) -> None:
        if not observations:
            return
        rows = []
        for observation in observations:
            normalized = normalize_windows_path(observation.path)
            rows.append(
                {
                    "scan_id": scan_id,
                    "directory_id": directory_ids[normalized],
                    "matching_bytes": observation.matching_bytes,
                    "direct_file_count": observation.direct_file_count,
                    "matched_file_count": observation.matched_file_count,
                    "direct_logical_bytes": observation.direct_logical_bytes,
                    "measurement_status": observation.measurement_status,
                    "files_examined": observation.files_examined or observation.direct_file_count,
                    "measurement_started_at": observation.measurement_started_at,
                    "measurement_completed_at": observation.measurement_completed_at,
                    "observed_at": observation.scanned_at,
                    "status": observation.status,
                    "warning_count": observation.warning_count,
                }
            )
        session.execute(insert(DirectoryObservation), rows)

    def top_for_scan(self, session: Session, scan_id: int, limit: int = 10) -> list[DirectoryObservation]:
        statement = (
            select(DirectoryObservation)
            .where(DirectoryObservation.scan_id == scan_id)
            .order_by(DirectoryObservation.matching_bytes.desc())
            .limit(limit)
        )
        return list(session.scalars(statement))

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(DirectoryObservation)) or 0)


class WarningRepository:
    """Batch insert and query scan warnings."""

    def insert_many(
        self,
        session: Session,
        warnings: list[ScanWarning],
        *,
        scan_id: int,
        directory_ids: dict[str, int] | None = None,
    ) -> None:
        if not warnings:
            return
        directory_ids = directory_ids or {}
        now = utc_now()
        rows = []
        for warning in warnings:
            normalized = normalize_windows_path(warning.path)
            rows.append(
                {
                    "scan_id": scan_id,
                    "directory_id": directory_ids.get(normalized),
                    "path": str(warning.path),
                    "operation": warning.operation,
                    "error_type": warning.error_type,
                    "error_code": None,
                    "message": warning.message,
                    "occurred_at": now,
                }
            )
        session.execute(insert(ScanWarningRecord), rows)

    def list_for_scan(self, session: Session, scan_id: int, limit: int = 50) -> list[ScanWarningRecord]:
        statement = (
            select(ScanWarningRecord)
            .where(ScanWarningRecord.scan_id == scan_id)
            .order_by(ScanWarningRecord.id)
            .limit(limit)
        )
        return list(session.scalars(statement))

    def count(self, session: Session) -> int:
        return int(session.scalar(select(func.count()).select_from(ScanWarningRecord)) or 0)

    def count_for_scan(self, session: Session, scan_id: int) -> int:
        statement = select(func.count()).select_from(ScanWarningRecord).where(
            ScanWarningRecord.scan_id == scan_id
        )
        return int(session.scalar(statement) or 0)


class VolumeObservationRepository:
    """Pre/post scan volume information operations."""

    def create_before(
        self,
        session: Session,
        *,
        scan_id: int,
        root_path: Path,
        total_bytes: int | None,
        free_bytes_before: int | None,
        captured_before_at: datetime | None,
        status: str,
        error_message: str | None,
    ) -> None:
        session.add(
            VolumeObservation(
                scan_id=scan_id,
                root_path=str(root_path),
                total_bytes=total_bytes,
                free_bytes_before=free_bytes_before,
                free_bytes_after=None,
                captured_before_at=captured_before_at,
                captured_after_at=None,
                status=status,
                error_message=error_message,
            )
        )

    def update_after(
        self,
        session: Session,
        *,
        scan_id: int,
        total_bytes: int | None,
        free_bytes_after: int | None,
        captured_after_at: datetime | None,
        status: str,
        error_message: str | None,
    ) -> None:
        values = {
            "free_bytes_after": free_bytes_after,
            "captured_after_at": captured_after_at,
            "status": status,
            "error_message": error_message,
        }
        if total_bytes is not None:
            values["total_bytes"] = total_bytes
        session.execute(
            update(VolumeObservation)
            .where(VolumeObservation.scan_id == scan_id)
            .values(**values)
        )
