"""Pydantic models for direct logical size comparisons."""

from datetime import datetime
from pathlib import Path

from pydantic import BaseModel


class BaselineSelection(BaseModel):
    current_scan_id: int
    baseline_scan_id: int | None
    status: str
    reason: str


class DirectoryDiff(BaseModel):
    directory_id: int
    path: Path
    parent_directory_id: int | None = None
    depth: int = 0

    previous_direct_bytes: int | None
    current_direct_bytes: int | None
    direct_delta_bytes: int | None

    previous_inclusive_bytes: int | None = None
    current_inclusive_bytes: int | None = None
    inclusive_delta_bytes: int | None = None

    previous_status: str | None = None
    current_status: str | None = None
    state: str
    direct_confidence: str = "unavailable"
    inclusive_confidence: str = "unavailable"
    confidence_reason: str | None = None
    warning_count: int = 0
    hierarchy_status: str | None = None


class ScanDiffSummary(BaseModel):
    previous_scan_id: int
    current_scan_id: int
    directories_compared: int
    directories_grown: int
    directories_reduced: int
    directories_unchanged: int
    directories_new: int
    directories_removed: int
    directories_incomplete: int
    total_positive_growth_bytes: int
    total_reduction_bytes: int
    net_change_bytes: int
    # Hierarchy-aware additions
    partial_hierarchy_count: int = 0
    hierarchy_warning_count: int = 0
    inclusive_comparison_available: bool = False


class ScanDiffReport(BaseModel):
    summary: ScanDiffSummary
    results: list[DirectoryDiff]
    generated_at: datetime
    measurement_type: str = "direct_logical_size"
