Below is a technical specification designed to let the coding agent refactor the application incrementally without breaking the existing GUI or requiring a complete rewrite in one pass.

# Windows Folder Sizes Diff

## Snapshot-Based Refactor Technical Specification

**Project:** `windows-folder-sizes-diff`
**Current version:** `0.1.0`
**Language:** Python 3.12+
**Primary platform:** Windows 11
**Database:** SQLite
**GUI:** CustomTkinter
**CLI:** Typer
**Database layer:** SQLAlchemy 2.x
**Schema migrations:** Alembic
**Validation and configuration:** Pydantic
**Windows integration:** pywin32
**Console reporting:** Rich

---

# 1. Purpose

Refactor the current folder scanning application from a modification-time estimator into a persistent snapshot-based disk-growth analyzer.

The current implementation reports the total size of files whose modification or creation timestamps fall within a selected historical period:

```python
max(e.stat().st_mtime, e.stat().st_ctime) > self._since.timestamp()
```

This does not measure actual folder growth. A file may be modified without changing size, moved between folders, recreated at the same size, or counted through multiple directory aliases.

The refactored application must compare filesystem measurements from two completed scans and report actual changes in allocated and logical size.

The primary question the application must answer is:

> Which unique folders consumed additional physical disk space between the previous completed scan and the current completed scan?

---

# 2. Refactor Goals

The refactor must provide:

1. Persistent SQLite snapshots.
2. One stable identity for each scanned directory.
3. Per-scan directory measurements.
4. Actual size differences between scans.
5. Protection against junction, symbolic-link, and reparse-point duplication.
6. Parent/child-aware reporting that avoids double counting.
7. Volume-level free-space reconciliation.
8. Scan completeness and confidence indicators.
9. Retention of the current CustomTkinter GUI.
10. A Typer CLI for testing, automation, and scheduled scans.
11. Alembic-managed database migrations.
12. A phased implementation that preserves a working application after each phase.

---

# 3. Non-Goals for the Initial Refactor

The first production version does not need to:

* Track every individual file.
* Detect all file moves and renames.
* Resolve every hard-link relationship.
* Parse NTFS metadata directly.
* Analyze Volume Shadow Copies in detail.
* inspect every VHDX internal filesystem.
* Replace the current GUI framework.
* Support operating systems other than Windows.
* Introduce a background Windows service.
* Continuously monitor filesystem events.

Those capabilities may be added after reliable directory snapshot comparisons are working.

---

# 4. Existing Application Assessment

The current implementation has several useful characteristics that should be retained:

* `os.scandir()` is appropriate for filesystem traversal.
* Scanning runs on a worker thread.
* The scanner exposes status, result, and completion callbacks.
* The scan can be cancelled with a `threading.Event`.
* Settings are stored outside the source code.
* Text logs are written for completed scans.
* The interface already accepts:

  * target directory;
  * reporting threshold;
  * history interval.

However, the current application has these accuracy limitations:

## 4.1 Modification time is used as a proxy for growth

The current code sums the current size of recently modified files. It does not compare prior and current sizes.

## 4.2 Only immediate files are measured per directory

Each folder is scanned independently and only direct files are totaled. The semantics of the resulting folder size are not clearly identified as exclusive or inclusive.

## 4.3 No persistent baseline exists

There is no prior snapshot against which a current measurement can be compared.

## 4.4 Reparse-point handling is incomplete

`follow_symlinks=False` helps, but the application should explicitly identify and record reparse points rather than relying only on `is_dir()` behavior.

## 4.5 Access errors are silently discarded

A `PermissionError` causes the folder to be skipped without being recorded. This can make a scan appear complete when it is not.

## 4.6 The BFS queue is inefficient

The current implementation uses:

```python
queue.pop(0)
```

This is increasingly expensive as the queue grows. It should be replaced with `collections.deque`.

## 4.7 Files are statted repeatedly

The current expression calls `e.stat()` multiple times for the same file. Each entry should be statted once.

## 4.8 Cancellation produces partial results without durable scan state

Cancelled scans should be recorded as cancelled and must never become comparison baselines.

---

# 5. Recommended Project Architecture

Refactor the code into explicit layers.

