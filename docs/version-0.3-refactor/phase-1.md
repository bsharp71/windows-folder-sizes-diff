# Phase 1 Technical Specification

Implement Phase 1 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 1. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Add SQLite Persistence and Durable Scan History

**Project:** `windows-folder-sizes-diff`
**Phase:** 1 — Database Foundation
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Current application behavior:** Timestamp-based recent-file reporting
**Prerequisite:** Phase 0 completed

---

# 1. Objective

Add durable SQLite persistence to the application without replacing the current timestamp-based scan calculation.

At the end of Phase 1:

* Every scan attempt must be recorded in SQLite.
* Every successfully observed directory must have a stable database identity.
* Every scan must store one measurement row for each observed directory.
* Scan warnings and errors must be persisted.
* Scan lifecycle states must be durable.
* Cancelled and failed scans must be retained but marked unusable as baselines.
* The application must expose basic scan-history and database-inspection commands.
* The existing CustomTkinter GUI and text reports must continue to work.
* The current `matching_bytes` metric must retain its existing meaning.

Phase 1 creates the persistence foundation required for true snapshot comparison in Phase 2.

It must not yet claim that stored measurements represent actual folder growth.

---

# 2. Prerequisites

Before beginning Phase 1, verify that Phase 0 provides:

* A package-based `src` layout.
* A scanner independent of the GUI.
* Typed Pydantic scan events.
* A thread-safe event queue.
* A GUI controller that consumes scan events.
* A separate text report writer.
* Structured scan warnings.
* Automated tests.
* A stable application entry point.

Phase 1 must build on those interfaces rather than reintroducing direct coupling.

---

# 3. Phase 1 Scope

Implement:

* SQLite database creation.
* SQLAlchemy engine and session configuration.
* Alembic initialization and first migration.
* Persistent scan lifecycle records.
* Stable directory identities.
* Per-scan directory observations.
* Persistent warnings and errors.
* Persistent scan configuration metadata.
* Volume-space observations.
* Database repositories or services.
* Basic Typer CLI commands for database and scan history.
* GUI integration with scan persistence.
* Tests for persistence and lifecycle behavior.

Do not implement:

* True folder-size differences.
* Comparison between scans.
* Baseline selection for reporting.
* Inclusive directory size aggregation.
* Allocated-size measurement.
* File-level cataloging.
* Move or rename detection.
* Hard-link handling.
* Reparse-point target resolution.
* Volume reconciliation.
* Retention or purge policies.
* Scheduled scanning.

---

# 4. Preserve Current Scan Semantics

The current scanner calculates:

> The logical size of direct child files whose modification or creation timestamp falls within the configured history period.

This value should continue to be stored as:

```text
matching_bytes
```

or:

```text
recent_activity_bytes
```

Do not rename it to:

```text
growth_bytes
size_delta
folder_growth
```

The database schema and application code must reflect that this is an observation from one scan, not a comparison result.

Phase 2 will introduce actual scan differences.

---

# 5. Required Project Additions

Extend the Phase 0 structure with database and CLI modules.

```text
windows-folder-sizes-diff/
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
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
│       │   ├── base.py
│       │   ├── engine.py
│       │   ├── models.py
│       │   ├── repositories.py
│       │   └── lifecycle.py
│       ├── scanner/
│       │   ├── folder_scanner.py
│       │   ├── models.py
│       │   └── events.py
│       ├── reporting/
│       │   └── text_log.py
│       └── gui/
│           ├── main_window.py
│           └── scan_controller.py
├── tests/
│   ├── test_database.py
│   ├── test_scan_repository.py
│   ├── test_directory_repository.py
│   ├── test_scan_lifecycle.py
│   ├── test_cli.py
│   └── ...
├── alembic.ini
├── config.yaml
├── pyproject.toml
└── README.md
```

The exact filenames may differ, but database engine creation, ORM models, repositories, and lifecycle coordination must remain separate responsibilities.

---

# 6. Database Location

Use the default database path:

```text
data/folder_sizes.db
```

The path must be configurable.

Add a database path to the application settings model.

Recommended setting:

```yaml
DatabasePath: 'data/folder_sizes.db'
```

Recommended Pydantic field:

```python
database_path: Path = Path("data/folder_sizes.db")
```

Requirements:

