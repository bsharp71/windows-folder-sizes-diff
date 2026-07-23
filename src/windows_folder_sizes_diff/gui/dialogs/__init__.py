"""Dialog components used by the desktop GUI."""

from windows_folder_sizes_diff.gui.dialogs.about import AboutDialog
from windows_folder_sizes_diff.gui.dialogs.measurement_explanation import (
    MeasurementExplanationDialog,
)
from windows_folder_sizes_diff.gui.dialogs.message import ask_yes_no, show_error, show_info
from windows_folder_sizes_diff.gui.dialogs.recent_scans import RecentScansDialog
from windows_folder_sizes_diff.gui.dialogs.scan_details import ScanDetailsDialog
from windows_folder_sizes_diff.gui.dialogs.scan_warnings import ScanWarningsDialog

__all__ = [
    "AboutDialog",
    "MeasurementExplanationDialog",
    "RecentScansDialog",
    "ScanDetailsDialog",
    "ScanWarningsDialog",
    "ask_yes_no",
    "show_error",
    "show_info",
]