```text
windows-folder-sizes-diff/
├── alembic/
│   ├── versions/
│   └── env.py
├── data/
│   └── folder_sizes.db
├── logs/
├── src/
│   └── windows_folder_sizes_diff/
│       ├── __init__.py
│       ├── app.py
│       ├── cli.py
│       ├── config.py
│       ├── constants.py
│       ├── db/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── models.py
│       │   ├── repositories.py
│       │   └── migrations.py
│       ├── scanner/
│       │   ├── __init__.py
│       │   ├── directory_scanner.py
│       │   ├── filesystem.py
│       │   ├── allocated_size.py
│       │   ├── path_identity.py
│       │   └── scan_events.py
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── differ.py
│       │   ├── hierarchy.py
│       │   ├── reconciliation.py
│       │   └── confidence.py
│       ├── reporting/
│       │   ├── __init__.py
│       │   ├── report_models.py
│       │   ├── text_report.py
│       │   └── rich_report.py
│       └── gui/
│           ├── __init__.py
│           ├── main_window.py
│           ├── scan_controller.py
│           └── result_view.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── config.yaml
├── pyproject.toml
└── README.md
```

The exact file count may be reduced initially, but the boundaries should remain.

---

# 6. Dependency Use

The installed dependencies should be used as follows.

## SQLAlchemy

Use SQLAlchemy 2.x declarative models and typed mappings.

Responsibilities:

* database schema;
* sessions and transactions;
* query composition;
* bulk inserts;
* directory and scan persistence;
* comparison queries.

## Alembic

Use Alembic for all schema changes after the initial database model is established.

The application must not rely on ad hoc `CREATE TABLE` statements scattered through runtime code.

## Pydantic

Use Pydantic for:

* validated application settings;
* scan options;
* report DTOs;
* callback event objects;
* threshold validation;
* database-independent domain models.

SQLAlchemy models should not be used directly as GUI models.

## pywin32

Use pywin32 or direct Windows API bindings where necessary for:

* filesystem attributes;
* volume identifiers;
* reparse-point detection;
* allocated-size queries when Python APIs are insufficient;
* disk free-space measurements;
* stable filesystem identity where practical.

## Typer

Use Typer to expose development and automation commands such as:

```powershell
uv run folder-diff scan C:\
uv run folder-diff report
uv run folder-diff scans
uv run folder-diff compare 12 13
uv run folder-diff db-info
```

## Rich

Use Rich for CLI tables, progress indicators, warnings, and summary output.

## CustomTkinter

Retain CustomTkinter as the GUI layer. The GUI should call the same application services as the CLI.

---

# 7. Configuration Model

Replace manual line parsing with a validated Pydantic settings model.

The existing file format may remain:

```yaml
TargetDirectory: 'C:\'
GrowthThresholdMB: 100
HistoryDays: 1
```

However, the refactored configuration should evolve toward:

```yaml
TargetDirectory: 'C:\'
GrowthThresholdMB: 100
ComparisonMode: previous_successful
DatabasePath: data/folder_sizes.db
FollowReparsePoints: false
StoreAllocatedSize: true
IncludeHiddenFolders: true
RetentionDays: 90
LargeFileThresholdMB: 100
ExcludedPaths:
  - 'C:\Windows.old'
  - 'C:\Users\All Users'
```

Recommended Pydantic model:

```python
class AppSettings(BaseModel):
    target_directory: Path
    growth_threshold_mb: int = Field(default=100, ge=0)
    comparison_mode: Literal["previous_successful", "specific_scan"] = "previous_successful"
    database_path: Path = Path("data/folder_sizes.db")
    follow_reparse_points: bool = False
    store_allocated_size: bool = True
    retention_days: int = Field(default=90, ge=1)
    large_file_threshold_mb: int = Field(default=100, ge=0)
    excluded_paths: list[Path] = []
```

`HistoryDays` should eventually be deprecated because snapshot comparison replaces timestamp-based estimation.

For backward compatibility:

* continue reading `HistoryDays`;
* ignore it for snapshot calculations;
* display a migration warning;
* remove it in a later major version.

A YAML parser is not currently listed in the project dependencies. The first phase may preserve the existing simple parser. A later cleanup may add `PyYAML` if desired.

---

# 8. Database Design

## 8.1 Database location

Default:

```text
data/folder_sizes.db
```

The path must be configurable.

The database directory should be created automatically.

## 8.2 SQLite configuration

Enable:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

WAL mode is recommended because the GUI may read progress or prior results while a worker thread writes scan data.

Each thread must use its own SQLAlchemy session.

Do not share a SQLAlchemy session across threads.

## 8.3 Core tables

### `scans`

One row per scan attempt.

Fields:

```text
id                    INTEGER PRIMARY KEY
scan_uuid             TEXT UNIQUE NOT NULL
target_path           TEXT NOT NULL
canonical_target_path TEXT NOT NULL
volume_id             TEXT
started_at             DATETIME NOT NULL
completed_at           DATETIME
status                 TEXT NOT NULL
scan_mode              TEXT NOT NULL
configuration_hash    TEXT NOT NULL
directory_count       INTEGER NOT NULL DEFAULT 0
file_count             INTEGER NOT NULL DEFAULT 0
error_count            INTEGER NOT NULL DEFAULT 0
free_bytes_before      INTEGER
free_bytes_after       INTEGER
total_bytes            INTEGER
logical_bytes_total    INTEGER
allocated_bytes_total  INTEGER
cancel_requested       BOOLEAN NOT NULL DEFAULT 0
notes                  TEXT
```

