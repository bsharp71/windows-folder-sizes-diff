"""Measurement explanation dialog."""

from __future__ import annotations

from windows_folder_sizes_diff.gui.dialogs._text import ReadOnlyTextDialog

MEASUREMENT_EXPLANATION_TEXT = """Baselines
The first compatible scan creates a baseline.
A later compatible scan is required to calculate changes.

Direct logical size
Direct size is the logical size of files directly contained in each folder.
It does not include descendant folders.

Inclusive logical size
Inclusive size is the direct size of a folder plus all descendant folder sizes.
Inclusive values overlap across parents and children, so they are shown for navigation and must not be summed.

True differences
Direct growth is calculated by subtracting the previous direct logical size from the current direct logical size.
Inclusive growth is calculated separately when both scans have hierarchy measurements.

Same-size rewrites
Rewriting a file without changing its size produces a zero-byte size difference.

New and removed folders
New folders are compared against zero.
Removed folders are reported as negative changes.

Incomplete comparisons
Folders that could not be measured reliably are shown as incomplete.
The application does not treat inaccessible folders as empty folders.
Inaccessible descendants make ancestor inclusive measurements partial.

Current limitations
Phase 3 does not yet provide:
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
