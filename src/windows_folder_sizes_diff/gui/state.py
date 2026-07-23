"""GUI state models for actions, menus, and result filtering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComparisonViewFilters:
    """User-controlled filters for the current comparison view."""

    show_growth: bool = True
    show_reductions: bool = False
    show_new_removed: bool = True
    show_incomplete: bool = True
    view_mode: str = "direct"  # "direct" or "tree"


@dataclass
class ApplicationState:
    """Centralized command-state snapshot for the main window."""

    scan_active: bool = False
    cancellation_requested: bool = False
    has_scans: bool = False
    has_completed_comparison: bool = False
    current_scan_id: int | None = None
    current_scan_warning_count: int = 0
    shutting_down: bool = False