Allowed status values:

```text
pending
running
completed
completed_with_errors
cancelled
failed
```

Only `completed` and optionally `completed_with_errors` scans may serve as baselines.

### `directories`

One stable row per canonical directory identity.

Fields:

```text
id                    INTEGER PRIMARY KEY
volume_id             TEXT NOT NULL
canonical_path        TEXT NOT NULL
display_path          TEXT NOT NULL
normalized_path_key   TEXT NOT NULL
parent_directory_id   INTEGER NULL
filesystem_object_id  TEXT NULL
first_seen_scan_id    INTEGER NOT NULL
last_seen_scan_id     INTEGER NOT NULL
is_reparse_point      BOOLEAN NOT NULL DEFAULT 0
reparse_tag            INTEGER NULL
is_hidden              BOOLEAN NOT NULL DEFAULT 0
is_system              BOOLEAN NOT NULL DEFAULT 0
```

Constraints:

```text
UNIQUE(volume_id, normalized_path_key)
```

When a stable filesystem object ID is available, it may later become an additional uniqueness signal.

### `directory_snapshots`

One row per directory per scan.

Fields:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
directory_id             INTEGER NOT NULL
direct_logical_bytes     INTEGER NOT NULL DEFAULT 0
direct_allocated_bytes   INTEGER
inclusive_logical_bytes  INTEGER NOT NULL DEFAULT 0
inclusive_allocated_bytes INTEGER
direct_file_count        INTEGER NOT NULL DEFAULT 0
descendant_file_count    INTEGER NOT NULL DEFAULT 0
direct_child_count       INTEGER NOT NULL DEFAULT 0
descendant_dir_count     INTEGER NOT NULL DEFAULT 0
scan_status              TEXT NOT NULL
error_count              INTEGER NOT NULL DEFAULT 0
measured_at              DATETIME NOT NULL
```

Constraint:

```text
UNIQUE(scan_id, directory_id)
```

`direct_*` represents files immediately inside the directory.

`inclusive_*` represents the directory plus all descendants.

Both are required to support useful reports without double counting.

### `scan_errors`

Fields:

```text
id              INTEGER PRIMARY KEY
scan_id         INTEGER NOT NULL
directory_id    INTEGER NULL
path            TEXT NOT NULL
operation       TEXT NOT NULL
error_type      TEXT NOT NULL
error_code      INTEGER NULL
message         TEXT
occurred_at     DATETIME NOT NULL
```

Typical operations:

```text
enumerate_directory
stat_file
query_allocated_size
resolve_path
query_volume
persist_snapshot
```

### `volume_snapshots`

This may be a separate table or included in `scans`.

Recommended fields:

```text
id            INTEGER PRIMARY KEY
scan_id       INTEGER NOT NULL UNIQUE
volume_id     TEXT NOT NULL
mount_point   TEXT NOT NULL
total_bytes   INTEGER NOT NULL
free_bytes    INTEGER NOT NULL
used_bytes    INTEGER NOT NULL
captured_at   DATETIME NOT NULL
```

A separate table allows future scans across multiple volumes.

## 8.4 Optional later tables

Defer these until the directory snapshot system is stable:

```text
files
file_snapshots
hard_link_groups
scan_exclusions
retention_rollups
system_storage_snapshots
```

---

# 9. Directory Measurement Semantics

Every directory snapshot must include two distinct measurements.

## 9.1 Direct size

The total size of files immediately contained in the directory.

```text
direct_size(folder) =
    sum(size of direct child files)
```

This is also called exclusive size.

## 9.2 Inclusive size

The total size of all files contained in the directory and every descendant.

```text
inclusive_size(folder) =
    direct_size(folder)
    + sum(inclusive_size(each child folder))
```

## 9.3 Growth calculations

For a directory present in both scans:

```text
direct_growth =
    current.direct_allocated_bytes
    - previous.direct_allocated_bytes
```

```text
inclusive_growth =
    current.inclusive_allocated_bytes
    - previous.inclusive_allocated_bytes
