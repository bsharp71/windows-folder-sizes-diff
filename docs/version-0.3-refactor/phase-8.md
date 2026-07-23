# Phase 8 Technical Specification

Phase 8 completes the refactor by turning the analyzer into a maintainable daily system rather than a tool that gradually creates another uncontrolled storage problem.

Implement Phase 8 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 8. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Retention, Maintenance, Automation, and Long-Term Operation

**Project:** `windows-folder-sizes-diff`
**Phase:** 8 — Operational Hardening
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**CLI:** Typer and Rich
**GUI:** CustomTkinter
**Primary platform:** Windows 11
**Prerequisites:** Phases 0–7 completed

---

# 1. Objective

Prepare the application for reliable long-term daily use.

By the end of Phase 7, the application can:

* measure logical and allocated size;
* compare folder snapshots;
* distinguish direct and inclusive changes;
* avoid reparse-point duplication;
* reconcile folder findings against volume usage;
* track significant files;
* detect moves, renames, resizing, and hard links;
* generate GUI, CLI, and text reports.

Phase 8 must make that system operationally sustainable.

At the end of Phase 8, the application must support:

* controlled historical-data retention;
* safe deletion of obsolete scan details;
* protection of required baselines;
* database maintenance;
* database backup and restore;
* integrity checks;
* scheduled unattended scans;
* machine-readable exports;
* scan and trend history;
* recovery from interrupted maintenance;
* operational health reporting;
* configurable notifications;
* clear documentation for long-term use.

Phase 8 is the final planned refactor phase.

---

# 2. Prerequisite Behavior

Phase 7 is expected to provide:

* durable scan lifecycle records;
* directory snapshots;
* logical and allocated measurements;
* direct and inclusive hierarchy data;
* reparse-point records;
* volume observations;
* reconciliation records;
* tracked file identities;
* file observations and path history;
* hard-link-aware accounting;
* GUI and CLI reports;
* Alembic migrations;
* structured warnings;
* metric-specific baseline selection;
* scan and comparison confidence.

Phase 8 must preserve all existing historical and analytical behavior.

---

# 3. Phase 8 Scope

Implement:

* configurable retention policies;
* baseline-aware pruning;
* summary preservation after detailed-data deletion;
* optional daily, weekly, and monthly rollups;
* database compaction and optimization;
* database integrity checks;
* safe backup and restore;
* automated scheduled scans;
* lock and concurrency protection;
* unattended exit codes;
* JSON and CSV exports;
* trend-history queries and views;
* operational health checks;
* scan-run metadata;
* notification hooks;
* maintenance logs;
* GUI and CLI administration tools;
* documentation and tests.

Do not implement:

* cloud synchronization;
* multi-user collaboration;
* hosted database support;
* remote telemetry;
* external file-content uploads;
* continuous filesystem event monitoring;
* USN Journal ingestion;
* Volume Shadow Copy forensics;
* antivirus functionality;
* automatic deletion of user files.

The application may delete its own historical database records according to policy. It must never delete scanned filesystem content.

---

# 4. Operational Principles

Phase 8 must follow these principles.

## 4.1 The database is authoritative

Text, JSON, and CSV reports are exports.

They are not the primary source of historical truth.

## 4.2 Maintenance must be transactional

A failed retention, backup, or cleanup operation must not leave the database in a partially corrupted state.

## 4.3 Required baselines must be protected

The application must not delete detailed records still needed for valid comparisons.

## 4.4 Destructive operations must be explicit

Manual purge and reset commands require confirmation unless an explicit unattended flag is provided.

## 4.5 Scheduled scans must be non-interactive

Automation commands must return meaningful process exit codes and write durable logs.

## 4.6 Maintenance must not block normal use unnecessarily

Long operations should expose progress and support cancellation where safe.

## 4.7 Historical summaries should outlive raw detail

The application may remove old per-directory and per-file observations while retaining useful scan-level and trend-level summaries.

---

# 5. Retention Strategy

Support separate retention rules for different data classes.

Recommended defaults:

```yaml
Retention:
  DetailedDirectoryDays: 90
  DetailedFileDays: 30
  WarningDays: 180
  ReparseDetailDays: 180
  TextReportDays: 180
  PreserveScanSummaries: true
  PreserveMonthlyRollups: true
  PreserveAnomalousScans: true
  PreserveManualPins: true
```

Recommended Pydantic model:

```python
class RetentionSettings(BaseModel):
    detailed_directory_days: int | None = Field(default=90, ge=1)
    detailed_file_days: int | None = Field(default=30, ge=1)
    warning_days: int | None = Field(default=180, ge=1)
    reparse_detail_days: int | None = Field(default=180, ge=1)
    text_report_days: int | None = Field(default=180, ge=1)

    preserve_scan_summaries: bool = True
    preserve_monthly_rollups: bool = True
    preserve_anomalous_scans: bool = True
    preserve_manual_pins: bool = True
```

A value of `None` means retain indefinitely.

Do not use zero to mean unlimited.

---

# 6. Data Retention Classes

Classify stored data into these groups.

## 6.1 Scan summaries

Examples:

* scan ID;
* target;
* status;
* timestamps;
* counts;
* volume changes;
* reconciliation summary;
* confidence;
* algorithm versions.

Recommended retention:

```text
indefinite
```

