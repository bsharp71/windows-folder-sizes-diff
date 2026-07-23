"""Event-driven scan persistence coordinator."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, sessionmaker

from windows_folder_sizes_diff.analysis.baseline import BaselineSelector
from windows_folder_sizes_diff.analysis.differ import ScanDiffer
from windows_folder_sizes_diff.analysis.hierarchy import HierarchyAggregator
from windows_folder_sizes_diff.analysis.models import ScanDiffReport
from windows_folder_sizes_diff.db.lifecycle import ScanLifecycleService
from windows_folder_sizes_diff.db.pathing import normalize_windows_path
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

LOGGER = logging.getLogger(__name__)


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
        self.comparison_status: str | None = None
        self.diff_report: ScanDiffReport | None = None

    @property
    def files_examined(self) -> int:
        return self._files_examined

    def handle_event(self, event: ScanEvent) -> None:
        if isinstance(event, ScanProgress):
            self._handle_progress(event)
        elif isinstance(event, FolderObserved):
            self._observation_batch.append(event.observation)
            self._files_examined += event.observation.files_examined or event.observation.direct_file_count
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
                self._run_comparison()

    def flush(self) -> None:
        self.flush_observations()
        self.flush_warnings()

    def flush_observations(self) -> None:
        if not self._observation_batch:
            return
        batch = self._observation_batch
        self._observation_batch = []
        with self._session_factory() as session:
            # Build parent and depth maps from observations
            parent_map: dict[str, str | None] = {}
            depth_map: dict[str, int] = {}
            for obs in batch:
                normalized = normalize_windows_path(obs.path)
                parent_map[normalized] = normalize_windows_path(obs.parent_path) if obs.parent_path else None
                depth_map[normalized] = obs.depth

            directory_ids = self._directories.ensure_many(
                session,
                [observation.path for observation in batch],
                scan_id=self.scan_id,
                parent_map=parent_map,
                depth_map=depth_map,
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

    def _run_comparison(self) -> None:
        selector = BaselineSelector()
        differ = ScanDiffer()
        aggregator = HierarchyAggregator()

        # Step 1: Run hierarchy aggregation for the current scan
        hierarchy_ok = True
        try:
            with self._session_factory() as session:
                agg_result = aggregator.aggregate_scan(session, self.scan_id)
                session.commit()
                LOGGER.info(
                    "Hierarchy aggregation for scan %s: %s (complete=%s partial=%s orphaned=%s)",
                    self.scan_id,
                    agg_result.status,
                    agg_result.complete_directories,
                    agg_result.partial_directories,
                    agg_result.orphaned_directories,
                )
        except Exception as exc:
            LOGGER.exception("Hierarchy aggregation failed for scan %s", self.scan_id)
            hierarchy_ok = False
            with self._session_factory() as session:
                self._scans.update_values(
                    session,
                    self.scan_id,
                    {
                        "hierarchy_aggregation_status": "failed",
                        "direct_measurement_status": "completed",
                    },
                )
                session.commit()

        # Step 2: Run comparison
        with self._session_factory() as session:
            selection = selector.find_previous_comparable_scan(session, self.scan_id)
            if selection.baseline_scan_id is None:
                self._scans.update_values(
                    session,
                    self.scan_id,
                    {
                        "baseline_scan_id": None,
                        "comparison_status": "baseline_created",
                        "comparison_failure_message": None,
                        "direct_measurement_status": "completed",
                    },
                )
                session.commit()
                self.comparison_status = "baseline_created"
                return

            self._scans.update_values(
                session,
                self.scan_id,
                {
                    "baseline_scan_id": selection.baseline_scan_id,
                    "comparison_status": "running",
                    "comparison_failure_message": None,
                },
            )
            session.commit()

        try:
            with self._session_factory() as session:
                self.diff_report = differ.compare(
                    session,
                    previous_scan_id=selection.baseline_scan_id,
                    current_scan_id=self.scan_id,
                )
                status = (
                    "completed_with_warnings"
                    if self.diff_report.summary.directories_incomplete
                    else "completed"
                )
                self._scans.update_values(
                    session,
                    self.scan_id,
                    {
                        "baseline_scan_id": selection.baseline_scan_id,
                        "comparison_status": status,
                        "comparison_failure_message": None,
                        "direct_measurement_status": "completed",
                    },
                )
                session.commit()
                self.comparison_status = status
        except Exception as exc:
            with self._session_factory() as session:
                self._scans.update_values(
                    session,
                    self.scan_id,
                    {
                        "baseline_scan_id": selection.baseline_scan_id,
                        "comparison_status": "failed",
                        "comparison_failure_message": str(exc),
                    },
                )
                session.commit()
            self.comparison_status = "failed"
