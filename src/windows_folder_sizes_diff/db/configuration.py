"""Scan configuration metadata helpers."""

from __future__ import annotations

import hashlib
import json

from windows_folder_sizes_diff.db.pathing import normalize_windows_path
from windows_folder_sizes_diff.scanner.models import ScanRequest

SCAN_ALGORITHM_VERSION = 1


def scan_configuration_hash(request: ScanRequest) -> str:
    payload = {
        "algorithm_version": SCAN_ALGORITHM_VERSION,
        "follow_symlinks": False,
        "growth_threshold_mb": request.growth_threshold_mb,
        "history_days": request.history_days,
        "target_path": normalize_windows_path(request.target_directory),
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