unless the user explicitly purges them.

## 6.2 Directory detail

Examples:

* directory observations;
* direct and inclusive sizes;
* hierarchy details;
* directory-level diffs.

Recommended retention:

```text
90 days
```

## 6.3 File detail

Examples:

* file observations;
* path history;
* file-level diffs;
* hard-link groups.

Recommended retention:

```text
30 days
```

because file-level forensic data may be large and privacy-sensitive.

## 6.4 Warnings and errors

Recommended retention:

```text
180 days
```

## 6.5 Reparse-point detail

Recommended retention:

```text
180 days
```

## 6.6 Rollups

Recommended retention:

```text
indefinite
```

## 6.7 Human-readable exports

Managed separately from database retention.

---

# 7. Protected Scans

A scan must not have required detail deleted when it is protected.

Protection reasons include:

```text
latest successful logical baseline
latest successful allocated baseline
latest successful file-tracking baseline
current comparison baseline
manually pinned
anomalous scan
newest successful scan
maintenance dependency
```

Create a protection service.

Recommended interface:

```python
class ScanProtectionService:
    def get_protection_reasons(self, scan_id: int) -> list[str]:
        ...

    def is_protected(self, scan_id: int) -> bool:
        ...
```

Retention planning must query this service before deleting detailed data.

---

# 8. Manual Scan Pins

Allow the user to preserve a scan manually.

Add to `scans`:

```text
is_pinned             BOOLEAN NOT NULL DEFAULT 0
pin_label             TEXT NULL
pinned_at             DATETIME NULL
```

Examples:

```text
Before Windows update
Disk-loss incident
Known clean baseline
Notion cache investigation
```

Pinned scans must not be purged automatically.

The user may unpin them explicitly.

---

# 9. Anomalous Scan Preservation

Optionally preserve scans that meet anomaly criteria.

Recommended conditions:

* observed volume growth exceeds a configured threshold;
* unexplained growth exceeds a configured threshold;
* large allocated growth;
* low reconciliation confidence combined with high disk loss;
* unusual number of new large files;
* significant hard-link or file-identity anomalies;
* scan completed with critical warnings.

Recommended configuration:

```yaml
AnomalyPreservation:
  Enabled: true
  ObservedVolumeGrowthMB: 2048
  UnexplainedGrowthMB: 1024
  AllocationFailurePercent: 5.0
```

Mark qualifying scans:

```text
is_anomalous
anomaly_reasons
```

Do not automatically delete anomaly status when later scans become normal.

---

# 10. Database Changes

Create a new Alembic migration.

Do not edit earlier migrations.

## 10.1 `scans` additions

Add:

```text
is_pinned                    BOOLEAN NOT NULL DEFAULT 0
pin_label                    TEXT NULL
pinned_at                    DATETIME NULL

is_anomalous                 BOOLEAN NOT NULL DEFAULT 0
anomaly_reasons_json         TEXT NULL

directory_detail_retained    BOOLEAN NOT NULL DEFAULT 1
file_detail_retained         BOOLEAN NOT NULL DEFAULT 1
warning_detail_retained      BOOLEAN NOT NULL DEFAULT 1
reparse_detail_retained      BOOLEAN NOT NULL DEFAULT 1

retention_processed_at       DATETIME NULL
```

## 10.2 `scan_rollups`

Create:

```text
id                              INTEGER PRIMARY KEY
rollup_type                     TEXT NOT NULL
period_start                    DATETIME NOT NULL
period_end                      DATETIME NOT NULL

target_path                     TEXT NOT NULL
volume_id                       TEXT NULL

scan_count                      INTEGER NOT NULL
successful_scan_count           INTEGER NOT NULL
failed_scan_count               INTEGER NOT NULL

logical_net_delta_bytes         INTEGER NULL
allocated_net_delta_bytes       INTEGER NULL
observed_volume_delta_bytes     INTEGER NULL
unexplained_delta_bytes         INTEGER NULL

largest_growth_scan_id          INTEGER NULL
largest_unexplained_scan_id     INTEGER NULL

average_scan_duration_seconds   REAL NULL
average_confidence_score        REAL NULL
warning_count                   INTEGER NOT NULL DEFAULT 0

created_at                      DATETIME NOT NULL
algorithm_version               INTEGER NOT NULL DEFAULT 1
```

Allowed `rollup_type` values:

```text
daily
weekly
monthly
```

Recommended unique constraint:

```text
UNIQUE(rollup_type, period_start, target_path, volume_id)
```

## 10.3 `maintenance_runs`

Create:

```text
id                       INTEGER PRIMARY KEY
maintenance_uuid         TEXT UNIQUE NOT NULL
operation                TEXT NOT NULL
status                   TEXT NOT NULL

started_at               DATETIME NOT NULL
completed_at             DATETIME NULL

rows_examined            INTEGER NOT NULL DEFAULT 0
rows_deleted             INTEGER NOT NULL DEFAULT 0
files_deleted            INTEGER NOT NULL DEFAULT 0
bytes_before             INTEGER NULL
bytes_after              INTEGER NULL

dry_run                  BOOLEAN NOT NULL DEFAULT 0
failure_message          TEXT NULL
details_json             TEXT NULL
```

Operations may include:

```text
retention
vacuum
optimize
integrity_check
backup
restore_validation
rollup
report_cleanup
```