```

If allocated size is unavailable, use logical size and mark the measurement as estimated.

## 9.4 New directory

If no prior snapshot exists:

```text
growth = current size
status = newly_created
```

## 9.5 Removed directory

If the directory existed previously but not currently:

```text
growth = -previous size
status = removed
```

Removed directories should appear in reduction reports but not be inserted as current snapshots.

---

# 10. Filesystem Traversal Design

## 10.1 Single-pass traversal

Replace the current two-phase approach of:

1. building a full folder list;
2. rescanning every folder;

with one traversal that gathers measurements as it walks.

The scanner should:

1. enter a directory;
2. enumerate each child once;
3. stat each file once;
4. enqueue normal child directories;
5. record direct size and counts;
6. aggregate child totals into parents after descendants are processed.

This avoids scanning every folder twice.

## 10.2 Queue structure

Use:

```python
from collections import deque
```

Do not use:

```python
queue.pop(0)
```

## 10.3 Bottom-up aggregation

A practical iterative strategy:

1. Traverse breadth-first or depth-first.
2. Store each directory’s direct measurements and parent relationship.
3. After traversal, sort directories by depth descending.
4. Add each child’s inclusive totals to its parent.
5. Persist final snapshot rows in batches.

This avoids Python recursion depth limitations on deeply nested folder trees.

## 10.4 File stat calls

For each file:

```python
stat_result = entry.stat(follow_symlinks=False)
```

Reuse the result.

Do not call `entry.stat()` repeatedly.

## 10.5 Error handling

Catch at least:

```python
PermissionError
FileNotFoundError
OSError
```

Files and folders can disappear during a scan.

Each failure must be recorded in `scan_errors`.

The scanner should continue where safe.

## 10.6 Long paths

Normalize or preserve Windows long-path-compatible forms.

Do not truncate paths for storage.

The GUI may abbreviate them for display.

---

# 11. Path Identity and Duplicate Prevention

## 11.1 Normalized comparison key

Create a normalized path key using:

* absolute path;
* normalized separators;
* normalized trailing slash;
* case folding;
* normalized drive letter;
* removal of redundant `.` and `..` elements.

Example:

```python
normalized_key = os.path.normcase(os.path.normpath(os.path.abspath(path)))
```

Windows API canonicalization may be added where necessary.

## 11.2 Preserve display path

Store both:

```text
canonical_path
display_path
```

The display path should remain human-readable.

## 11.3 Reparse points

By default:

* detect reparse points;
* record them;
* do not recursively traverse them;
* do not include their target content in directory totals.

This prevents duplication from paths such as:

```text
C:\Users\All Users
C:\ProgramData
```

## 11.4 Reparse-point metadata

Record:

* source path;
* reparse tag;
* whether it was followed;
* target path when safely resolvable.

## 11.5 Cycle prevention

If following reparse points becomes configurable, maintain a set of visited filesystem identities.

Do not rely only on visited path strings.

---

# 12. Allocated Size Strategy

## 12.1 Logical size

Logical size is available from:

```python
stat_result.st_size
```

## 12.2 Allocated size

Use a dedicated abstraction:

```python
class AllocatedSizeProvider(Protocol):
    def get_allocated_size(self, path: Path, stat_result: os.stat_result) -> int | None:
        ...
```

Implement a Windows provider using an appropriate Windows filesystem query.

The rest of the application must not depend directly on pywin32 calls.

## 12.3 Fallback

If allocated size cannot be obtained:

* retain logical size;
* set allocated size to `NULL`;
* mark the result as estimated;
* do not silently equate the two.

## 12.4 Performance

Allocated-size API calls may be expensive.

The scanner should support:

```text
logical_only
allocated_size
```

Initial daily scans may use logical size while allocated-size support is developed and benchmarked.

The database schema should support both from the beginning.

---

# 13. Scan Lifecycle

Each scan must follow a durable lifecycle.

## 13.1 Start

1. Validate settings.
2. Open a database session.
3. Capture initial volume information.
4. Create a `scans` row with `running` status.
5. Commit the scan record.
6. Begin traversal.

## 13.2 During scan

* emit typed progress events;
* collect directory measurements;
* write errors;
* periodically update scan counters;
* honor cancellation requests;
* avoid publishing comparison results before the snapshot is complete.

## 13.3 Successful completion

1. Finalize inclusive sizes.
2. Persist directory snapshots.
3. Capture final volume information.
4. Update scan counts.
5. Mark scan `completed` or `completed_with_errors`.
6. Commit.
7. Run comparison analysis.
8. generate GUI, CLI, and log output.

## 13.4 Cancellation

If cancelled:

* stop enumeration promptly;
* retain the scan record;
* mark it `cancelled`;
* preserve error and progress information;
* do not use it as a baseline;
* optionally delete incomplete directory snapshot rows.

## 13.5 Failure

On an unhandled failure:

* roll back the active batch;
* mark the scan `failed` in a fresh transaction;
* store the failure message;
* do not use the scan as a baseline.

---

# 14. Baseline Selection

The default comparison baseline is:

> The most recent successful scan with the same target, volume, scan mode, and configuration hash.

The baseline query must match:

* canonical target path;
* volume identity;
* scan mode;
* exclusion rules;
* reparse-point policy;
* size measurement mode.

A configuration hash should be generated from all settings that affect scan results.

Do not compare scans with materially different configurations without an explicit override.

If no baseline exists:

* save the current scan;
* identify it as the baseline;
* report current sizes;
* do not claim that growth occurred.

Display:

```text
Baseline created. Run another scan to calculate folder growth.
```

---

# 15. Difference Analysis

Create a dedicated comparison service.

Example interface:

```python
class ScanDiffer:
    def compare(
        self,
        previous_scan_id: int,
        current_scan_id: int,
        threshold_bytes: int,
    ) -> ScanDiffReport:
        ...
