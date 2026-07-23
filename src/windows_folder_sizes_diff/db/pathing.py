"""Path normalization helpers for path-based Phase 1 identity."""

from __future__ import annotations

import os
from pathlib import Path


def normalize_windows_path(path: Path | str) -> str:
    """Normalize a path for Phase 1 path-based identity.

    This deliberately does not resolve reparse-point targets.
    """

    absolute = os.path.abspath(os.fspath(path))
    normalized = os.path.normpath(absolute)
    normalized = os.path.normcase(normalized)
    normalized = normalized.replace("/", "\\").lower()
    drive, tail = os.path.splitdrive(normalized)
    if drive and tail in {"", "\\"}:
        return f"{drive}\\"
    return normalized.rstrip("\\")


def parent_normalized_path(path: Path | str) -> str | None:
    normalized = normalize_windows_path(path)
    parent = normalize_windows_path(Path(normalized).parent)
    if parent == normalized:
        return None
    return parent