## 10.4 `scheduled_run_records`

Optional but recommended:

```text
id                       INTEGER PRIMARY KEY
run_uuid                 TEXT UNIQUE NOT NULL
trigger_type             TEXT NOT NULL
task_name                TEXT NULL
started_at               DATETIME NOT NULL
completed_at             DATETIME NULL
exit_code                INTEGER NULL
scan_id                  INTEGER NULL
status                   TEXT NOT NULL
message                  TEXT NULL
```

---

# 11. Rollup Strategy

Rollups summarize historical changes after detailed data expires.

## 11.1 Daily rollup

One row per target and calendar day.

May include:

* scan count;
* final successful scan;
* logical net change;
* allocated net change;
* observed volume change;
* unexplained change;
* largest growth event;
* warning count.

## 11.2 Weekly rollup

Aggregate daily rollups.

## 11.3 Monthly rollup

Aggregate daily or weekly rollups.

Monthly rollups should be preserved indefinitely by default.

## 11.4 Rollup correctness

Rollups must be reproducible from retained source data at creation time.

Record:

```text
algorithm version
period
source scan IDs or range
creation timestamp
```

Do not silently regenerate historical rollups using changed semantics without versioning.

---

# 12. Rollup Timing

Create or refresh rollups before deleting detailed source records.

Required retention sequence:

```text
identify eligible scans
→ calculate required rollups
→ validate rollups
→ delete eligible details
→ update scan retention flags
→ commit
```

If rollup creation fails, do not delete the source detail needed to create it.

---

# 13. Retention Planning

Create a retention planner.

Recommended interface:

```python
class RetentionPlanner:
    def build_plan(
        self,
        *,
        now: datetime,
        settings: RetentionSettings,
    ) -> RetentionPlan:
        ...
```

Recommended plan model:

```python
class RetentionPlan(BaseModel):
    directory_scan_ids: list[int]
    file_scan_ids: list[int]
    warning_scan_ids: list[int]
    reparse_scan_ids: list[int]
    protected_scan_ids: dict[int, list[str]]

    report_files_to_delete: list[Path]

    estimated_rows_to_delete: int
    dry_run: bool
```

The planner must not modify data.

Execution belongs in a separate service.

---

# 14. Retention Dry Run

All retention operations must support dry-run mode.

CLI example:

```powershell
uv run folder-diff-cli retention-plan
```

Display:

```text
Scans evaluated
Directory-detail scans eligible
File-detail scans eligible
Warnings eligible
Protected scans
Estimated rows removed
Report files removed
```

Dry run must be the default for manual retention planning.

Actual deletion requires:

```powershell
uv run folder-diff-cli retention-run --apply
```

or an equivalent explicit flag.

---

# 15. Retention Execution

Create a retention executor.

Recommended interface:

```python
class RetentionExecutor:
    def execute(
        self,
        plan: RetentionPlan,
    ) -> MaintenanceResult:
        ...
```

Requirements:

* write a `maintenance_runs` record;
* validate protected scans again immediately before deletion;
* process bounded batches;
* preserve scan summaries;
* update retention flags;
* support cancellation between batches;
* commit consistently;
* write diagnostic logs;
* report exact rows deleted.

Do not hold one giant transaction for millions of rows if bounded transactions can preserve consistency.

Use operation checkpoints.

---

# 16. Deletion Order

Respect foreign-key dependencies.

Recommended logical order:

```text
file diffs or derived file records
file observations
file paths no longer referenced
hard-link groups
unused file identities

directory comparison caches if present
directory observations
hierarchy detail if separate

scan warnings
reparse-point records

derived detail records
```

Do not delete stable identity rows that remain referenced by retained scans.

Remove orphaned identity rows only through an explicit cleanup step.

---

# 17. Baseline Preservation

At least one compatible successful baseline must remain for every active scan configuration and target.

Before pruning a scan, determine whether it is the newest retained usable baseline for:

```text
logical measurement
allocated measurement
file tracking
hard-link physical accounting
```

If deleting detail would remove the only usable baseline, protect it.

A newer scan may replace it only after that newer scan is complete, comparable, and retained.

---

# 18. Database Integrity Checks

Add an integrity-check service.

Use SQLite checks including:

```sql
PRAGMA quick_check;
PRAGMA foreign_key_check;
```

Support a deeper manual mode:

```sql
PRAGMA integrity_check;
```

CLI:

```powershell
uv run folder-diff-cli db-check
```

Options:

```text
--full
--json
```

Display:

* quick-check result;
* foreign-key violations;
* schema revision;
* orphaned rows;
* incomplete maintenance runs;
* stale running scans;
* database file size;
* WAL and shared-memory file sizes.

A failed integrity check must return a non-zero exit code.

---

# 19. Database Optimization

Support:

```sql
PRAGMA optimize;
```

Run this after substantial retention or on a configurable maintenance schedule.

Do not run `VACUUM` after every scan.

Recommended commands:

```powershell
uv run folder-diff-cli db-optimize
uv run folder-diff-cli db-vacuum
```

`db-vacuum` must:

* require sufficient free space;
* acquire an exclusive maintenance lock;
* warn that it may take time;
* record before and after database sizes;
* not run while a scan is active.

---

# 20. VACUUM Strategy

