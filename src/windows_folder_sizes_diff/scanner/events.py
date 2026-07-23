"""Typed scanner events independent of the GUI."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from windows_folder_sizes_diff.scanner.models import FolderObservation


class ScanStarted(BaseModel):
    scan_id: int = 0
    started_at: datetime
    target_directory: Path


class ScanProgress(BaseModel):
    scan_id: int = 0
    phase: str
    current: int
    total: int | None = None
    folders_found: int = 0
    elapsed_seconds: int = 0
    current_path: Path | None = None


class FolderObserved(BaseModel):
    scan_id: int = 0
    observation: FolderObservation


class FolderMatched(BaseModel):
    scan_id: int = 0
    folder: Path
    matching_bytes: int = Field(ge=0)
    history_days: int = Field(ge=1)

    @property
    def matching_megabytes(self) -> float:
        return round(self.matching_bytes / 1024 / 1024, 2)


class ScanWarning(BaseModel):
    scan_id: int = 0
    path: Path
    operation: str
    error_type: str
    message: str


class ScanCompleted(BaseModel):
    scan_id: int = 0
    scan_uuid: str | None = None
    database_status: str | None = None
    comparison_status: str | None = None
    baseline_scan_id: int | None = None
    started_at: datetime
    completed_at: datetime
    cancelled: bool
    folders_scanned: int
    folders_matched: int
    warning_count: int
    results: list[FolderMatched]


ScanEvent = (
    ScanStarted
    | ScanProgress
    | FolderObserved
    | FolderMatched
    | ScanWarning
    | ScanCompleted
)