```

## 15.1 Directory states

Each directory result should be classified as:

```text
unchanged
grown
reduced
new
removed
incomplete
not_comparable
```

## 15.2 Reported metrics

Each result should include:

```text
path
previous_direct_bytes
current_direct_bytes
direct_delta_bytes
previous_inclusive_bytes
current_inclusive_bytes
inclusive_delta_bytes
measurement_type
confidence
error_count
status
```

## 15.3 Ranking

The primary report should rank by:

```text
direct allocated growth descending
```

This avoids counting the same growth repeatedly through every ancestor.

The GUI may also offer an inclusive-growth view for navigation.

## 15.4 Parent/child handling

The application may display both a parent and child, but the primary total must use direct growth or another non-overlapping metric.

Never sum inclusive growth from multiple hierarchy levels.

---

# 16. Volume Reconciliation

Capture free-space and total-space measurements for the scanned volume.

Calculate:

```text
previous_used_bytes =
    previous_total_bytes - previous_free_bytes
```

```text
current_used_bytes =
    current_total_bytes - current_free_bytes
```

```text
observed_volume_growth =
    current_used_bytes - previous_used_bytes
```

Calculate explained growth using non-overlapping directory measurements:

```text
explained_growth =
    sum(current direct bytes)
    - sum(previous direct bytes)
```

Then:

```text
unexplained_growth =
    observed_volume_growth - explained_growth
```

The report must show:

```text
Observed volume growth
Explained folder growth
Unexplained or system-managed growth
```

A mismatch is not necessarily an error. Causes may include:

* scan timing differences;
* files changing during traversal;
* inaccessible directories;
* system-managed space;
* pagefile or hibernation changes;
* shadow copies;
* filesystem metadata;
* compressed or sparse allocation behavior.

---

# 17. Confidence Model

Assign a confidence level to the overall scan and individual results.

## High confidence

* both scans completed;
* same configuration;
* no relevant errors;
* allocated size available;
* reparse points excluded;
* same volume identity.

## Medium confidence

* scans completed;
* logical size only;
* minor inaccessible paths;
* path-based identity only.

## Low confidence

* completed with substantial errors;
* configuration mismatch;
* incomplete allocated-size data;
* target changed during scanning;
* volume reconciliation mismatch is large.

The report should include a reason, not only a label.

---

# 18. Typed Events and Threading

Replace loosely structured callback parameters with Pydantic event models.

Examples:

```python
class ScanProgress(BaseModel):
    scan_id: int
    phase: str
    current_path: str | None
    directories_scanned: int
    files_scanned: int
    errors: int
    elapsed_seconds: int
```

```python
class ScanCompleted(BaseModel):
    scan_id: int
    status: str
    directories_scanned: int
    files_scanned: int
    errors: int
    elapsed_seconds: int
```

The scanner should never update GUI widgets directly.

Recommended flow:

```text
Scanner thread
    ↓
thread-safe queue
    ↓
GUI controller
    ↓