* Resolve relative database paths from the project or application data root consistently.
* Create the parent directory automatically.
* Do not place the SQLite database in the source package.
* Do not place the database in the logs directory.
* Tests must use temporary database files.

---

# 7. SQLAlchemy Engine Configuration

Create a centralized database engine factory.

Example responsibility:

```python
def create_database_engine(database_path: Path) -> Engine:
    ...
```

Use a SQLite URL based on the resolved path.

Configure SQLite connection pragmas:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

Apply pragmas using a SQLAlchemy connection event.

Example pattern:

```python
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()
```

Scope this behavior carefully so tests and non-SQLite engines are not affected unexpectedly.

Requirements:

* Use SQLAlchemy 2.x style.
* Use typed declarative mappings.
* Do not use deprecated query APIs.
* Do not share ORM sessions across threads.
* Do not keep one global session open for the application lifetime.

---

# 8. Session Management

Create a session factory:

```python
from sqlalchemy.orm import sessionmaker

SessionFactory = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)
```

Use one session per unit of work.

The scanner worker thread must create and close its own session.

The GUI thread must not reuse the scanner’s session.

Recommended pattern:

```python
with session_factory() as session:
    ...
    session.commit()
```

On failure:

```python
session.rollback()
```

Requirements:

* Every session must be closed.
* Repository methods should receive a session or use an explicit unit-of-work boundary.
* Do not hide long-lived sessions inside singleton repositories.
* Database writes must not occur from the GUI event loop unless they are lightweight and intentional.

---

# 9. Alembic Setup

Initialize Alembic for the project.

Create:

```text
alembic.ini
alembic/env.py
alembic/versions/
```

Configure Alembic to import SQLAlchemy metadata from the application models.

The database URL may be injected from application settings or environment configuration rather than duplicated manually.

Create the first migration containing all Phase 1 tables.

The application must not rely on `Base.metadata.create_all()` as the production migration strategy.

It may be used in isolated tests where appropriate, but production setup must use Alembic.

Required commands should work:

```powershell
uv run alembic upgrade head
```

```powershell
uv run alembic current
```

```powershell
uv run alembic history
```

The coding agent must document how a fresh user creates or upgrades the database.

---

# 10. Database Schema

## 10.1 `scans`

Create one row for every scan attempt.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
scan_uuid                TEXT UNIQUE NOT NULL
target_path              TEXT NOT NULL
normalized_target_path   TEXT NOT NULL
started_at               DATETIME NOT NULL
completed_at             DATETIME NULL
status                   TEXT NOT NULL
history_days             INTEGER NOT NULL
growth_threshold_mb      INTEGER NOT NULL
configuration_hash       TEXT NOT NULL
folders_discovered       INTEGER NOT NULL DEFAULT 0
folders_analyzed         INTEGER NOT NULL DEFAULT 0
folders_matched          INTEGER NOT NULL DEFAULT 0
files_examined           INTEGER NOT NULL DEFAULT 0
warning_count            INTEGER NOT NULL DEFAULT 0
cancel_requested         BOOLEAN NOT NULL DEFAULT 0
failure_message          TEXT NULL
created_at               DATETIME NOT NULL
updated_at               DATETIME NOT NULL
```

Allowed status values:

```text
pending
running
completed
completed_with_warnings
cancelled
failed
```

Use either:

* a Python enum persisted as strings; or
* a constrained string field.

Avoid database-specific enum types because SQLite support is limited.

## 10.2 `directories`

Create one stable row per normalized directory path.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
normalized_path          TEXT NOT NULL UNIQUE
display_path             TEXT NOT NULL
parent_normalized_path   TEXT NULL
first_seen_scan_id       INTEGER NOT NULL
last_seen_scan_id        INTEGER NOT NULL
created_at               DATETIME NOT NULL
updated_at               DATETIME NOT NULL
```

Phase 1 directory identity is path-based.

Do not attempt NTFS file-ID identity yet.

Requirements:

* Windows path comparison must be case-insensitive.
* Normalize path separators.
* Normalize trailing separators.
* Normalize drive-letter casing.
* Preserve a human-readable display path separately.
* The target root must have a directory row.
* A directory must not receive a new database identity solely because path casing changed.

A future migration may add:

```text
volume_id
filesystem_object_id
is_reparse_point
reparse_tag
```