SQLite `VACUUM` may temporarily require substantial additional disk space.

Before running:

1. determine database file size;
2. determine free space on the database volume;
3. require a safety margin;
4. verify no active scan or maintenance process;
5. create a backup or recommend one;
6. run;
7. verify integrity after completion.

Recommended safety requirement:

```text
free space >= database size × 1.5
```

The exact factor may be configurable.

Do not begin if the requirement is not met.

---

# 21. WAL Maintenance

WAL mode may create:

```text
folder_sizes.db-wal
folder_sizes.db-shm
```

Add a safe checkpoint command:

```powershell
uv run folder-diff-cli db-checkpoint
```

Use an appropriate SQLite checkpoint mode.

Do not delete WAL files manually while the database may be active.

Expose WAL size in `db-info`.

---

# 22. Database Backup

Implement SQLite-consistent backup.

Preferred method:

* SQLite online backup API through Python’s `sqlite3.Connection.backup()`; or
* another safe database-copy mechanism.

Do not copy the database file directly while active unless all related WAL state is handled safely.

Recommended command:

```powershell
uv run folder-diff-cli db-backup
```

Options:

```text
--output PATH
--label TEXT
--compress
--verify
```

Default location:

```text
backups/
```

Recommended filename:

```text
folder_sizes_2026-07-23_14-30-00.db
```

---

# 23. Backup Metadata

Create an adjacent metadata file or embed metadata in a manifest.

Include:

```text
application version
database schema revision
backup timestamp
database size
scan count
newest scan ID
integrity-check result
optional label
checksum
```

Do not include file contents from the scanned filesystem.

---

# 24. Backup Verification

When `--verify` is used:

1. open the backup read-only;
2. run `quick_check`;
3. verify Alembic revision;
4. verify core table presence;
5. compare expected scan count;
6. calculate checksum;
7. record success or failure.

An unverified copy must not be labeled verified.

---

# 25. Database Restore

Provide a controlled restore workflow.

Recommended command:

```powershell
uv run folder-diff-cli db-restore PATH
```

Restore must:

1. require explicit confirmation;
2. verify the backup first;
3. stop or block active scans;
4. back up the current database automatically;
5. replace the database atomically where possible;
6. reopen and run integrity checks;
7. verify schema revision;
8. preserve recovery logs.

Do not overwrite the current database without creating a recovery copy unless an explicit override is supplied.

---

# 26. Maintenance Lock

Create a cross-process application lock.

Use it to prevent conflicting operations such as:

* two scans writing simultaneously;
* scan plus restore;
* scan plus vacuum;
* two retention runs;
* GUI scan plus scheduled CLI scan.

Recommended lock metadata:

```text
process ID
operation
started time
hostname
application version
```

The lock may use:

* a lock file;
* Windows named mutex;
* or another reliable cross-process mechanism.

A lock file alone must handle stale locks safely.

---

# 27. Stale Lock Recovery

A lock is stale only when:

* the recorded process no longer exists; or
* the lock exceeds a configured age and process validation fails.

Do not remove an active lock merely because it is old.

CLI:

```powershell
uv run folder-diff-cli lock-status
uv run folder-diff-cli lock-clear --stale-only
```

Manual forced clearing should require confirmation.

---

# 28. Scheduled Scan Command

Create a dedicated unattended command.

Example:

```powershell
uv run folder-diff-cli scheduled-scan
```

It must:

* load saved configuration;
* acquire the scan lock;
* migrate or validate schema according to policy;
* run the scan;
* persist results;
* run comparison;
* run reconciliation;
* generate configured exports;
* optionally run light maintenance;
* return a meaningful exit code;
* release the lock in all cases.

Do not require GUI interaction.

---

# 29. Process Exit Codes

Define stable exit codes.

Recommended:

```text
0   completed successfully
1   completed with warnings
2   configuration error
3   database unavailable
4   schema migration required
5   scan failed
6   scan cancelled
7   lock already held
8   comparison failed
9   reconciliation failed
10  maintenance failed
11  integrity check failed
12  export failed
```

Document these codes.

A scheduled scan that completes with warnings may return `1` while still retaining valid results.

---

# 30. Windows Task Scheduler Support

Provide documentation and optional helper commands.

Recommended CLI:

```powershell
uv run folder-diff-cli scheduler-command
```

This prints the exact command and working directory suitable for Task Scheduler.

Optional:

```powershell
uv run folder-diff-cli scheduler-install
```

If implemented, it must:

* use Windows Task Scheduler APIs or `schtasks`;
* display the proposed task before creating it;
* require confirmation;
* use the current Python/uv environment;
* set the correct working directory;
* configure log output;
* not store credentials in plaintext.

A helper script may be safer than automatic task creation.

---

# 31. Recommended Schedule

Suggested default:

```text
daily
after normal working hours
```

The application must not impose a schedule.

The user chooses the time.

Scheduled scans should avoid overlapping with known backup or update windows.

---

# 32. Scheduled-Run Logging

Write a dedicated log:

```text
logs/scheduled.log
```

Include:

```text
run UUID
start time
end time
exit code
scan ID
status
warnings
report paths
maintenance actions
```

Use rotating logs.

Do not rely only on Task Scheduler history.

---

# 33. Notification Hooks

Add optional local notification behavior.

