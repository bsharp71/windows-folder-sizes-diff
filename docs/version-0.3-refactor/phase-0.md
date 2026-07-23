# Phase 0 Technical Specification

## Stabilize and Modularize the Existing Application

**Project:** `windows-folder-sizes-diff`
**Phase:** 0 — Application Stabilization
**Language:** Python 3.12+
**Current version:** `0.1.0`

---

# 1. Objective

Refactor the existing application into a clean, testable project structure without changing its current user-visible behavior or reporting logic.

At the end of Phase 0:

* The application must still use modification timestamps to identify recently changed files.
* The existing CustomTkinter GUI must still work.
* Scan results and text logs must retain their current meaning.
* SQLite, SQLAlchemy, and Alembic must not yet be integrated into the runtime.
* Core scanning logic must be separated from GUI code.
* The project must be ready for database persistence in Phase 1.

Phase 0 is a structural stabilization phase, not an accuracy refactor.

---

# 2. Current Behavior to Preserve

The existing scanner:

1. Reads settings from `config.yaml`.
2. Scans a configured target directory.
3. Builds a list of folders.
4. Checks files directly inside each folder.
5. Sums the current size of files whose modification or creation time falls within the selected history period.
6. Reports folders exceeding the configured threshold.
7. Runs on a background thread.
8. Supports cancellation.
9. Sends status, result, and completion callbacks.
10. Writes a timestamped text log.

These behaviors must remain functional throughout Phase 0.

Do not replace the current timestamp-based calculation yet.

---

# 3. Phase 0 Scope

Implement only the following:

* Reorganize the source into modules.
* Introduce validated internal data models.
* Improve traversal efficiency.
* Improve error handling.
* Improve thread communication.
* Add application logging.
* Add automated tests.
* Preserve the current GUI behavior.
* Prepare interfaces that Phase 1 can connect to a database.

Do not implement:

* SQLite persistence.
* SQLAlchemy models.
* Alembic migrations.
* Snapshot comparisons.
* Folder growth deltas.
* Allocated-size calculations.
* File identity tracking.
* Reparse-point target resolution.
* Volume reconciliation.
* Retention policies.
* Scheduled execution.

---

# 4. Required Project Structure

Reorganize the project toward the following structure:

```text
windows-folder-sizes-diff/
├── logs/
├── src/
│   └── windows_folder_sizes_diff/
│       ├── __init__.py
│       ├── app.py
│       ├── config.py
│       ├── constants.py
│       ├── scanner/
│       │   ├── __init__.py
│       │   ├── folder_scanner.py
│       │   ├── models.py
│       │   └── events.py
│       ├── reporting/
│       │   ├── __init__.py
│       │   └── text_log.py
│       └── gui/
│           ├── __init__.py
│           ├── main_window.py
│           └── scan_controller.py
├── tests/
│   ├── test_config.py
│   ├── test_scanner.py
│   ├── test_reporting.py
│   └── fixtures/
├── config.yaml
├── pyproject.toml
└── README.md
```

The exact filenames may vary slightly, but the following boundaries are required:

* Configuration must not live inside the scanner.
* Logging and report generation must not live inside the scanner.
* GUI widgets must not contain filesystem traversal logic.
* The scanner must not directly manipulate GUI widgets.
* Domain models and scan events must not depend on CustomTkinter.

---

# 5. Package Configuration

Update `pyproject.toml` so the project uses the `src` package layout and can be run consistently with `uv`.

Add a GUI entry point or application entry point similar to:

```toml
[project.scripts]
folder-diff = "windows_folder_sizes_diff.app:main"
```

The exact command name may remain project-specific.

Add development dependencies:

```powershell
uv add --dev pytest pytest-cov
```

Do not remove any currently installed runtime dependency.

It is acceptable for SQLAlchemy, Alembic, pywin32, Typer, and Rich to remain installed but unused during this phase.

---

# 6. Configuration Refactor

Move settings handling into `config.py`.

Preserve compatibility with the current `config.yaml` shape:

```yaml
TargetDirectory: 'C:\'
GrowthThresholdMB: 100
HistoryDays: 1
```

Create a Pydantic model:

```python
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class AppSettings(BaseModel):
    target_directory: Path = Path("C:/")
    growth_threshold_mb: int = Field(default=100, ge=0)
    history_days: int = Field(default=1, ge=1)

    @field_validator("target_directory")
    @classmethod
    def normalize_target_directory(cls, value: Path) -> Path:
        return value.expanduser()
```

The implementation may use aliases so the model can read the existing PascalCase keys.

Required behavior:

