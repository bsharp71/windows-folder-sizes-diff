"""Scanner request and domain models."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ScanRequest(BaseModel):
    """Validated inputs for one timestamp-based scan."""

    target_directory: Path
    growth_threshold_mb: int = Field(ge=0)
    history_days: int = Field(ge=1)

    @field_validator("target_directory", mode="before")
    @classmethod
    def normalize_target_directory(cls, value: str | Path) -> Path:
        return Path(value).expanduser()

    @property
    def growth_threshold_bytes(self) -> int:
        return self.growth_threshold_mb * 1024 * 1024


class FolderObservation(BaseModel):
    """Structured per-folder measurement for Phase 1 persistence."""

    path: Path
    matching_bytes: int = Field(ge=0)
    direct_file_count: int = Field(ge=0)
    matched_file_count: int = Field(ge=0)
    scanned_at: datetime
    status: str = "observed"
    warning_count: int = Field(default=0, ge=0)