Do not require those in Phase 1 unless already available from Phase 0 without significant scope expansion.

## 10.3 `directory_observations`

Create one observation row per directory per scan.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
directory_id             INTEGER NOT NULL
matching_bytes           INTEGER NOT NULL DEFAULT 0
direct_file_count        INTEGER NOT NULL DEFAULT 0
matched_file_count       INTEGER NOT NULL DEFAULT 0
observed_at              DATETIME NOT NULL
status                   TEXT NOT NULL
warning_count            INTEGER NOT NULL DEFAULT 0
```

Constraint:

```text
UNIQUE(scan_id, directory_id)
```

Suggested status values:

```text
observed
observed_with_warnings
inaccessible
disappeared
skipped
```

This table stores Phase 1’s current timestamp-based observation.

Do not call it `directory_snapshots` unless the team deliberately wants that term for raw observations. `directory_observations` is more accurate for Phase 1.

Phase 2 may extend or replace its measurement fields.

## 10.4 `scan_warnings`

Persist structured warning events.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
directory_id             INTEGER NULL
path                     TEXT NOT NULL
operation                TEXT NOT NULL
error_type               TEXT NOT NULL
error_code               INTEGER NULL
message                  TEXT NOT NULL
occurred_at              DATETIME NOT NULL
```

Typical operations:

```text
enumerate_directory
stat_file
analyze_folder
normalize_path
capture_volume
persist_observation
write_report
```

Warnings from report writing may be persisted only when they belong to the scan lifecycle. General application errors should remain in the diagnostic log.

## 10.5 `volume_observations`

Create one volume-space record per scan.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL UNIQUE
root_path                TEXT NOT NULL
total_bytes              INTEGER NULL
free_bytes_before        INTEGER NULL
free_bytes_after         INTEGER NULL
captured_before_at       DATETIME NULL
captured_after_at        DATETIME NULL
status                   TEXT NOT NULL
error_message            TEXT NULL
```

Phase 1 must store these values but must not yet calculate reconciliation or claim causality.

Suggested status values:

```text
complete
partial
unavailable
```

Use Python’s disk-usage APIs or an appropriate Windows API.

---

# 11. Recommended ORM Relationships

Define typed SQLAlchemy relationships.

Conceptually:

```text
Scan
├── directory_observations
├── warnings
└── volume_observation

Directory
├── observations
├── first_seen_scan
└── last_seen_scan
```

Requirements:

* Use foreign keys.
* Enable SQLite foreign-key enforcement.
* Use explicit delete behavior.
* Do not cascade-delete directories when deleting a scan.
* If a scan is deleted in future phases, its observations and warnings may cascade.
* Directory identity rows should remain unless a future maintenance process removes unused entries.

Avoid bidirectional relationships where they add complexity without value.

---

# 12. Indexes

Create indexes for expected access patterns.

Required indexes:

```text
scans(status, started_at)
scans(normalized_target_path, started_at)
directories(normalized_path)
directory_observations(scan_id, directory_id)
directory_observations(directory_id, scan_id)
scan_warnings(scan_id)
```

The unique constraint on `directories.normalized_path` may already provide an index.

Add only indexes that serve known queries.

---

# 13. Path Normalization

Create one shared path-normalization function.

Example:

```python
def normalize_windows_path(path: Path | str) -> str:
    absolute = os.path.abspath(os.fspath(path))
    normalized = os.path.normpath(absolute)
    return os.path.normcase(normalized)