* Missing configuration file uses defaults.
* Invalid integer values produce a clear error.
* Negative threshold values are rejected.
* `HistoryDays` must be at least 1.
* Settings can still be saved in the existing format.
* File reading and writing must explicitly use UTF-8.
* Paths to the config and logs directories must be centralized in `constants.py`.

Do not introduce a new YAML dependency in Phase 0 unless required. The existing simple parser may be retained behind the new configuration interface.

---

# 7. Scanner Interface

Replace the current loosely structured constructor with a request model.

Example:

```python
from pathlib import Path

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    target_directory: Path
    growth_threshold_mb: int = Field(ge=0)
    history_days: int = Field(ge=1)

    @property
    def growth_threshold_bytes(self) -> int:
        return self.growth_threshold_mb * 1024 * 1024
```

The scanner should expose:

```python
class FolderScanner:
    def __init__(
        self,
        request: ScanRequest,
        event_sink: Callable[[ScanEvent], None],
    ) -> None:
        ...

    def start(self) -> None:
        ...

    def stop(self) -> None:
        ...

    @property
    def is_running(self) -> bool:
        ...
```

The scanner may continue owning its worker thread during Phase 0.

Do not expose GUI-specific callbacks such as `on_status`, `on_result`, and `on_complete` as separate constructor arguments.

Instead, emit typed scan events through one event sink.

---

# 8. Typed Scan Events

Define application-independent event models.

At minimum, support:

```python
class ScanStarted(BaseModel):
    started_at: datetime
    target_directory: Path
```

```python
class ScanProgress(BaseModel):
    phase: str
    current: int
    total: int | None = None
    folders_found: int = 0
    elapsed_seconds: int = 0
    current_path: Path | None = None
```

```python
class FolderMatched(BaseModel):
    folder: Path
    matching_bytes: int
    history_days: int

    @property
    def matching_megabytes(self) -> float:
        return round(self.matching_bytes / 1024 / 1024, 2)
```

```python
class ScanWarning(BaseModel):
    path: Path
    operation: str
    error_type: str
    message: str
```

```python
class ScanCompleted(BaseModel):
    started_at: datetime
    completed_at: datetime
    cancelled: bool
    folders_scanned: int
    folders_matched: int
    warning_count: int
    results: list[FolderMatched]
```

Create a union type:

```python
ScanEvent = (
    ScanStarted
    | ScanProgress
    | FolderMatched
    | ScanWarning
    | ScanCompleted
)
```

Phase 1 will later consume these same events for database persistence.

---

# 9. Thread Communication

The worker thread must not manipulate CustomTkinter widgets directly.

Use a thread-safe queue:

```python
from queue import Queue
```

Recommended flow:

```text
FolderScanner worker thread
        ↓
Queue[ScanEvent]
        ↓
GUI scan controller
        ↓
CustomTkinter widgets
```

The GUI controller should poll the queue using the Tk event loop:

```python
root.after(100, process_pending_events)
```

The scanner’s event sink may simply enqueue events.

This change is required even if the existing callbacks currently appear to work.

---

# 10. Traversal Improvements

Preserve the current two-phase behavior for Phase 0:

1. Build a folder list.
2. Analyze each folder.

Do not redesign the scanner into a single-pass snapshot engine yet.

However, correct the following implementation issues.

## 10.1 Use `deque`

Replace:

```python
queue = [self._target_dir]
current = queue.pop(0)
```

With:

```python
from collections import deque

queue = deque([self._request.target_directory])
current = queue.popleft()
```

## 10.2 Include the target root

The current implementation collects child folders but may not analyze the target root itself.

The folder list should begin with the target directory unless there is a deliberate reason to exclude it.

## 10.3 Stat each file once

Replace repeated calls such as:

```python
e.stat().st_size
e.stat().st_mtime
e.stat().st_ctime
```

With:

```python
stat_result = entry.stat(follow_symlinks=False)
```

Reuse that result.

## 10.4 Do not follow links

Continue using:

```python
follow_symlinks=False
```

Do not recursively follow symbolic links or junction-like entries during Phase 0.

Full Windows reparse-point handling is deferred to a later phase.

## 10.5 Handle disappearing paths

A file or directory may disappear between enumeration and stat.

Catch:

```python
PermissionError
FileNotFoundError
OSError
```

Do not allow one inaccessible path to terminate the scan.

## 10.6 Check cancellation frequently

Check the stop event:

* before dequeuing another directory;
* while enumerating large directories where practical;
* before analyzing each folder;
* while iterating files in a large folder.

Cancellation should stop the scan promptly without corrupting the final event.

---

# 11. Preserve Current Measurement Semantics

The Phase 0 scanner must continue calculating:

```text
Current logical size of direct child files whose modification
or creation timestamp is newer than the selected cutoff.
```

The cutoff is:

```python
datetime.now() - timedelta(days=history_days)
```

