"""Event-driven scan persistence coordinator."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.pathing import normalize_windows_path
from windows_folder_sizes_diff.db.repositories import (
    DirectoryRepository,
    ObservationRepository,
    ScanRepository,
    WarningRepository,
)
from windows_folder_sizes_diff.scanner.events import (
    FolderObserved,
    ScanCompleted,
    ScanEvent,
    ScanProgress,
    ScanWarning,
)
from windows_folder_sizes_diff.scanner.models import FolderObservation


class ScanPersistenceCoordinator:
    """Consume scan events and persist observations, warnings, and lifecycle state."""

    def __init__(
        self,
        *,
        scan_id: int,
        session_factory: sessionmaker[Session],
        lifecycle_service: ScanLifecycleService,
        batch_size: int = 500,
    ) -> None:
        self.scan_id = scan_id
        self._session_factory = session_factory
        self._lifecycle = lifecycle_service
        self._batch_size = batch_size
        self._directories = DirectoryRepository()
        self._observations = ObservationRepository()
        self._warnings = WarningRepository()
        self._scans = ScanRepository()
        self._observation_batch: list[FolderObservation] = []
        self._warning_batch: list[ScanWarning] = []
        self._folders_discovered = 0
        self._files_examined = 0
        self._warnings_seen = 0
        self.final_status: str | None = None

    @property
    def files_examined(self) -> int:
        return self._files_examined

    def handle_event(self, event: ScanEvent) -> None:
        if isinstance(event, ScanProgress):
            self._handle_progress(event)
        elif isinstance(event, FolderObserved):
            self._observation_batch.append(event.observation)
            self._files_examined += event.observation.direct_file_count
            if len(self._observation_batch) >= self._batch_size:
                self.flush_observations()
        elif isinstance(event, ScanWarning):
            self._warnings_seen += 1
            self._warning_batch.append(event)
            if len(self._warning_batch) >= self._batch_size:
                self.flush_warnings()
        elif isinstance(event, ScanCompleted):
            self.flush()
            if event.cancelled:
                self._lifecycle.mark_cancelled(
                    self.scan_id,
                    event,
                    files_examined=self._files_examined,
                )
                self.final_status = "cancelled"
            else:
                self._lifecycle.mark_completed(
                    self.scan_id,
                    event,
                    files_examined=self._files_examined,
                )
                self.final_status = (
                    "completed_with_warnings" if event.warning_count else "completed"
                )

    def flush(self) -> None:
        self.flush_observations()
        self.flush_warnings()

    def flush_observations(self) -> None:
        if not self._observation_batch:
            return
        batch = self._observation_batch
        self._observation_batch = []
        with self._session_factory() as session:
            directory_ids = self._directories.ensure_many(
                session,
                [observation.path for observation in batch],
                scan_id=self.scan_id,
            )
            self._observations.insert_many(
                session,
                batch,
                scan_id=self.scan_id,
                directory_ids=directory_ids,
            )
            self._scans.update_values(
                session,
                self.scan_id,
                {
                    "folders_analyzed": len(batch),
                    "files_examined": self._files_examined,
                },
            )
            session.commit()

    def flush_warnings(self) -> None:
        if not self._warning_batch:
            return
        batch = self._warning_batch
        self._warning_batch = []
        with self._session_factory() as session:
            self._warnings.insert_many(
                session,
                batch,
                scan_id=self.scan_id,
            )
            self._scans.update_values(
                session,
                self.scan_id,
                {"warning_count": self._warnings_seen},
            )
            session.commit()

    def _handle_progress(self, event: ScanProgress) -> None:
        if event.phase == "build_folder_list":
            self._folders_discovered = max(self._folders_discovered, event.folders_found)
            self._lifecycle.update_progress(
                self.scan_id,
                folders_discovered=self._folders_discovered,
                files_examined=self._files_examined,
                warning_count=self._warnings_seen,
            )