CustomTkinter widgets
```

Use the GUI event loop to poll the queue with `after()`.

This is safer than calling GUI callbacks directly from the worker thread.

---

# 19. CLI Specification

Create a Typer application with these commands.

## `scan`

```powershell
uv run folder-diff scan C:\
```

Options:

```text
--threshold-mb
--database
--logical-only
--include-errors
--exclude
--no-compare
```

Behavior:

* run a new scan;
* persist it;
* compare it against the appropriate baseline;
* display a Rich summary.

## `scans`

```powershell
uv run folder-diff scans
```

Displays:

* scan ID;
* start time;
* target;
* status;
* directory count;
* error count;
* baseline eligibility.

## `report`

```powershell
uv run folder-diff report
```

Displays the newest comparison.

Options:

```text
--scan-id
--previous-scan-id
--threshold-mb
--limit
--inclusive
```

## `errors`

```powershell
uv run folder-diff errors --scan-id 12
```

## `db-info`

Displays:

* database path;
* schema revision;
* file size;
* scan count;
* snapshot count;
* oldest and newest scan.

## `purge`

Deletes snapshots according to retention rules.

Require confirmation unless `--yes` is supplied.

---

# 20. GUI Refactor

The GUI should retain the current workflow while changing the meaning of the results.

## 20.1 Scan controls

Retain:

* target directory;
* growth threshold;
* scan button;
* cancel button;
* progress/status display.

Replace or deprecate:

```text
HistoryDays
```

Add:

```text
Comparison baseline
Measurement mode
Include system paths
Show reductions
```

## 20.2 First scan behavior

Display:

```text
Baseline scan completed.
No previous comparable scan exists.
Run another scan to calculate growth.
```

## 20.3 Result table

Recommended columns:

```text
Folder
Net Growth
Current Size
Previous Size
Type
Confidence
Errors
```

Allow sorting by net growth.

## 20.4 Summary panel

Display:

```text
Previous free space
Current free space
Observed disk usage change
Explained folder growth
Unexplained growth
Folders scanned
Files scanned
Errors
Comparison confidence
```

## 20.5 Detail view

Selecting a folder should show:

* direct growth;
* inclusive growth;
* prior size;
* current size;
* child folders contributing most growth;
* scan errors;
* whether the path is new or removed.

---

# 21. Logging

Continue writing human-readable log files, but logs should become generated reports rather than the source of truth.

The SQLite database is authoritative.

Recommended log format:

```text
Scan ID: 14
Scan started: 2026-07-23 09:15:02
Scan completed: 2026-07-23 09:28:41
Target: C:\
Baseline scan: 13
Status: completed_with_errors
Measurement: allocated
Directories: 708,923
Files: 4,064,768
Errors: 37

Volume reconciliation
------------------------------------------------------------
Observed volume growth:       10.02 GB
Explained folder growth:       7.84 GB
Unexplained growth:            2.18 GB