Recommended settings:

```yaml
Notifications:
  Enabled: true
  OnSuccess: false
  OnWarnings: true
  OnFailure: true
  OnLargeUnexplainedGrowth: true
  LargeUnexplainedGrowthMB: 1024
```

Notification mechanisms may include:

* Windows toast notification;
* terminal output;
* writing a notification record;
* invoking a user-supplied command.

Do not implement external email or cloud messaging unless explicitly configured in a future feature.

---

# 34. User-Supplied Notification Command

Optionally support:

```yaml
NotificationCommand: ''
```

When configured, pass structured information safely.

Do not concatenate untrusted paths directly into a shell string.

Prefer:

```python
subprocess.run(
    [command, "--scan-id", str(scan_id), "--status", status],
    shell=False,
)
```

Document the security implications.

Disable by default.

---

# 35. Export Formats

Support:

```text
JSON
CSV
```

Text reports already exist.

Optional:

```text
JSON Lines
```

Exports should be generated from persisted database results, not scanner memory.

---

# 36. JSON Export

Recommended command:

```powershell
uv run folder-diff-cli export-json --scan-id 15
```

Export may include:

```text
scan summary
configuration metadata
folder comparison summary
top folder changes
reconciliation
file attribution summary
warnings
reparse summary
```

Options:

```text
--full
--include-files
--include-warnings
--output PATH
```

Default export should avoid enormous full forensic datasets unless `--full` is supplied.

---

# 37. CSV Export

Provide separate flat files when necessary.

Example:

```powershell
uv run folder-diff-cli export-csv --scan-id 15 --output exports/scan-15
```

Potential files:

```text
scan_summary.csv
folder_changes.csv
file_changes.csv
warnings.csv
reparse_points.csv
```

Do not force incompatible structures into one CSV.

Use UTF-8 with BOM only if required for Windows spreadsheet compatibility; otherwise use standard UTF-8 and document it.

---

# 38. Export Metadata

Every export should include or accompany:

```text
application version
schema revision
scan ID
baseline scan ID
export timestamp
measurement metric
algorithm versions
filters applied
detail retention state
```

An export produced after detailed data was purged must state which detail is unavailable.

---

# 39. Trend History

Add query services for historical trends.

Recommended metrics:

```text
free space
used space
logical net change
allocated net change
observed volume change
unexplained change
allocation coverage
identity coverage
scan duration
warning count
database size
```

The trend service should use:

* detailed scan summaries for recent periods;
* rollups for older periods.

---

# 40. Trend CLI

Add:

```powershell
uv run folder-diff-cli trends
```

Options:

```text
--metric free-space
--metric allocated-change
--metric unexplained-change
--days 30
--weekly
--monthly
--target PATH
--json
```

Default output may be a Rich table.

Do not require charting dependencies in Phase 8.

---

# 41. GUI History View

Add a history area or tab.

Recommended views:

```text
Recent scans
Disk-space trend
Unexplained-growth trend
Largest anomalies
Maintenance history
```

At minimum, provide tabular history.

A simple chart is optional only if it can be added without introducing unnecessary dependencies.

---

# 42. Scan History Table

Recommended columns:

```text
Date
Scan ID
Status
Target
Used Space
Observed Change
Allocated Change
Unexplained Change
Confidence
Duration
Warnings
Pinned
```

Allow filtering by:

```text
status
target
date range
anomalous
pinned
```

---

# 43. Operational Health Check

Create a health service.

Recommended command:

```powershell
uv run folder-diff-cli health
```

Check:

* configuration validity;
* database availability;
* schema revision;
* integrity status;
* stale active scans;
* active maintenance lock;
* last successful scan;
* last failed scan;
* database size;
* WAL size;
* free space on database volume;
* backup age;
* retention age;
* scheduled-run age;
* newest usable baseline;
* unresolved maintenance failures.

Recommended result states:

```text
healthy
warning
critical
```

Return a non-zero exit code for critical health.

---

# 44. Health Thresholds

Recommended configuration:

```yaml
Health:
  WarnIfNoSuccessfulScanHours: 48
  CriticalIfNoSuccessfulScanHours: 168
  WarnIfNoBackupDays: 14
  WarnIfDatabaseSizeGB: 10
  WarnIfWalSizeMB: 1024
  WarnIfFreeSpaceGB: 10
```

Thresholds must be configurable.

Do not treat defaults as universal truths.

---

# 45. Startup Recovery

Extend startup recovery to detect:

* interrupted scans;
* interrupted maintenance runs;
* stale locks;
* incomplete backups;
* incomplete restores;
* rollups created but not finalized;
* retention flags inconsistent with remaining detail.

Recovery should:

* mark abandoned operations interrupted;
* preserve available data;
* avoid repeating destructive work automatically;
* report required manual action.

---

# 46. Maintenance Lifecycle

Maintenance statuses:

```text
pending
running
completed
completed_with_warnings
cancelled
failed
interrupted
```

Use explicit allowed transitions.

Do not mark a partially completed destructive operation as fully completed.

Store checkpoint details where needed.

---

# 47. Automatic Light Maintenance

Optionally run low-risk maintenance after scheduled scans.

Recommended:

```text
PRAGMA optimize
stale-scan recovery
rollup refresh
retention planning
```

Do not automatically run:

```text
VACUUM
restore
large retention deletion
```

unless explicitly enabled.

---

# 48. Automatic Retention

Automatic retention may be enabled:

```yaml
AutomaticRetention:
  Enabled: false
  RunAfterScheduledScan: false
  RequireRecentBackupHours: 24
```

Recommended default:

```text
disabled
```

When enabled:

* require a recent verified backup;
* write a maintenance plan;
* preserve baselines and protected scans;
* process bounded batches;
* record results;
* notify on failure.

---

# 49. Database Size Reporting

Extend `db-info` to display:

```text
main database size
WAL size
SHM size
backup directory size
scan count
directory observation count
file observation count
oldest detailed scan
newest detailed scan
retention policy
last vacuum
last optimization
last backup
```

---

# 50. Schema Migration Policy

Scheduled unattended scans must not silently perform risky schema migrations by default.

Recommended policy:

```text
validate schema
if outdated:
    exit with code 4
    log migration instruction
```

Optional automatic migration may be added behind explicit configuration.

GUI startup should display a clear migration message.

---

# 51. Application Versioning

Add explicit application and data-format versions.

Store application version with:

```text
scans
maintenance runs
backups
exports
scheduled runs
```

This improves troubleshooting and historical interpretation.

Use the version from project metadata where practical.

---

# 52. Audit Logging

Maintenance and destructive actions must be auditable.

Record:

```text
operation
timestamp
user or process context where available
parameters
dry-run status
rows affected
files affected
result
failure
```

Do not store sensitive operating-system credentials.

---

# 53. Privacy Controls

File-level history may contain sensitive paths.

Add options to:

* exclude file-level detail from exports;
* purge file detail earlier than folder detail;
* redact user-defined path prefixes in exports;
* disable file tracking;
* omit warnings containing full paths from public exports.

Do not alter the authoritative database paths through redaction.

Redaction applies only to exports and presentation.

---

# 54. Export Redaction

Recommended configuration:

```yaml
Export:
  RedactPaths: false
  RedactionMappings:
    'C:\Users\brad': '<USER_HOME>'
```

Apply longest-prefix mapping first.

Clearly label exports as redacted.

Do not attempt irreversible database redaction in Phase 8.

---

# 55. Error Handling

Persist and report failures for:

```text
retention_plan
retention_execute
rollup_create
database_optimize
database_vacuum
database_backup
backup_verify
database_restore
integrity_check
export
scheduled_scan
notification
lock_acquire
lock_release
```

Maintenance failures must not invalidate existing scan data.

---

# 56. Service Boundaries

Recommended structure:

```text
maintenance/
├── retention.py
├── rollups.py
├── optimize.py
├── integrity.py
├── backup.py
├── restore.py
├── locks.py
└── health.py

automation/
├── scheduled_scan.py
├── task_scheduler.py
└── notifications.py

exporting/
├── json_export.py
├── csv_export.py
└── redaction.py

analysis/
└── trends.py
```

The scanner must not contain maintenance logic.

The GUI must not perform direct SQL deletion.

CLI commands should invoke services rather than contain business logic.

---

# 57. Suggested Domain Models

## Retention plan

```python
class RetentionPlan(BaseModel):
    created_at: datetime
    directory_scan_ids: list[int]
    file_scan_ids: list[int]
    warning_scan_ids: list[int]
    reparse_scan_ids: list[int]

    protected_scans: dict[int, list[str]]

    estimated_rows_to_delete: int
    estimated_report_files_to_delete: int
```

## Maintenance result

```python
class MaintenanceResult(BaseModel):
    maintenance_id: int
    operation: str
    status: str

    rows_examined: int
    rows_deleted: int
    files_deleted: int

    bytes_before: int | None
    bytes_after: int | None

    warnings: list[str]
    failure_message: str | None
```

## Health result

```python
class HealthCheckResult(BaseModel):
    status: str
    checks: list["HealthCheckItem"]
    checked_at: datetime
```

## Trend point

```python
class TrendPoint(BaseModel):
    period_start: datetime
    period_end: datetime
    metric: str
    value: int | float | None
    source: str
```

---

# 58. CLI Requirements

Add at least these commands:

```powershell
uv run folder-diff-cli retention-plan
uv run folder-diff-cli retention-run --apply

uv run folder-diff-cli scan-pin SCAN_ID
uv run folder-diff-cli scan-unpin SCAN_ID

uv run folder-diff-cli rollups-refresh

uv run folder-diff-cli db-check
uv run folder-diff-cli db-optimize
uv run folder-diff-cli db-checkpoint
uv run folder-diff-cli db-vacuum

uv run folder-diff-cli db-backup
uv run folder-diff-cli db-restore PATH

uv run folder-diff-cli lock-status

uv run folder-diff-cli scheduled-scan

uv run folder-diff-cli export-json --scan-id SCAN_ID
uv run folder-diff-cli export-csv --scan-id SCAN_ID

uv run folder-diff-cli trends
uv run folder-diff-cli health
```

Every destructive command must support help text and clear confirmation behavior.

---

# 59. GUI Requirements

Add an administration or maintenance view.

Recommended sections:

## Scan history

* recent scans;
* pinned scans;
* anomalies;
* retained-detail state.

## Database

* database size;
* WAL size;
* schema revision;
* integrity status.