For each file:

```python
is_recent = max(
    stat_result.st_mtime,
    stat_result.st_ctime,
) > cutoff_timestamp
```

If `is_recent` is true, add:

```python
stat_result.st_size
```

Do not label this value as true folder growth inside the internal models.

Use neutral internal terminology such as:

* `matching_bytes`
* `recent_file_bytes`
* `recent_activity_bytes`

The existing GUI may temporarily continue displaying its current wording, but new code and comments must not describe this value as a snapshot delta.

---

# 12. Error and Warning Handling

The current code silently ignores permission errors. Replace that behavior with warning events.

Each warning should record:

* path;
* attempted operation;
* exception type;
* exception message.

Example operations:

```text
enumerate_directory
stat_file
analyze_folder
write_log
load_settings
save_settings
```

Warnings should not normally stop the scan.

The completion event must include a warning count.

The GUI should show a concise warning summary at completion, such as:

```text
Scan completed with 18 inaccessible paths.
```

Do not flood the GUI with every warning unless a detail view already exists.

All warnings should be sent to the application log.

---

# 13. Application Logging

Add standard Python logging for diagnostic information.

Use:

```python
import logging
```

Create a centralized logging setup in `app.py` or a dedicated utility module.

Log at least:

* application startup;
* settings load;
* scan start;
* scan cancellation request;
* scan completion;
* unexpected exceptions;
* inaccessible directories;
* report file creation.

Write diagnostic logs separately from scan result reports.

Recommended location:

```text
logs/application.log
```

Use rotating logs if straightforward, for example `RotatingFileHandler`.

Do not replace the existing scan result log files.

---

# 14. Text Report Refactor

Move `write_log` out of `FolderScanner`.

Create a report writer such as:

```python
class TextScanReportWriter:
    def write(
        self,
        request: ScanRequest,
        completion: ScanCompleted,
    ) -> Path:
        ...
```

The report writer should:

* create the logs directory;
* use UTF-8;
* preserve the current timestamped filename style;
* include scan parameters;
* list matched folders;
* include cancellation status;
* include warning count;
* return the written path.

The scanner should produce data.

The report writer should format and persist that data.

The GUI controller or application service should decide when to create the report.

---

# 15. GUI Responsibilities

Move GUI code into `gui/main_window.py`.

Create a controller in `gui/scan_controller.py` responsible for:

* validating current settings;
* creating the `ScanRequest`;
* creating the event queue;
* starting the scanner;
* polling events;
* updating widgets;
* handling cancellation;
* invoking the text report writer after completion.

The GUI must not:

* call `os.scandir()`;
* calculate file sizes;
* inspect timestamps;
* write scan logs directly;
* perform filesystem work on the GUI thread.

The visible behavior should remain substantially unchanged.

---

# 16. Application Entry Point

Create a clear entry point:

```python
def main() -> None:
    configure_logging()
    settings = load_settings()
    window = MainWindow(settings=settings)
    window.run()
```

Guard direct execution:

```python
if __name__ == "__main__":
    main()
```

The project should launch through:

```powershell
uv run folder-diff
```

or an equivalent project script.

Direct module execution may also be supported:

```powershell
uv run python -m windows_folder_sizes_diff.app
```

---

# 17. Testing Requirements

Add `pytest` tests for Phase 0.