Largest direct folder growth
------------------------------------------------------------
C:\Users\brad\AppData\...      1.49 GB
...
```

Logs should include scan IDs so results can be reproduced from the database.

---

# 22. Retention Strategy

Initial retention policy:

* retain all detailed scans for 90 days;
* never delete the newest successful scan;
* never delete a scan referenced as an explicitly preserved baseline;
* retain scan summary rows after deleting detailed snapshots;
* allow retention to be disabled.

Do not implement weekly and monthly rollups in the initial refactor unless database growth becomes a demonstrated problem.

SQLite can support a substantial number of directory snapshot rows if indexes and batch inserts are used correctly.

---

# 23. Performance Requirements

Initial target:

* scan approximately 700,000 directories without excessive memory growth;
* cancellation response within a few seconds;
* avoid loading all prior snapshots into Python when SQL joins can calculate differences;
* batch database inserts;
* use SQLAlchemy Core bulk operations where ORM-per-row insertion is too slow;
* display progress at throttled intervals rather than for every filesystem entry.

Progress callbacks should be emitted no more than approximately 5–10 times per second.

## Recommended indexes

```text
scans(status, canonical_target_path, completed_at)
directories(volume_id, normalized_path_key)
directories(parent_directory_id)
directory_snapshots(scan_id, directory_id)
directory_snapshots(directory_id, scan_id)
scan_errors(scan_id)
```

---

# 24. Testing Strategy

Use temporary directories and temporary SQLite databases.

A test framework is not currently listed in `pyproject.toml`. Add development dependencies separately when implementation begins:

```powershell
uv add --dev pytest pytest-cov
```

## Unit tests

Test:

* path normalization;
* configuration validation;
* direct-size calculations;
* inclusive-size aggregation;
* baseline selection;
* delta calculation;
* confidence classification;
* configuration hash generation.

## Integration tests

### File grows

1. Create a 100 MB file.
2. Scan.
3. Increase it to 150 MB.
4. Scan again.

Expected:

```text
Net direct growth: 50 MB
```

### File is rewritten at the same size

Expected:

```text
Net growth: 0 MB
```

### File moves between folders

Expected:

```text
Source direct growth: negative file size
Destination direct growth: positive file size
Total explained growth: 0
```

Move detection is not required to classify it as a move in Phase 1.

### Child growth

A file is added to a nested folder.

Expected:

```text
Child direct growth: file size
Parent direct growth: 0
Parent inclusive growth: file size
```

### Reparse-point alias

Create or use a directory junction to a scanned directory.

Expected:

```text
Target data counted once
Junction recorded as skipped
```

### Permission failure

Expected:

```text
Error persisted
Scan marked completed_with_errors
Confidence reduced
```

### Cancellation

Expected:

```text
Scan marked cancelled
Scan not eligible as baseline
```

### No prior baseline

Expected:

```text
Baseline created
No growth claims made
```

### Configuration mismatch

Expected:

```text
Automatic comparison blocked
```

---

# 25. Refactor Phases

## Phase 0 — Stabilize the Current Application

### Objective

Prepare the existing code for refactoring without changing its current user-visible behavior.

### Work

* Move source code into a proper package.
* Separate settings, scanning, logging, and GUI code.
* Replace `list.pop(0)` with `deque.popleft()`.
* Stat each file only once.
* Add structured error handling.
* Add Python logging.
* Add type hints.
* Add pytest as a development dependency.
* Add basic tests for existing behavior.
* Create an application version constant.
* Preserve the current timestamp-based report temporarily.

### Deliverable

The application behaves as it does today but has modular code and tests.

### Acceptance criteria

* Existing GUI still launches.
* Existing scans still complete.
* Cancellation still works.
* Existing text logs are produced.
* No database dependency is required yet.
* Core scanner logic is no longer defined in the GUI module.

---

## Phase 1 — Database Foundation

### Objective

Introduce SQLite persistence without changing the current scan algorithm.

### Work

* Configure SQLAlchemy engine and sessions.
* Add SQLite pragmas.
* Define initial models:

  * `scans`;
  * `directories`;
  * `directory_snapshots`;
  * `scan_errors`;
  * `volume_snapshots`.
* Initialize Alembic.
* Create the first migration.
* Add repository classes.
* Record scan lifecycle states.
* Store current folder measurements in the database.
* Add `db-info` and `scans` CLI commands.

### Deliverable

Every scan creates a durable scan record and stores directory measurements.

### Acceptance criteria

* Database is created automatically.
* Alembic reports the current schema revision.
* Each completed scan appears in `scans`.
* Cancelled and failed scans are retained with correct statuses.
* Scan errors are stored.
* No incomplete scan is selected as a baseline.
* Existing GUI results still work.

---

## Phase 2 — True Snapshot Differences

### Objective

Replace timestamp-based growth estimates with snapshot comparisons.

### Work

* Remove modification-time calculations from the primary report.
* Compare the current scan to the previous comparable successful scan.
* Implement direct logical-size deltas.
* Classify directories as:

  * grown;
  * reduced;
  * new;
  * removed;
  * unchanged.
* Add baseline creation behavior.
* Implement configuration hashing.
* Add Rich CLI comparison reports.
* Update GUI terminology from “MB in last N days” to “Net growth since previous scan.”

### Deliverable

The application reports actual logical-size changes between scans.

### Acceptance criteria

* Same-size file modifications produce zero growth.
* New files produce their actual size as growth.
* Deleted files produce negative growth.
* The first scan creates a baseline without claiming growth.
* Reports identify both current and baseline scan IDs.
* `HistoryDays` is no longer used for the primary calculation.

This is the minimum point at which the application becomes an accurate folder-size diff tool.

---

## Phase 3 — Hierarchical Accuracy

### Objective

Separate direct and inclusive directory growth and eliminate parent/child double counting.

### Work

* Record parent relationships.
* Calculate directory depth.
* Calculate inclusive logical sizes bottom-up.
* Store direct and inclusive values separately.
* Rank the primary report by direct growth.
* Add an optional inclusive view.
* Add hierarchy-aware GUI results.
* Prevent inclusive parent and child rows from being summed together.

### Deliverable

The report can show both where bytes physically appeared and which larger directory trees were affected.

### Acceptance criteria

* Child growth appears once in direct-growth totals.
* Parent inclusive growth reflects descendant changes.
* Grand totals do not double count descendants.
* The report clearly labels direct and inclusive values.
* The previous `Whesvc` parent/child duplication pattern cannot inflate the reported total.

---

## Phase 4 — Reparse Points and Canonical Identity

### Objective

Prevent duplicate traversal through Windows aliases, junctions, and symbolic links.

### Work

* Add explicit reparse-point detection.
* Store reparse-point metadata.
* Skip reparse-point traversal by default.
* Normalize canonical path keys.
* Identify the scanned volume.
* Add cycle protection.
* Add default exclusions for known compatibility aliases where useful.
* Add tests using junctions.

### Deliverable

The same physical directory tree is not counted through multiple Windows paths.

### Acceptance criteria

* `C:\Users\All Users` does not duplicate `C:\ProgramData`.
* Junctions are shown as skipped rather than silently ignored.
* Reparse-point behavior is included in the configuration hash.
* No reparse cycle can cause infinite traversal.

---

## Phase 5 — Volume Reconciliation

### Objective

Compare explained folder growth with the actual volume free-space change.

### Work

* Capture volume size and free space for each successful scan.
* Calculate observed used-space growth.
* Compare observed growth with directory growth.
* Add unexplained/system-managed growth.
* Add reconciliation confidence and warnings.
* Add GUI and CLI summary panels.

### Deliverable

The report states how much of the observed disk-space loss is explained by the directory scan.

### Acceptance criteria

The report displays:

```text
Observed volume growth
Explained directory growth
Unexplained growth
```

* The values use bytes internally.
* Human-readable conversions are presentation-only.
* Large discrepancies generate a warning.
* Scan timing limitations are documented.

---

## Phase 6 — Allocated Size Support

### Objective

Measure physical disk allocation rather than relying only on logical file length.

### Work

* Implement `AllocatedSizeProvider`.
* Add Windows allocated-size lookup.
* Preserve logical and allocated values.
* Add fallback behavior.
* Benchmark performance.
* Add measurement-mode configuration.
* Update confidence rules.
* Add tests for sparse and compressed files where practical.

### Deliverable

Reports can rank growth by physical disk consumption.

### Acceptance criteria

* Logical and allocated sizes are stored separately.
* Missing allocated-size values are explicit.
* Estimated results are labeled.
* The application does not silently treat logical size as allocated size.
* Users may select logical-only mode for faster scans.

---

## Phase 7 — File-Level Forensics

### Objective

Add targeted file-level attribution without cataloging every small file during every daily scan.

### Work

* Add `files` and `file_snapshots`.
* Track files above a configurable threshold.
* Store file IDs where available.
* Identify:

  * new large files;
  * removed large files;
  * resized files;
  * probable moves or renames.
* Add folder detail reports listing the largest contributing files.

### Deliverable

Users can see which large files caused a folder to grow.

### Acceptance criteria

* Large-file thresholds are configurable.
* Same-size rewrites do not count as growth.
* Moves do not inflate volume totals.
* File identity uncertainty is clearly labeled.
* Daily scans remain performant.

---

## Phase 8 — Retention, Maintenance, and Scheduling

### Objective

Prepare the application for long-term daily use.

### Work

* Implement retention rules.
* Add database maintenance commands.
* Add optional SQLite `VACUUM`.
* Add export to CSV or JSON.
* Add Task Scheduler documentation.
* Add application health checks.
* Add database backup guidance.
* Add scan history and trend views.

### Deliverable

The application can operate daily without uncontrolled database growth.

### Acceptance criteria

* Old detailed snapshots can be removed safely.
* The latest usable baseline is protected.
* Purge operations are transactional.
* Database size and snapshot counts are visible.
* Scheduled CLI execution works independently of the GUI.

---

# 26. Recommended Implementation Boundary

Do not attempt all phases in one branch.

Recommended branch sequence:

```text
refactor/modular-foundation
feature/sqlite-snapshots
feature/true-scan-diffs
feature/hierarchical-sizes
feature/reparse-protection
feature/volume-reconciliation
feature/allocated-size
feature/file-forensics
```

Each branch should leave the application runnable and testable.

---

# 27. Immediate Coding-Agent Assignment

The first coding assignment should be limited to Phases 0 and 1.

Use this scope:

```text
Refactor the current application into separate configuration, scanner,
database, reporting, CLI, and GUI modules.