## Retention

* current policy;
* estimated purge;
* protected scans;
* dry-run preview;
* apply button.

## Backup

* last backup;
* create backup;
* verify backup.

## Health

* last successful scan;
* scheduled-run status;
* warnings;
* critical issues.

## Exports

* JSON;
* CSV;
* redaction options.

Do not expose restore or force-lock clearing casually. Place them behind an advanced or administrative section.

---

# 60. Text Report and Logs

Scheduled and manual scan reports should include:

```text
Application version
Trigger type
Run UUID
Scan ID
Maintenance actions
Export paths
Notification result
```

Maintenance logs should be separate from scan reports.

Recommended:

```text
logs/application.log
logs/scheduled.log
logs/maintenance.log
```

Use rotating logs.

---

# 61. Testing Requirements

Use temporary SQLite databases, temporary directories, mocked clocks, and mocked Task Scheduler or notification services where needed.

## 61.1 Retention eligibility

Create old and recent scans.

Verify only eligible scans are selected.

## 61.2 Protected newest baseline

Verify the only usable baseline is not pruned.

## 61.3 Newer replacement baseline

Verify an older baseline becomes eligible after a newer retained compatible baseline exists.

## 61.4 Pinned scan

Pinned scan must not be purged.

## 61.5 Anomalous scan

An anomalous scan must be preserved when configured.

## 61.6 File-detail versus directory-detail retention

Verify file observations may be purged earlier while folder detail remains.

## 61.7 Summary preservation

After detail purge:

* scan summary remains;
* reconciliation remains;
* rollup remains;
* detail flags are updated.

## 61.8 Rollup before purge

Verify source detail is not deleted when rollup generation fails.

## 61.9 Dry run

Verify dry run changes no database rows or report files.

## 61.10 Retention execution

Verify rows are deleted in correct dependency order.

## 61.11 Interrupted retention

Simulate failure between batches.

Verify:

* maintenance run marked failed or interrupted;
* database remains consistent;
* future retry is possible.

## 61.12 Integrity check

Verify healthy temporary database passes.

## 61.13 Foreign-key violation reporting

Inject test corruption where feasible.

Verify violation is reported.

## 61.14 Backup creation

Verify backup contains expected scans and schema revision.

## 61.15 Backup verification

Verify corrupted backup fails verification.

## 61.16 Restore

Verify:

* current database is backed up;
* valid backup restored;
* integrity checked;
* invalid backup rejected.

## 61.17 VACUUM safety

Mock insufficient free space.

Expected:

```text
operation refused
```

## 61.18 WAL checkpoint

Verify checkpoint command completes safely.

## 61.19 Active lock

Second scan must not start while first lock is active.

## 61.20 Stale lock

Verify stale lock can be recovered only after process validation.

## 61.21 Scheduled scan success

Expected:

* scan completes;
* scheduled-run record created;
* exit code `0`.

## 61.22 Scheduled scan warnings

Expected exit code:

```text
1
```

with valid persisted scan.

## 61.23 Scheduled lock conflict

Expected exit code:

```text
7
```

## 61.24 Migration required

Expected exit code:

```text
4
```

## 61.25 JSON export

Verify structured output and metadata.

## 61.26 CSV export

Verify separate files and UTF-8 preservation.

## 61.27 Redaction

Verify configured path prefixes are replaced in exports only.

## 61.28 Detail already purged

Export must state unavailable detail rather than fail unexpectedly.

## 61.29 Daily rollup

Verify expected daily values.

## 61.30 Monthly rollup

Verify aggregation from daily records.

## 61.31 Trend query

Verify recent detail and older rollups produce one coherent series.

## 61.32 Health check

Test healthy, warning, and critical states.

## 61.33 Backup-age warning

Verify configurable threshold.

## 61.34 No-recent-scan warning

Verify thresholds.

## 61.35 Notification hook

Mock command execution.

Verify:

* argument list used safely;
* no shell interpolation;
* failure recorded without invalidating scan.

## 61.36 Report cleanup

Verify only reports older than policy are removed.

## 61.37 Historical compatibility

All Phase 0–7 records remain readable.

## 61.38 Large retention benchmark

Generate a substantial synthetic database.

Verify bounded memory and batched deletion.

## 61.39 Cancellation

Cancel retention between batches.

Verify consistent status and database integrity.

## 61.40 Complete test suite

All prior tests must continue to pass.

---

# 62. Performance Requirements

Retention and maintenance must support large databases.

Requirements:

* batch deletes;
* indexed eligibility queries;
* bounded memory use;
* no per-row commits;
* progress events;
* cancellable long operations;
* no GUI blocking;
* database aggregates for rollups;
* no loading all historical observations into Python unnecessarily.

Benchmark:

```text
1 million directory observations
500,000 file observations
1,000 scans
```

A smaller automated benchmark is acceptable, but the implementation must be designed for these scales.

---

# 63. Documentation Requirements

Update `README.md` with:

* retention policy;
* protected scans;
* manual pins;
* anomaly preservation;
* rollups;
* database optimization;
* backup and restore;
* integrity checks;
* scheduled scans;
* Task Scheduler setup;
* exit codes;
* exports;
* trend history;
* health checks;
* notification settings;
* privacy considerations;
* recovery procedures.

Include a recommended operating routine:

