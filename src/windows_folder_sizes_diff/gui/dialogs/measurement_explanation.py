"""Measurement explanation dialog."""

from __future__ import annotations

from windows_folder_sizes_diff.gui.dialogs._text import ReadOnlyTextDialog

MEASUREMENT_EXPLANATION_TEXT = """Baselines
The first compatible scan creates a baseline.
A later compatible scan is required to calculate changes.

Direct logical size
Phase 2 measures the logical size of files directly contained in each folder.
It does not yet include descendant folders in parent totals.

True differences
Growth is calculated by subtracting the previous direct logical size from the current direct logical size.

Same-size rewrites
Rewriting a file without changing its size produces a zero-byte size difference.

New and removed folders
New folders are compared against zero.
Removed folders are reported as negative changes.

Incomplete comparisons
Folders that could not be measured reliably are shown as incomplete.
The application does not treat inaccessible folders as empty folders.

Current limitations
Phase 2 does not yet provide:
- inclusive parent-folder totals;
- reparse-point deduplication;
- physical allocated size;
- whole-volume reconciliation;
- file-level attribution.
"""


class MeasurementExplanationDialog(ReadOnlyTextDialog):
    """Scrollable explanation of current measurement behavior."""

    def __init__(self, master) -> None:
        super().__init__(
            master,
            title="Measurement Explanation",
            text=MEASUREMENT_EXPLANATION_TEXT,
        )