Add a SQLite database using SQLAlchemy 2.x and Alembic.

Persist one scan record per scan, one stable directory identity per canonical
path, one directory snapshot per directory per scan, all scan errors, and
volume free-space information.

Do not replace the current modified-file reporting algorithm yet.

Preserve the existing CustomTkinter GUI behavior and callbacks.

Add Typer commands for listing scans and showing database information.

Use a separate SQLAlchemy session inside the worker thread.

Mark scans as running, completed, completed_with_errors, cancelled, or failed.

Cancelled, failed, and partial scans must never be selected as future
comparison baselines.

Add automated tests for scan lifecycle, cancellation, database persistence,
and error recording.
```

Once that is stable, Phase 2 should replace the inaccurate growth algorithm.

---

# 28. Definition of Done for the Refactor

The refactor is complete when:

1. A first scan creates a durable baseline.
2. A subsequent scan compares against that baseline.
3. Modified but unchanged files show zero growth.
4. New, deleted, and resized data produce correct deltas.
5. Parent and child folders do not inflate totals.
6. Junction aliases do not duplicate data.
7. Logical and allocated size are distinguishable.
8. Volume-level disk loss is reconciled against folder growth.
9. Incomplete scans are clearly identified.
10. GUI and CLI use the same scanning and analysis services.
11. Database schema changes are Alembic-managed.
12. Daily historical scans can be retained and queried reliably.

The safest implementation order is to add persistence before changing the measurement logic. That gives the agent a durable baseline system first, then Phase 2 can replace the current timestamp method with true snapshot differences without simultaneously rebuilding every other part of the application.