```text
Daily:
- scheduled scan
- report generation
- lightweight health check

Weekly:
- verified database backup
- integrity quick check
- rollup refresh

Monthly:
- retention review
- database optimization
- optional VACUUM when justified
```

---

# 64. Operational Runbook

Create a concise runbook covering:

## Scan fails

* inspect scheduled log;
* inspect application log;
* run health check;
* retry manually.

## Database locked

* inspect lock status;
* verify active process;
* clear only stale lock.

## Database integrity warning

* stop scans;
* create backup if possible;
* run full integrity check;
* restore verified backup if required.

## Disk critically low

* do not run VACUUM;
* create retention dry run;
* purge eligible file detail;
* checkpoint WAL;
* back up externally if possible.

## Migration required

* back up database;
* run Alembic upgrade;
* run integrity check;
* restart application.

---

# 65. Acceptance Criteria

Phase 8 is complete when all of the following are true:

1. Retention settings are configurable.
2. File, directory, warning, and report retention periods are independent.
3. Retention planning supports dry-run mode.
4. Protected baselines are not deleted.
5. The newest successful scan is protected.
6. Pinned scans are protected.
7. Anomalous scans can be protected.
8. Rollups are created before required source detail is deleted.
9. Scan summaries remain after detail pruning.
10. Retention flags accurately describe available detail.
11. Retention execution is batched and auditable.
12. Interrupted retention leaves the database consistent.
13. SQLite integrity checks are available.
14. Foreign-key checks are available.
15. Database optimization is available.
16. WAL checkpointing is available.
17. VACUUM performs safety checks.
18. Consistent database backups can be created.
19. Backups can be verified.
20. Restore creates a recovery copy of the current database.
21. Restore validates the replacement database.
22. Cross-process operation locking is implemented.
23. Stale locks are handled safely.
24. Scheduled scans run without GUI interaction.
25. Scheduled scans return documented exit codes.
26. Scheduled runs are logged durably.
27. Windows Task Scheduler instructions are documented.
28. JSON exports are supported.
29. CSV exports are supported.
30. Exports include schema and scan metadata.
31. Export redaction is supported.
32. Trend history can use detailed scans and rollups.
33. GUI exposes history and maintenance status.
34. CLI exposes retention, backup, health, trend, and export commands.
35. Health checks report warning and critical states.
36. Notification hooks are optional and safe.
37. Maintenance failures do not invalidate scan history.
38. Historical Phase 0–7 data remains readable.
39. No maintenance function deletes scanned filesystem content.
40. All prior tests continue to pass.
41. All Phase 8 tests pass with:

```powershell
uv run pytest
```

42. The application is suitable for unattended daily operation.

---

# 66. Coding-Agent Assignment

Implement Phase 8 only.

Add long-term operational support for the existing snapshot, comparison, reconciliation, and file-forensics system.

Implement configurable retention for:

* directory detail;
* file detail;
* warnings;
* reparse records;
* text reports.

Preserve scan summaries indefinitely by default.

Create protection rules so retention cannot delete:

* the newest successful scan;
* required logical, allocated, or file-tracking baselines;
* manually pinned scans;
* anomalous scans when preservation is enabled.

Add scan pinning and anomaly-preservation metadata.

Create daily, weekly, and monthly rollups. Generate and validate required rollups before deleting source detail.

Add a dry-run retention planner and a separate retention executor. Destructive retention must require an explicit apply flag and must run in bounded, auditable batches.

Add maintenance records for:

* retention;
* rollups;
* integrity checks;
* optimization;
* WAL checkpoints;
* VACUUM;
* backups;
* restore validation.

Add SQLite integrity checks using quick check, foreign-key check, and optional full integrity check.

Add safe database optimization, WAL checkpointing, and VACUUM. VACUUM must verify that adequate free space exists and that no scan or maintenance task is active.

Add consistent SQLite backup and restore services. Backups must include metadata and optional verification. Restore must verify the backup, create a recovery backup of the current database, replace it safely, and rerun integrity checks.

Add a cross-process operation lock to prevent overlapping scans, retention, backup, restore, and VACUUM operations. Handle stale locks only after validating that the owning process is no longer running.

Add a non-interactive scheduled-scan command suitable for Windows Task Scheduler. It must persist run records, write scheduled logs, release locks reliably, and return documented exit codes.

Add JSON and CSV exports generated from persisted results. Exports must include application version, schema revision, scan IDs, algorithm versions, filters, and detail-retention status. Add optional export-only path redaction.

Add trend queries for:

* used and free space;
* logical change;
* allocated change;
* observed volume change;
* unexplained change;
* scan duration;
* warning counts;
* measurement coverage.

Add GUI and CLI administration views for:

* scan history;
* pinned and anomalous scans;
* retention planning;
* database size;
* backups;
* integrity;
* health;
* trends;
* exports.

Add an operational health command that checks configuration, database integrity, schema revision, active locks, last successful scan, backup age, retention state, database size, WAL size, and free disk space.

Do not implement cloud synchronization, hosted databases, remote telemetry, continuous monitoring, USN Journal ingestion, VSS forensics, or automatic deletion of scanned filesystem content.

The completed Phase 8 application must be safe for unattended daily operation, preserve useful long-term history, control database growth, and provide clear recovery and maintenance procedures.
