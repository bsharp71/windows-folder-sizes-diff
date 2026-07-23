Implemented Phase 0 only.

Prerequisite inspection found that Phase 0 was not already present: the repo had flat src/main.py and src/scanner.py, no package layout, no typed events, no event queue controller, and no project tests. Later phase specs are present, but 

I did not implement Phase 1 database work.

Files Added/Changed

Added package modules under src/windows_folder_sizes_diff/:
app.py, config.py, constants.py
scanner/models.py, scanner/events.py, scanner/folder_scanner.py
reporting/text_log.py
gui/main_window.py, gui/scan_controller.py

Added tests:
tests/test_config.py
tests/test_scanner.py
tests/test_reporting.py
tests/test_gui_controller.py

Changed:src/main.py now delegates to the package app entry point.
src/scanner.py is now a compatibility shim.
pyproject.toml adds folder-diff, src-layout packaging, pytest config, and dev/build dependencies.
uv.lock updated.
README.md now documents uv run folder-diff and corrects settings file wording to config.yaml.

Architectural Decisions
Scanner now accepts ScanRequest and emits typed Pydantic ScanEvent objects.
GUI communication now flows through Queue[ScanEvent], polled by ScanController via Tk after.
Scanner emits FolderObserved for every analyzed folder and FolderMatched only for threshold display/reporting.
Config uses a Pydantic AppSettings model while preserving the current PascalCase config.yaml shape.
Text report generation is outside the scanner.
Diagnostic logging writes to logs/application.log.
Existing timestamp/creation-time recent-file semantics are preserved.
Commands / Migrations
No migrations are required.
Dependencies were updated with:uv add --dev pytest pytest-cov
uv add --dev hatchling

Run the app with:uv run folder-diff

Legacy launch still works:uv run python src/main.py

Test Results
uv run pytest
Result: 18 passed in 4.84s
Verified package/script state:folder-diff.EXE exists in .venv\Scripts.

Acceptance Criteria Not Fully Satisfied
None known. I did not manually open the GUI window, but the entry point, package import, controller behavior, scanner behavior, reporting, cancellation, and warnings are covered by tests.
Deferred Technical Debt
No detailed GUI warning view yet; Phase 0 only shows/logs a concise warning summary.
Scanner intentionally remains two-pass and timestamp-based.
No SQLite, SQLAlchemy runtime integration, Alembic migrations, snapshot comparisons, allocated-size logic, or reparse-point resolution were added.

Edited 22 files+1,465-182Review changesUndoReview

pyproject.tomlpyproject.toml+13-0
src/main.pysrc/main.py+2-138
src/scanner.pysrc/scanner.py+29-0
src/windows_folder_sizes_diff/__init__.pysrc/windows_folder_sizes_diff/__init__.py+5-0
src/windows_folder_sizes_diff/app.pysrc/windows_folder_sizes_diff/app.py+40-0
src/windows_folder_sizes_diff/config.pysrc/windows_folder_sizes_diff/config.py+80-0
src/windows_folder_sizes_diff/constants.pysrc/windows_folder_sizes_diff/constants.py+11-0
src/windows_folder_sizes_diff/gui/__init__.pysrc/windows_folder_sizes_diff/gui/__init__.py+6-0
src/windows_folder_sizes_diff/gui/main_window.pysrc/windows_folder_sizes_diff/gui/main_window.py+137-1
src/windows_folder_sizes_diff/gui/scan_controller.pysrc/windows_folder_sizes_diff/gui/scan_controller.py+198-0
src/windows_folder_sizes_diff/reporting/__init__.pysrc/windows_folder_sizes_diff/reporting/__init__.py+5-0
src/windows_folder_sizes_diff/reporting/text_log.pysrc/windows_folder_sizes_diff/reporting/text_log.py+47-2
src/windows_folder_sizes_diff/scanner/__init__.pysrc/windows_folder_sizes_diff/scanner/__init__.py+26-0
src/windows_folder_sizes_diff/scanner/events.pysrc/windows_folder_sizes_diff/scanner/events.py+63-0
src/windows_folder_sizes_diff/scanner/folder_scanner.pysrc/windows_folder_sizes_diff/scanner/folder_scanner.py+272-26
src/windows_folder_sizes_diff/scanner/models.pysrc/windows_folder_sizes_diff/scanner/models.py+33-0
tests/test_config.pytests/test_config.py+81-0
tests/test_gui_controller.pytests/test_gui_controller.py+144-0
tests/test_reporting.pytests/test_reporting.py+44-0
tests/test_scanner.pytests/test_scanner.py+205-5
pyproject.tomlpyproject.toml+16-8
README.mdREADME.md+8-2