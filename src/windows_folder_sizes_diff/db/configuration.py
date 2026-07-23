"""Scan configuration metadata helpers."""

from __future__ import annotations

import hashlib
import json

from windows_folder_sizes_diff.db.pathing import normalize_windows_path
from windows_folder_sizes_diff.scanner.models import ScanRequest

SCAN_ALGORITHM_VERSION = 1
MEASUREMENT_ALGORITHM_VERSION = 2
PATH_NORMALIZATION_VERSION = 1


def scan_configuration_hash(request: ScanRequest) -> str:
    payload = {
        "measurement_algorithm_version": MEASUREMENT_ALGORITHM_VERSION,
        "measurement_type": "direct_logical_size",
        "follow_symlinks": False,
        "target_path": normalize_windows_path(request.target_directory),
        "path_normalization_version": PATH_NORMALIZATION_VERSION,
        "exclusions": [],
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