```

Requirements:

* Use the same normalization function for:

  * scan targets;
  * directory identity;
  * warning paths where relevant;
  * repository lookup.
* Preserve the original or display form separately.
* Do not resolve reparse-point targets in Phase 1.
* Do not use `Path.resolve()` blindly if it may follow links or fail on inaccessible paths.
* Document that identity remains path-based until a later phase.

---

# 14. Configuration Hash

Create a deterministic configuration hash for every scan.

Include settings that affect the scan result:

```text
normalized target path
history days
growth threshold
link-following policy
current scan algorithm version
relevant exclusions, if any
```

Use a stable serialized representation and SHA-256.

Example:

```python
payload = {
    "target_path": normalized_target_path,
    "history_days": request.history_days,
    "growth_threshold_mb": request.growth_threshold_mb,
    "follow_symlinks": False,
    "algorithm_version": 1,
}
```

Serialize keys in stable order.

Store the resulting hash in `scans.configuration_hash`.

Phase 1 does not yet use the hash to select a baseline, but Phase 2 will.

---

# 15. Scan Lifecycle Service

Create a dedicated service responsible for durable scan state.

Recommended interface:

```python
class ScanLifecycleService:
    def create_scan(self, request: ScanRequest) -> ScanRecord:
        ...

    def mark_running(self, scan_id: int) -> None:
        ...

    def update_progress(
        self,
        scan_id: int,
        *,
        folders_discovered: int,
        folders_analyzed: int,
        files_examined: int,
        warning_count: int,
    ) -> None:
        ...

    def mark_completed(
        self,
        scan_id: int,
        completion: ScanCompleted,
    ) -> None:
        ...

    def mark_cancelled(
        self,
        scan_id: int,
        completion: ScanCompleted,
    ) -> None:
        ...

    def mark_failed(
        self,
        scan_id: int,
        message: str,
    ) -> None:
        ...
```

The lifecycle service should own status transitions.

Do not scatter direct `scan.status = ...` assignments throughout GUI and scanner code.

---

# 16. Allowed Status Transitions

Enforce sensible transitions.

```text
pending → running
running → completed
running → completed_with_warnings
running → cancelled
running → failed
pending → cancelled
pending → failed
```

Disallow or warn on invalid transitions such as:

```text
completed → running
cancelled → completed
failed → completed
```

Status transition validation may live in the lifecycle service.

The database does not need a complex state machine, but invalid transitions should not happen silently.

---

# 17. Scan Persistence Flow

## 17.1 Before scanner start

The GUI controller or application service must:

1. Validate the `ScanRequest`.
2. Create a `scans` row.
3. Store status as `pending`.
4. Capture pre-scan volume information.
5. Change status to `running`.
6. Start the scanner worker.

The scanner should receive the durable `scan_id`.

Add `scan_id` to all events.

Example:

```python
class ScanStarted(BaseModel):
    scan_id: int
    started_at: datetime
    target_directory: Path
```

## 17.2 During folder discovery and analysis

Persist directory observations as structured scan data becomes available.

Two acceptable strategies:

### Strategy A: Persist after each analyzed directory

Advantages:

* minimal data loss on failure;
* simple event-driven persistence.

Disadvantages:

* many small transactions;
* slower for large scans.

### Strategy B: Persist in batches

Recommended.

Collect observations into batches such as:

```text
250
500
1000
```

Persist each batch in one transaction.

Requirements:

* Do not retain all observations in memory until a 700,000-folder scan finishes.
* Flush batches regularly.
* Update scan counters periodically.
* On cancellation, completed batches may remain.
* Cancelled scan data must be marked unusable for future comparison.

## 17.3 On warning

Persist each warning or warning batch.

A warning should reference the scan and, when known, the directory.

## 17.4 On completion

The controller or persistence coordinator must:

1. Flush pending observations.
2. Capture post-scan volume information.
3. Update final counters.
4. Set final scan status.
5. Set `completed_at`.
6. Commit.
7. Generate the existing text report.
8. Notify the GUI.

## 17.5 On cancellation

The application must:

1. Stop traversal promptly.
2. Flush or discard the current in-memory batch consistently.
3. Mark the scan `cancelled`.
4. Set `completed_at`.
5. Record final counters.
6. Retain already committed observations.
7. Never treat the scan as complete.

## 17.6 On failure

The application must:

1. Roll back the current transaction.
2. Open a fresh transaction if needed.
3. Mark the scan `failed`.
4. Store a concise failure message.
5. Preserve already committed batches.
6. Write the full exception to `application.log`.
7. Restore the GUI to an idle state.

---

# 18. Directory Upsert Behavior

When an observation is received:

1. Normalize the directory path.
2. Query or insert the `directories` row.
3. Preserve or update `display_path`.
4. Set `first_seen_scan_id` only on creation.
5. Update `last_seen_scan_id`.
6. Insert the `directory_observations` row.

Use an efficient upsert strategy compatible with SQLite.

Possible approaches:

* SQLAlchemy Core `INSERT ... ON CONFLICT`.
* Repository lookup with a directory identity cache.
* Batched path lookup followed by bulk insert.

Recommended for performance:

* Maintain an in-memory cache of normalized path to `directory_id` during the scan.
* Query existing IDs in batches.
* Bulk-insert missing directory identities.
* Bulk-insert observations.

Do not issue multiple ORM queries per directory for hundreds of thousands of directories.

---

# 19. Persistence Coordinator

Introduce an application-layer coordinator between scanner events and repositories.

Recommended responsibility:

```python
class ScanPersistenceCoordinator:
    def handle_event(self, event: ScanEvent) -> None:
        ...
