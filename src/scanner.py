"""Compatibility wrappers for the pre-package module path."""

from pathlib import Path
from typing import Any

from windows_folder_sizes_diff.config import (
    AppSettings,
    load_settings as _load_settings,
    save_settings as _save_settings,
    settings_to_legacy_dict,
)
from windows_folder_sizes_diff.scanner import FolderScanner, ScanRequest


def load_settings() -> dict[str, Any]:
    return settings_to_legacy_dict(_load_settings())


def save_settings(target_dir: str, threshold_mb: int, history_days: int) -> None:
    _save_settings(
        AppSettings(
            target_directory=Path(target_dir),
            growth_threshold_mb=threshold_mb,
            history_days=history_days,
        )
    )


__all__ = ["FolderScanner", "ScanRequest", "load_settings", "save_settings"]
