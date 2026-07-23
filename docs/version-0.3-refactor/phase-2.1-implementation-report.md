Implemented Phase 2.1.

Changed/added:
- `src/windows_folder_sizes_diff/gui/main_window.py`
- `src/windows_folder_sizes_diff/gui/scan_controller.py`
- `src/windows_folder_sizes_diff/gui/actions.py`
- `src/windows_folder_sizes_diff/gui/menu_bar.py`
- `src/windows_folder_sizes_diff/gui/state.py`
- `src/windows_folder_sizes_diff/gui/dialogs/*`
- `src/windows_folder_sizes_diff/db/repositories.py`
- `tests/test_gui_controller.py`
- `tests/test_gui_phase21.py`

What changed:
- Added native Tk menu bar: File, History, View, Help with only the specified Phase 2.1 commands.
- Added shared `ApplicationActions` so Run Scan, shortcuts, menu commands, exit, refresh, logs, dialogs, and filtering use centralized action paths.
- Replaced the old Show Log button with contextual Cancel Scan.
- Added cooperative cancellation state: visible while scanning, disabled after cancellation request, hidden after terminal scan state.
- Added persisted Recent Scans, Scan Details, and Scan Warnings dialogs.
- Added Measurement Explanation and About dialogs.
- Added comparison filter state with defaults:
  - growth on
  - reductions off
  - new/removed on
  - incomplete on
- Added latest-comparison load and refresh without rescanning.
- Added `Ctrl+R` and `F5`.
- Added repository helpers for latest scan/comparison and warning counts.

Architectural decisions:
- Menu construction is isolated in `ApplicationMenuBar`.
- State is centralized in `ApplicationState` and `ComparisonViewFilters`.
- Dialogs read data passed by actions; they do not open database sessions directly.
- Existing scan orchestration stays in `ScanController`.

Commands/migrations:
- No migration needed.
- Existing databases still need the existing schema at Alembic head.

Tests:
- `uv run pytest`
- Result: `51 passed in 15.56s`

Unmet acceptance criteria:
- None known from code/test verification.

Deferred technical debt:
- GUI tests use a fake menu/root API because the local uv Python Tk runtime reported a missing `ttk/winTheme.tcl` during direct Tk root testing. Functional coverage is present, but a manual visual smoke test on a healthy Tk install is still worthwhile.

Note: git status shows unrelated doc changes/untracked docs (`version-0.3-refactor-spec.md`, `_implementation-checklist.md`, `phase-2.1.md`) that I did not edit as part of this implementation.