```

It should:

* recognize scan lifecycle events;
* buffer directory observations;
* buffer warnings;
* flush batches;
* update counters;
* finalize scan status.

The scanner must not import SQLAlchemy or database repositories.

The scanner should remain independently testable.

The GUI controller may forward events to both:

* persistence coordinator;
* GUI presentation handlers.

Recommended flow:

```text
Scanner worker
    ↓
event queue
    ↓
GUI/application controller
    ├── persistence coordinator
    └── GUI view updates
```

Alternatively, persistence may occur in a dedicated consumer thread, but that is not required in Phase 1.

---

# 20. Scanner Event Changes

Extend Phase 0 events with the durable scan ID.

Add or retain enough information to persist each directory observation.

Recommended observation event:

```python
class FolderObserved(BaseModel):
    scan_id: int
    folder: Path
    matching_bytes: int
    direct_file_count: int
    matched_file_count: int
    observed_at: datetime
    warning_count: int = 0
```

A folder may be observed without exceeding the reporting threshold.

This distinction is essential.

The scanner must emit an observation for every successfully analyzed folder.

The existing `FolderMatched` event may remain for GUI display, or matching may be derived by the controller:

```python
if observation.matching_bytes >= request.growth_threshold_bytes:
    ...
```

Preferred design:

* Scanner emits `FolderObserved`.
* Controller or report service decides whether it matches the threshold.

This ensures the database contains every observed directory, not only flagged results.

---

# 21. Persist Every Observed Directory

Phase 1 must catalog every folder the scanner successfully analyzes.

For each scan, store:

* directory identity;
* matching bytes;
* direct file count;
* matched file count;
* observation timestamp;
* status;
* warning count.

Do not store only folders exceeding the threshold.

The threshold is a reporting filter, not a persistence filter.

This is required because Phase 2 must compare all folder measurements between scans.

---

# 22. Inaccessible and Disappeared Directories

When a discovered folder cannot be analyzed:

* Create or resolve its directory identity when possible.
* Persist a directory observation with an appropriate status.
* Persist a warning.
* Do not invent a zero-byte measurement as though the directory were successfully scanned.

Example statuses:

```text
inaccessible
disappeared
enumeration_failed
```

A zero-byte successful observation and an inaccessible observation must be distinguishable.

This distinction will matter when Phase 2 compares scans.

---

# 23. Scan Counters

Persist counters during and after scanning.

At minimum:

```text
folders_discovered
folders_analyzed
folders_matched
files_examined
warning_count
```

Counter semantics must be documented.

Example:

* `folders_discovered`: Number of folder paths added to the scan list.
* `folders_analyzed`: Number for which analysis was attempted.
* `folders_matched`: Number whose `matching_bytes` exceeded the threshold.
* `files_examined`: Number of direct child files statted.
* `warning_count`: Number of structured warnings emitted.

Do not derive all counters from database queries after every progress update.

Update them periodically.

---

# 24. Volume Observation

Capture disk usage for the target volume before and after the scan.

Use:

```python
shutil.disk_usage(target_directory)
```

or an equivalent Windows-safe implementation.

Store:

```text
total_bytes
free_bytes_before
free_bytes_after
```

Capture timestamps for both observations.

Requirements:

* Failure to capture disk usage must not fail the scan.
* Persist the failure as a partial or unavailable volume observation.
* Do not yet calculate unexplained disk growth.
* Do not imply that changes during the scan were caused by scanned folders.

---

# 25. Application Startup and Migration Behavior

At application startup:

1. Resolve the configured database path.
2. Verify that the database schema exists and is current.
3. Provide a clear message if migrations are required.

Two acceptable approaches:

### Explicit migration requirement

The user runs:

```powershell
uv run alembic upgrade head
```

The application refuses to run against an outdated schema.

### Automatic upgrade

The application invokes Alembic programmatically.

For Phase 1, explicit migrations are safer and easier to debug.

Recommended behavior:

* Automatically create the database directory.
* Detect missing or outdated schema.
* Display a clear instruction to run the migration.
* Do not silently create tables outside Alembic.

---

# 26. CLI Commands

Use Typer to add database inspection commands.

Add a script entry point:

```toml
[project.scripts]
folder-diff = "windows_folder_sizes_diff.app:main"
folder-diff-cli = "windows_folder_sizes_diff.cli:app"
```

A single Typer application that can also launch the GUI is acceptable.

## 26.1 `db-info`

```powershell
uv run folder-diff-cli db-info
```

Display:

* database path;
* database file size;
* current Alembic revision;
* total scan count;
* total directory count;
* total observation count;
* total warning count;
* newest scan timestamp.

Use Rich formatting.

## 26.2 `scans`

```powershell
uv run folder-diff-cli scans
```

Display:

```text
ID
Started
Completed
Target
Status
Folders
Matched
Warnings
```

Options:

```text
--limit
--status
--target
```

Default limit may be 20.

## 26.3 `scan-show`

```powershell
uv run folder-diff-cli scan-show 12
```

Display:

* scan metadata;
* configuration;
* counters;
* volume observation;
* warning summary;
* top matched directory observations.

This command does not calculate diffs.

## 26.4 `warnings`

```powershell
uv run folder-diff-cli warnings --scan-id 12
```

Display persisted warnings.

---

# 27. GUI Changes

Keep GUI changes minimal.

Add:

* current scan database ID;
* persisted scan status;
* completion warning count;
* optional button or menu item to view recent scan history.

The primary scan result list must retain its current behavior.

At scan start, display something similar to:

```text
Scan 14 started.
```

At completion:

```text
Scan 14 completed and was saved to the database.
```

For warnings:

```text
Scan 14 completed with 18 warnings.
```

For cancellation:

```text
Scan 14 was cancelled. Partial observations were retained.
```

For failure:

```text
Scan 14 failed. See the application log for details.
```

Do not add comparison or trend views yet.

---

# 28. Text Report Changes

Keep the existing text report format, but add durable identifiers.

Include:

```text
Scan ID
Scan UUID
Database status
Started time
Completed time
Final scan status
```

Continue listing only folders exceeding the configured threshold.

The report must clearly describe the metric as recent activity, not true growth.

Recommended wording:

```text
Recent file bytes matching the selected history window
```

Avoid:

```text
Actual folder growth
Net disk growth
Snapshot difference
```

The database is authoritative. The text report is a human-readable export.

---

# 29. Transaction Strategy

Use bounded transactions.

Recommended:

* One transaction to create and start the scan.
* Repeated batch transactions for directory identities and observations.
* Repeated batch transactions for warnings.
* One final transaction to finalize counters, volume observations, and status.

Do not keep one transaction open across an entire full-drive scan.

Long-running transactions can:

* grow the WAL;
* hold locks;
* increase rollback cost;
* make failures harder to recover from.

Each committed batch must remain associated with a scan whose status is still `running`.

---

# 30. Batch Insertion Requirements

Use bulk operations for observations.

Acceptable approaches:

```python
session.execute(insert(DirectoryObservation), rows)
```

or SQLAlchemy Core insert statements with lists of dictionaries.

Avoid:

```python
for observation in observations:
    session.add(observation)
    session.commit()