Tests must use temporary directories and must not scan the real `C:\` drive.

Use pytest’s `tmp_path` fixture.

## 17.1 Configuration tests

Test:

* defaults load when the config is missing;
* valid settings load correctly;
* invalid threshold is rejected;
* invalid history value is rejected;
* settings save and reload correctly;
* paths containing spaces are preserved.

## 17.2 Scanner tests

Test:

### Recent file above threshold

* Create a recent file.
* Run the scanner against the temporary root.
* Verify a `FolderMatched` event is emitted.

### Old file excluded

* Create a file.
* Set its timestamps outside the history window.
* Verify its size is not included.

### Modified same-size file

For Phase 0, verify that it is still included according to current semantics.

This test documents the known behavior that Phase 2 will replace.

### Nested folders

* Create nested folders.
* Verify they are discovered.
* Verify the target root is also analyzed.

### Permission or enumeration failure

Use mocking where changing Windows permissions is unreliable.

Verify:

* a warning event is emitted;
* the scan continues;
* completion records the warning count.

### File disappears during scan

Mock `stat()` or remove the file at the appropriate point.

Verify the scan continues.

### Cancellation

* Start a scan against a fixture with enough entries to allow cancellation.
* Call `stop()`.
* Verify completion has `cancelled=True`.

### No duplicate completion

Verify exactly one completion event is emitted per scan.

## 17.3 Report tests

Test:

* logs directory is created;
* report filename contains a timestamp;
* header contains target, threshold, and history;
* matched folders are written;
* cancellation is represented;
* UTF-8 paths are preserved.

## 17.4 GUI controller tests

Do not require full visual GUI automation.

Test controller behavior with mocked widgets or handler methods:

* start scan creates a request;
* events update controller state;
* completion triggers report writing;
* cancellation delegates to the scanner;
* GUI controls return to an idle state after completion.

---

# 18. Compatibility Requirements

Phase 0 must preserve:

* Existing `config.yaml` compatibility.
* Existing threshold units in megabytes.
* Existing history units in days.
* Existing log directory behavior.
* Existing background-thread scanning.
* Existing cancellation behavior.
* Existing CustomTkinter interface.
* Existing scan result meaning.

Minor visual changes are acceptable only where needed to display warnings or clearer status.

Do not require the user to manually migrate configuration files.

---

# 19. Code Quality Requirements

Use:

* Python type hints on public functions.
* `pathlib.Path` for application-managed paths.
* Docstrings for public classes and non-obvious functions.
* Pydantic models for scan requests and events.
* Explicit UTF-8 file operations.
* Meaningful exception handling.
* Small modules with clear responsibilities.

Avoid:

* broad `except Exception` blocks unless logging and re-raising or converting at an application boundary;
* mutable default arguments;
* global scanner state;
* GUI imports in scanner modules;
* filesystem traversal in GUI modules;
* direct worker-thread widget updates;
* duplicated path constants;
* business logic inside callback lambdas.

---

# 20. Phase 1 Preparation Requirements

Phase 0 must leave these extension points available.

## Scan lifecycle

The scanner must emit clear start and completion events so Phase 1 can create and update database scan records.

## Directory observations

The scanner’s internal analysis should produce structured observations rather than preformatted strings.

A folder observation should contain at least:

```python
class FolderObservation(BaseModel):
    path: Path
    matching_bytes: int
    direct_file_count: int
    scanned_at: datetime
```

Phase 1 will extend this model with directory identity and snapshot fields.

## Warning persistence

Warnings must be structured so Phase 1 can store them in a `scan_errors` table.

## Report separation

Reports must consume completed scan data rather than scanner internals.

## Controller separation

The GUI controller must consume scanner events without knowing how filesystem traversal is implemented.

## No database assumptions

Do not add placeholder database code or partially initialized SQLAlchemy models during Phase 0.

Prepare clean interfaces only.

---

# 21. Acceptance Criteria

Phase 0 is complete when all of the following are true:

1. The application launches successfully through the project entry point.
2. The CustomTkinter interface still performs scans.
3. Existing settings continue to load and save.
4. Scanning occurs outside the GUI thread.
5. Worker threads do not manipulate GUI widgets directly.
6. Scan events move through a thread-safe queue.
7. The target root and descendant folders are analyzed.
8. BFS traversal uses `deque`.
9. Each file is statted no more than once per folder analysis pass.
10. Permission, missing-file, and general OS errors are recorded as warnings.
11. Cancellation produces exactly one completion event.
12. Text report generation is outside the scanner.
13. Diagnostic logging is enabled.
14. Scanner, configuration, reporting, and GUI code live in separate modules.
15. Automated tests cover configuration, scanning, cancellation, warnings, and report writing.
16. All tests pass with:

```powershell
uv run pytest
```

17. The current timestamp-based reporting result is unchanged in meaning.
18. No SQLite database is created.
19. No SQLAlchemy runtime code is introduced.
20. The scanner exposes structured data suitable for Phase 1 persistence.

---

# 22. Coding-Agent Assignment

Implement Phase 0 only.

Refactor the current application into separate configuration, scanner, reporting, and GUI modules while preserving its existing behavior.

Use Pydantic models for application settings, scan requests, folder observations, warnings, progress events, matched-folder events, and completion events.

Move scanner-to-GUI communication to a thread-safe queue polled by the GUI event loop. The scanner must never update GUI widgets directly.

Keep the current two-phase scan and timestamp-based matching algorithm. Do not implement snapshot comparison or database persistence.

Replace the BFS list queue with `collections.deque`. Include the target root in the folders analyzed. Stat each file once per analysis pass. Catch and report `PermissionError`, `FileNotFoundError`, and `OSError` without terminating the scan.

Move text report generation out of the scanner. Add centralized diagnostic logging.

Add pytest and pytest-cov as development dependencies and create tests for configuration, recent and old files, nested folders, warnings, disappearing files, cancellation, event completion, and report writing.

The completed Phase 0 application must remain runnable through the existing CustomTkinter interface and must be structurally ready for SQLAlchemy and SQLite persistence in Phase 1.