```

Recommended batch size:

```text
500–2000 observations
```

Make the batch size configurable internally if needed.

Benchmark before choosing a final default.

---

# 31. Concurrency and Thread Safety

Requirements:

* Scanner worker thread emits events only.
* GUI thread consumes events.
* Database sessions are thread-local by usage.
* No ORM object should be passed between threads.
* Pass primitive IDs or Pydantic models between components.
* SQLite write operations should be serialized through one persistence path.
* WAL mode should be enabled.
* Set a busy timeout.
* The GUI should remain responsive during batch persistence.

If persistence in the GUI event loop causes noticeable pauses, move persistence consumption to a dedicated worker in a later Phase 1 iteration.

Do not complicate the initial implementation unless profiling demonstrates a need.

---

# 32. Startup Recovery

On application startup, detect scans left in:

```text
pending
running
```

These may indicate the application or system terminated unexpectedly.

Mark them as:

```text
failed
```

or introduce:

```text
interrupted
```

Recommended Phase 1 approach:

* Add `interrupted` as a valid terminal status.
* Mark stale `pending` or `running` scans as `interrupted`.
* Set `completed_at` to recovery time.
* Add a failure or recovery note.

Terminal statuses:

```text
completed
completed_with_warnings
cancelled
failed
interrupted
```

Interrupted scans must never be considered complete.

---

# 33. Data Integrity Rules

Enforce these rules:

1. Every directory observation belongs to one scan.
2. Every directory observation references one directory.
3. A directory may have at most one observation per scan.
4. A scan UUID must be unique.
5. A normalized directory path must be unique.
6. Scan timestamps must be stored consistently.
7. Terminal scans must have `completed_at`.
8. A completed scan must not remain marked `cancel_requested`.
9. Warning counts should match persisted warnings after finalization.
10. Partial scans must retain a non-complete status.

Use UTC timestamps internally where practical.

Convert to local time for display.

---

# 34. Repository Responsibilities

Create focused repositories.

## `ScanRepository`

Responsibilities:

* create scan;
* retrieve scan;
* list scans;
* update counters;
* update status;
* recover stale scans.

## `DirectoryRepository`

Responsibilities:

* normalize and resolve directory identities;
* batch-fetch IDs;
* batch-insert missing directories;
* update `last_seen_scan_id`.

## `ObservationRepository`

Responsibilities:

* batch-insert directory observations;
* retrieve observations for a scan;
* retrieve top observations by matching bytes.

## `WarningRepository`

Responsibilities:

* batch-insert warnings;
* retrieve warnings by scan;
* count warnings.

## `VolumeObservationRepository`

Responsibilities:

* create or update scan volume information;
* retrieve volume information.

Repositories should not contain GUI formatting.

---

# 35. Service Boundaries

Recommended service structure:

```text
FolderScanner
- filesystem traversal
- emits typed events
- no database imports

ScanPersistenceCoordinator
- consumes scan events
- buffers writes
- calls repositories

ScanLifecycleService
- owns scan state transitions

TextScanReportWriter
- produces text report from completion data

GUI ScanController
- starts scan
- polls queue
- updates view
- forwards events to persistence

CLI
- reads persisted data
- formats through Rich
```

Keep persistence out of scanner internals.

---

# 36. Testing Requirements

All tests must use temporary SQLite databases.

Use SQLite file databases rather than only `:memory:` where WAL behavior or multiple connections matter.

## 36.1 Engine tests

Test:

* database file is created;
* foreign keys are enabled;
* WAL mode is enabled where supported;
* busy timeout is configured;
* sessions can be opened and closed.

## 36.2 Migration tests

Test:

* a fresh database upgrades to the current revision;
* expected tables exist;
* required indexes exist;
* migration can run twice safely;
* Alembic current revision matches expected head.

## 36.3 Scan lifecycle tests

Test:

* pending scan creation;
* pending to running;
* running to completed;
* running to completed-with-warnings;
* running to cancelled;
* running to failed;
* stale running scan becomes interrupted;
* invalid status transition is rejected.

## 36.4 Directory identity tests

Test:

* identical normalized paths reuse one directory row;
* path casing differences do not create duplicates;
* trailing separators do not create duplicates;
* display path is preserved;
* first-seen scan remains unchanged;
* last-seen scan updates.

## 36.5 Observation tests

Test:

* every analyzed folder creates one observation;
* below-threshold folders are persisted;
* above-threshold folders are persisted;
* duplicate observation for the same scan and directory is rejected;
* inaccessible folders have a non-success status;
* zero matching bytes are stored correctly.

## 36.6 Warning tests

Test:

* permission warnings persist;
* file-disappeared warnings persist;
* warning counts finalize correctly;
* warnings can reference a directory or only a path.

## 36.7 Cancellation tests

Test:

* scan status becomes cancelled;
* committed observations remain;
* pending batch handling is deterministic;
* cancelled scan has `completed_at`;
* cancelled scan is not reported as completed.

## 36.8 Failure tests

Test:

* current batch rolls back;
* prior committed batches remain;
* scan status becomes failed;
* failure message is stored;
* GUI/controller receives one terminal event.

## 36.9 Volume observation tests

Test:

* pre-scan disk usage persists;
* post-scan disk usage persists;
* capture failure does not fail the scan;
* partial volume status is recorded.

## 36.10 CLI tests

Test:

* `db-info` runs against a temporary database;
* `scans` lists stored scans;
* `scan-show` shows one scan;
* missing scan ID returns a clear error;
* warnings command handles an empty result.

---

# 37. Performance Validation

Create a synthetic test or benchmark with at least:

```text
10,000 directory observations
```

Validate:

* batch insert performance;
* directory identity reuse;
* memory does not grow without bound;
* no per-row commit behavior;
* scan history query remains responsive.

A full 700,000-directory benchmark is not required for automated tests, but the implementation should be designed for that scale.

---

# 38. Compatibility Requirements

Phase 1 must preserve:

* Existing GUI launch behavior.
* Existing scan request fields.
* Existing `config.yaml`.
* Existing threshold behavior.
* Existing history-window behavior.
* Existing cancellation control.
* Existing text reports.
* Existing diagnostic logs.
* Existing scanner tests from Phase 0.

No manual configuration migration should be required.

The only required setup action should be running the Alembic migration.

---

# 39. Documentation Requirements

Update `README.md` with:

## Database setup

```powershell
uv run alembic upgrade head
```

## Launch GUI

```powershell
uv run folder-diff
```

## Inspect database

```powershell
uv run folder-diff-cli db-info
```

## List scans

```powershell
uv run folder-diff-cli scans
```

Document:

* database file location;
* how to change the database path;
* meaning of scan statuses;
* that Phase 1 does not yet calculate true growth;
* how cancelled and interrupted scans are handled;
* how to reset a development database safely.

Do not recommend deleting the production database casually.

---

# 40. Acceptance Criteria

Phase 1 is complete when all of the following are true:

1. A fresh SQLite database can be created through Alembic.
2. The application detects whether the schema is current.
3. Every scan attempt creates a durable scan row.
4. Scan status transitions are persisted.
5. Every successfully analyzed folder creates a directory observation.
6. Folders below the threshold are still stored.
7. Directory paths are normalized and deduplicated case-insensitively.
8. Scan warnings are persisted.
9. Pre-scan and post-scan volume information are stored.
10. Cancelled scans retain partial observations and have a cancelled status.
11. Failed scans retain previously committed batches and have a failed status.
12. Interrupted scans are recovered at startup.
13. No SQLAlchemy session is shared across threads.
14. Observation writes are batched.
15. The GUI remains responsive during scans.
16. Existing text reports still work.
17. Reports include the durable scan ID.
18. The current timestamp-based metric is not mislabeled as true growth.
19. CLI commands can inspect the database and scan history.
20. All Phase 0 tests continue to pass.
21. All Phase 1 tests pass with:

```powershell
uv run pytest
```

22. The application is structurally ready for Phase 2 scan comparison.

---

# 41. Coding-Agent Assignment

Implement Phase 1 only.

Add SQLite persistence using SQLAlchemy 2.x and Alembic while preserving the existing timestamp-based scan logic.

Create durable tables for scans, directories, directory observations, scan warnings, and volume observations.

Persist every analyzed directory, including folders that do not exceed the reporting threshold. Treat the threshold only as a display and reporting filter.

Use one normalized path-based identity per directory. Windows path comparisons must be case-insensitive, and path formatting differences must not create duplicate directory rows.

Create a scan row before starting the scanner. Persist lifecycle states including pending, running, completed, completed-with-warnings, cancelled, failed, and interrupted.

Use batch inserts for directory identities, observations, and warnings. Do not commit one row at a time and do not hold one transaction open for the entire scan.

Do not import SQLAlchemy into the scanner. Add a persistence coordinator that consumes structured scan events and writes them through repositories.

Add the durable scan ID to scan events and text reports.

Capture total and free volume bytes before and after each scan, but do not perform reconciliation or attribute disk usage changes yet.

Add Typer and Rich commands for database information, scan history, scan details, and warnings.

Do not implement scan comparisons, actual folder growth, inclusive sizes, allocated sizes, file tracking, retention, or reparse-point resolution.

The completed Phase 1 application must preserve the current GUI and scan behavior while creating a complete database history suitable for Phase 2 snapshot comparisons.
