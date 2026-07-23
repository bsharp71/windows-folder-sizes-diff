# Phase 2 Technical Specification

Implement Phase 2 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 2. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## True Snapshot-Based Folder Size Differences

**Project:** `windows-folder-sizes-diff`
**Phase:** 2 — True Snapshot Differences
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Prerequisites:** Phase 0 and Phase 1 completed

---

# 1. Objective

Replace the current modification-time-based reporting method with actual folder-size comparisons between completed scans.

At the end of Phase 2, the application must answer:

> How much did each folder’s directly contained file size change between the previous comparable scan and the current scan?

The application must stop treating recently modified file size as folder growth.

A file modified during the comparison period but remaining the same size must produce:

```text
0 bytes net change
```

A file added to a folder must increase that folder’s measured size.

A file deleted from a folder must reduce that folder’s measured size.

A file moved between two folders must produce:

```text
Source folder:      negative change
Destination folder: positive change
Overall net change: zero
```

Phase 2 introduces true logical-size snapshot differences.

It does not yet introduce inclusive recursive folder sizes, allocated size, NTFS physical identity, reparse-point resolution, or volume reconciliation.

---

# 2. Prerequisite Behavior

Phase 1 is expected to provide:

* SQLite persistence;
* SQLAlchemy models;
* Alembic migrations;
* durable scan records;
* stable path-based directory identities;
* one directory observation per analyzed directory per scan;
* persisted scan warnings;
* persisted volume observations;
* durable scan lifecycle states;
* CLI commands for scan history and database inspection;
* the existing CustomTkinter GUI;
* the existing timestamp-based `matching_bytes` observation.

Phase 2 must extend these capabilities rather than rebuilding them.

---

# 3. Phase 2 Scope

Implement:

* current logical size measurement for every directly analyzed folder;
* persistent direct logical-size snapshots;
* selection of the previous comparable completed scan;
* scan-to-scan folder differences;
* new, removed, grown, reduced, unchanged, and incomplete folder states;
* configuration compatibility rules;
* baseline creation behavior;
* comparison result models and services;
* updated GUI, CLI, and text reports;
* tests for true snapshot differences;
* deprecation of timestamp-based growth reporting.

Do not implement:

* inclusive recursive folder size;
* parent-child aggregation;
* allocated physical disk size;
* reparse-point target identity;
* junction deduplication beyond existing skip behavior;
* hard-link handling;
* file-level historical cataloging;
* move detection using file IDs;
* volume reconciliation;
* retention policies;
* scheduling;
* historical trend charts.

Those belong to later phases.

---

# 4. Current Behavior Being Replaced

The existing application calculates:

```text
The current size of direct child files whose creation or modification
timestamp is newer than a selected cutoff.
```

This value is stored as:

```text
matching_bytes
```

That value does not represent folder growth.

For example, if a 500 MB file is modified but remains 500 MB:

```text
Current timestamp-based result: 500 MB
Actual net folder growth:          0 MB
```

Phase 2 must make snapshot differences the primary reporting method.

The old timestamp-based value may remain in the database for historical compatibility, but it must no longer drive the main report.

---

# 5. Measurement Semantics

Phase 2 measures the logical size of files directly contained in each directory.

For a directory `D`:

```text
direct_logical_size(D) =
    sum(st_size of all direct child files successfully statted in D)
```

This measurement excludes files in descendant directories.

Example:

```text
C:\Example
├── root.bin          100 MB
└── Child
    └── child.bin     250 MB
```

Phase 2 measurements:

| Directory          | Direct logical size |
| ------------------ | ------------------: |
| `C:\Example`       |              100 MB |
| `C:\Example\Child` |              250 MB |

The root does not report 350 MB in Phase 2.

Recursive and inclusive size will be added in Phase 3.

---

# 6. Database Changes

Create a new Alembic migration for Phase 2.

Do not edit already-applied Phase 1 migration files.

## 6.1 Directory observation changes

Extend the existing per-directory observation table.

Preferred table name:

```text
directory_observations
```

Add:

```text
direct_logical_bytes    INTEGER NULL
measurement_status      TEXT NOT NULL DEFAULT 'pending'
files_examined          INTEGER NOT NULL DEFAULT 0
measurement_started_at  DATETIME NULL
measurement_completed_at DATETIME NULL
```

If Phase 1 already stores:

```text
direct_file_count
```

retain it and define the distinction clearly:

```text
files_examined:
    Number of direct files for which stat was attempted.

direct_file_count:
    Number of direct files successfully measured.
```

The existing `matching_bytes` field may remain temporarily.

Do not rename `matching_bytes` to growth.

## 6.2 Scan comparison metadata

Add fields to `scans` where needed:

```text
measurement_algorithm_version  INTEGER NOT NULL DEFAULT 2
baseline_scan_id               INTEGER NULL
comparison_status              TEXT NOT NULL DEFAULT 'not_started'
comparison_failure_message     TEXT NULL
```

Recommended foreign key:

```text
baseline_scan_id → scans.id
```

Suggested comparison statuses:

```text
not_started
baseline_created
running
completed
completed_with_warnings
not_comparable
failed
```

A scan can complete successfully even when no prior baseline exists.

## 6.3 Optional persisted comparison table

Persisted comparison results are optional in Phase 2.

The preferred initial design is to calculate differences from snapshot rows when requested.

Do not add a large comparison-results table unless the existing architecture clearly benefits from caching.

If comparison results are persisted, they must be reproducible from the underlying scan observations.

---

# 7. Scanner Changes

The scanner must calculate total current direct logical size for every analyzed folder.

For each directory:

1. Enumerate direct child entries.
2. For every direct file:

   * call `stat()` once;
   * add `st_size` to `direct_logical_bytes`;
   * increment direct file counters.
3. Continue recording warnings for inaccessible or disappearing files.
4. Emit a complete structured directory observation.

The measurement must include all successfully statted direct files, regardless of timestamp.

Do not filter by:

```text
st_mtime
st_ctime
creation time
history days
```

for the primary size measurement.

Recommended observation model:

```python
class FolderObservation(BaseModel):
    scan_id: int
    directory_path: Path

    direct_logical_bytes: int | None
    direct_file_count: int
    files_examined: int

    measurement_status: str
    warning_count: int

    observed_at: datetime
```

The scanner may temporarily continue calculating `matching_bytes` for compatibility, but this should be optional and must not determine the main report.

---

# 8. Measurement Status

Use explicit directory measurement states.

Recommended values:

```text
complete
complete_with_warnings
inaccessible
disappeared
partial
skipped
failed
```

## Complete

All direct entries were enumerated and all direct files were measured successfully.

## Complete with warnings

The folder was measured, but warnings occurred that did not make the resulting size materially incomplete.

Use this classification conservatively.

## Partial

Some files could not be measured, so the stored size may be understated.

## Inaccessible

The directory could not be enumerated.

## Disappeared

The path existed during discovery but no longer existed during analysis.

## Skipped

The path was intentionally skipped by policy.

## Failed

An unexpected folder-level error prevented a reliable measurement.

Do not store an inaccessible folder as a successful zero-byte folder.

---

# 9. Scan Completeness

Add or retain scan-level completeness metadata.

A scan must distinguish:

```text
completed
completed_with_warnings
cancelled
failed
interrupted
```

Only completed scans may automatically serve as comparison baselines.

Recommended baseline eligibility:

## Eligible by default

```text
completed
```

## Optionally eligible with downgraded confidence

```text
completed_with_warnings
```

## Never eligible

```text
cancelled
failed
interrupted
running
pending
```

A scan with substantial partial directory measurements should not silently become the preferred baseline.

---

# 10. Configuration Compatibility

Two scans may only be compared automatically when their measurement-producing settings are compatible.

Create a deterministic measurement configuration record or hash.

Include at least:

```text
normalized target path
measurement algorithm version
link-following policy
exclusion rules
path normalization version
file inclusion rules
```

Do not include display-only settings such as the reporting threshold unless they affect what is stored.

The reporting threshold does not determine scan comparability because every observed folder is stored.

`HistoryDays` must not be included in the Phase 2 measurement compatibility hash because timestamps no longer determine the stored direct size.

Recommended payload:

```python
payload = {
    "target_path": normalized_target_path,
    "measurement_algorithm_version": 2,
    "follow_symlinks": False,
    "exclusions": normalized_exclusions,
    "path_normalization_version": 1,
    "measurement_type": "direct_logical_size",
}
```

Serialize deterministically and hash with SHA-256.

---

# 11. Baseline Selection

Create a dedicated baseline selection service.

Recommended interface:

```python
class BaselineSelector:
    def find_previous_comparable_scan(
        self,
        current_scan_id: int,
    ) -> ScanRecord | None:
        ...
```

The default baseline must be:

> The most recent earlier baseline-eligible scan with the same normalized target path and compatible measurement configuration.

The query must exclude:

* the current scan;
* cancelled scans;
* failed scans;
* interrupted scans;
* scans using the old timestamp-only algorithm;
* scans with incompatible exclusions;
* scans with incompatible link policy;
* scans from another target root.

Order by successful completion time descending.

Do not simply use the immediately preceding scan ID.

---

# 12. First Baseline Behavior

When no comparable prior scan exists:

1. Complete and persist the current scan.
2. Mark:

```text
comparison_status = baseline_created
baseline_scan_id = NULL
```

3. Do not claim that any folder grew.
4. Display:

```text
Baseline scan created.

No previous comparable scan exists. Run another scan to calculate folder-size changes.
```

The first Phase 2-compatible scan establishes a baseline.

It is not itself a growth report.

---

# 13. Comparison Service

Create a dedicated scan difference service.

Recommended interface:

```python
class ScanDiffer:
    def compare(
        self,
        previous_scan_id: int,
        current_scan_id: int,
    ) -> ScanDiffReport:
        ...
```

The differ must compare all directory identities appearing in either scan.

Conceptually, use a full outer join.

SQLite does not provide a traditional full outer join, so acceptable strategies include:

* union of left joins;
* union of all directory IDs from both scans followed by joins;
* SQLAlchemy queries merged in Python;
* temporary comparison structures.

The implementation must handle:

* directories in both scans;
* directories only in the current scan;
* directories only in the previous scan.

Do not compare only currently existing folders.

---

# 14. Directory Difference Model

Recommended model:

```python
class DirectoryDiff(BaseModel):
    directory_id: int
    path: Path

    previous_direct_logical_bytes: int | None
    current_direct_logical_bytes: int | None
    delta_bytes: int | None

    previous_status: str | None
    current_status: str | None

    state: str
    confidence: str
    warning_count: int
```

Recommended directory states:

```text
grown
reduced
unchanged
new
removed
incomplete
not_comparable
```

---

# 15. Difference Rules

## 15.1 Directory present in both scans

When both measurements are complete enough to compare:

```text
delta =
    current_direct_logical_bytes
    - previous_direct_logical_bytes
```

Classification:

```text
delta > 0  → grown
delta < 0  → reduced
delta = 0  → unchanged
```

## 15.2 New directory

Directory exists only in the current scan.

When the current measurement is complete:

```text
previous size = 0
current size = measured size
delta = current size
state = new
```

A new empty directory has:

```text
delta = 0
state = new
```

## 15.3 Removed directory

Directory exists only in the previous scan.

When the previous measurement is complete:

```text
previous size = measured size
current size = 0
delta = -previous size
state = removed
```

A removed empty directory has:

```text
delta = 0
state = removed
```

## 15.4 Incomplete measurement

When either scan contains an inaccessible, partial, disappeared, skipped, or failed measurement that prevents a reliable comparison:

```text
delta = NULL
state = incomplete
```

Do not substitute zero.

Do not report a folder decrease merely because the current scan could not access it.

---

# 16. Timestamp Independence

Modification and creation timestamps must no longer affect the main difference calculation.

Examples:

## Same-size rewrite

Previous scan:

```text
file.dat = 500 MB
```

Current scan:

```text
file.dat = 500 MB
```

Expected folder delta:

```text
0 MB
```

## File increases

Previous:

```text
file.dat = 500 MB
```

Current:

```text
file.dat = 650 MB
```

Expected folder delta:

```text
+150 MB
```

## File decreases

Previous:

```text
file.dat = 500 MB
```

Current:

```text
file.dat = 200 MB
```

Expected folder delta:

```text
-300 MB
```

The file’s timestamps are irrelevant to these calculations.

---

# 17. File Moves

Phase 2 does not track individual file identity.

A file moved between directories should appear through folder totals.

Example:

Previous scan:

```text
Folder A = 1 GB
Folder B = 0 GB
```

Current scan:

```text
Folder A = 0 GB
Folder B = 1 GB
```

Expected:

```text
Folder A delta: -1 GB
Folder B delta: +1 GB
Net change:      0 GB
```

Do not label the operation as a confirmed move.

Move classification will require file-level identity in a later phase.

---

# 18. Comparison Confidence

Assign confidence to each directory comparison.

## High confidence

* both scans are completed;
* configurations are compatible;
* both directory measurements are complete;
* no relevant warnings affected either measurement.

## Medium confidence

* one or both measurements completed with minor warnings;
* the measured values are still believed complete;
* identity is path-based only.

## Low confidence

* one scan completed with substantial warnings;
* directory status suggests possible understatement;
* comparison relies on an explicit user override.

## Unavailable

* one measurement is partial, inaccessible, disappeared unexpectedly, skipped, or failed;
* scans are incompatible;
* no usable baseline exists.

Confidence should include a reason.

---

# 19. Scan Comparison Lifecycle

After a successful current scan:

1. Finalize all directory observations.
2. Mark the scan measurement complete.
3. Select the previous comparable baseline.
4. If none exists:

   * mark baseline created;
   * stop comparison processing.
5. If a baseline exists:

   * store `baseline_scan_id`;
   * set comparison status to `running`;
   * calculate differences;
   * set comparison status to `completed` or `completed_with_warnings`.
6. Generate GUI, CLI, and text output.

If comparison processing fails:

* retain the completed scan;
* mark comparison status `failed`;
* preserve the baseline ID;
* log the failure;
* allow the comparison to be retried later.

A comparison failure must not erase a valid scan snapshot.

---

# 20. Reporting Threshold

The growth threshold now applies to actual folder deltas.

For the primary positive-growth report:

```text
delta_bytes >= threshold_bytes
```

For reductions:

```text
delta_bytes <= -threshold_bytes
```

The threshold is a report filter only.

It must not control what observations are stored.

A user may change the reporting threshold after the scan and regenerate the report without rescanning.

---

# 21. Summary Metrics

Create scan comparison summary values.

Recommended fields:

```text
directories_compared
directories_grown
directories_reduced
directories_unchanged
directories_new
directories_removed
directories_incomplete

total_positive_growth_bytes
total_reduction_bytes
net_change_bytes
```

Calculate:

```text
total_positive_growth =
    sum(all positive comparable deltas)
```

```text
total_reduction =
    absolute value of sum(all negative comparable deltas)
```

```text
net_change =
    sum(all comparable deltas)
```

Because Phase 2 stores direct file sizes only, these folder measurements do not overlap and may be summed.

Phase 3 will retain direct totals while also adding overlapping inclusive values.

---

# 22. Important Scope Limitation

Phase 2 totals represent:

> Net change in the logical size of successfully measured direct files within the scanned directory tree.

They do not yet necessarily equal physical disk-space change.

Differences may remain because of:

* allocated size versus logical size;
* sparse files;
* compressed files;
* hard links;
* filesystem metadata;
* inaccessible paths;
* reparse-point aliases;
* system-managed storage;
* files changing during the scan.

Reports must not describe Phase 2 totals as authoritative physical disk consumption.

Use:

```text
Logical folder-size change
```

Avoid:

```text
Physical disk-space growth
Actual allocated growth
```

---

# 23. CLI Requirements

Extend the Typer CLI.

## 23.1 Run scan

If scan execution already exists:

```powershell
uv run folder-diff-cli scan
```

After completion, display either:

```text
Baseline created
```

or a true comparison summary.

## 23.2 Comparison report

Add:

```powershell
uv run folder-diff-cli report
```

Default behavior:

* use newest completed comparison;
* rank positive folder deltas descending;
* apply configured threshold;
* display current and previous scan IDs.

Recommended columns:

```text
Path
Previous Size
Current Size
Net Change
State
Confidence
```

## 23.3 Explicit comparison

Add:

```powershell
uv run folder-diff-cli compare CURRENT_SCAN_ID PREVIOUS_SCAN_ID
```

The command must validate compatibility.

Require an explicit override flag for incompatible scans:

```text
--force
```

Forced comparisons must be labeled low-confidence.

## 23.4 Reductions

Add:

```powershell
uv run folder-diff-cli report --reductions
```

## 23.5 Include unchanged or incomplete

Optional flags:

```text
--include-unchanged
--include-incomplete
--limit
--threshold-mb
```

## 23.6 Baseline information

Extend `scan-show` to display:

```text
baseline scan ID
comparison status
measurement algorithm version
configuration compatibility
```

---

# 24. GUI Requirements

Update the GUI to present true snapshot differences.

## 24.1 Remove history-window emphasis

`HistoryDays` no longer controls the primary result.

Recommended transition:

* hide or disable it in the main scan workflow;
* retain it only if legacy activity reporting remains accessible;
* clearly mark it as legacy behavior;
* remove it entirely in a later cleanup phase.

Do not show:

```text
Grew by X MB in the last N days
```

Use:

```text
Net change since scan 14
```

or:

```text
Changed by X MB since July 23, 2026
```

## 24.2 First compatible scan

Display:

```text
Baseline scan completed.

Run another scan to calculate folder-size changes.
```

## 24.3 Main result table

Recommended columns:

```text
Folder
Net Change
Previous Size
Current Size
State
Confidence
```

Default sorting:

```text
Net Change descending
```

## 24.4 Summary panel

Display:

```text
Current scan ID
Baseline scan ID
Baseline completion time
Folders compared
Folders grown
Folders reduced
New folders
Removed folders
Incomplete comparisons
Total positive growth
Total reductions
Net logical change
```

## 24.5 Incomplete folders

Incomplete comparisons should appear in a warning or separate view.

Do not mix unknown deltas into numeric totals.

---

# 25. Text Report Changes

Replace timestamp-based growth wording.

Recommended header:

```text
Folder Size Difference Report

Current scan:  15
Baseline scan: 14
Target:        C:\
Measurement:   Direct logical size
```

Recommended summary:

```text
COMPARISON SUMMARY
------------------------------------------------------------
Folders compared:          708,400
Folders grown:                  143
Folders reduced:                 89
New folders:                     21
Removed folders:                 14
Incomplete comparisons:          7

Total positive growth:       4.82 GB
Total reductions:            1.37 GB
Net logical change:          3.45 GB
```

Recommended result:

```text
C:\Users\brad\AppData\Roaming\Notion
    Previous direct size:  2.80 GB
    Current direct size:   4.29 GB
    Net change:           +1.49 GB
    State:                 Grown
    Confidence:            High
```

Include a limitation statement:

```text
These values represent logical file-size differences between snapshots.
They do not yet represent physical allocated disk-space differences.
```

---

# 26. Legacy Timestamp-Based Data

Retain Phase 1’s `matching_bytes` field for compatibility unless removing it is clearly safe.

Recommended behavior:

* stop displaying it in the primary GUI;
* stop using it in default reports;
* retain it in existing historical observations;
* optionally expose it through a legacy or diagnostic CLI command;
* mark it deprecated in code and documentation.

Do not delete historical database columns in Phase 2 unless a migration strategy is justified.

---

# 27. Baseline and Comparison Queries

Create repository queries for:

## Previous comparable scan

Filter by:

```text
completed status
same normalized target
same measurement algorithm
same configuration hash
completed before current scan
```

Order by:

```text
completed_at descending
```

## Directory observations for comparison

Retrieve only required columns:

```text
directory ID
normalized path
display path
direct logical bytes
measurement status
warning count
```

Avoid loading full ORM relationships for hundreds of thousands of rows.

Use streaming or batched query handling where needed.

---

# 28. Performance Requirements

The comparison must support hundreds of thousands of directory observations.

Requirements:

* avoid one query per directory;
* avoid ORM lazy-loading loops;
* select only required columns;
* use indexed joins;
* compare in SQL or bounded batches;
* do not load unnecessary warning bodies;
* allow report limits without calculating presentation models for every unchanged folder;
* calculate summary totals efficiently.

Required indexes should include:

```text
directory_observations(scan_id, directory_id)
directory_observations(directory_id, scan_id)
scans(normalized_target_path, configuration_hash, completed_at)
scans(status, completed_at)
```

Benchmark with at least:

```text
10,000–100,000 synthetic directory observations
```

A full production-drive benchmark is recommended before completion.

---

# 29. Concurrency and Scan Timing

The filesystem may change while a scan is running.

Phase 2 does not create an atomic filesystem snapshot.

Document that measurements represent each folder when it was observed during the scan.

Store:

```text
measurement_started_at
measurement_completed_at
```

where practical.

Do not claim that all folder values represent one exact instant.

If a directory changes during its enumeration and a reliable result cannot be obtained:

* mark it partial;
* emit a warning;
* exclude its delta from trusted totals.

---

# 30. Service Boundaries

Recommended structure:

```text
scanner/
- measures current direct logical folder size
- emits observations
- no historical comparison logic

db/
- stores scans and directory observations

analysis/baseline.py
- selects previous comparable scan

analysis/differ.py
- compares directory observations
- calculates summary metrics

reporting/
- formats comparison results

gui/
- presents results
- does not calculate deltas

cli/
- queries and displays comparisons
```

Do not place comparison logic inside:

* the scanner;
* SQLAlchemy ORM models;
* GUI widget handlers;
* text report templates.

---

# 31. Suggested Domain Models

## Baseline result

```python
class BaselineSelection(BaseModel):
    current_scan_id: int
    baseline_scan_id: int | None
    status: str
    reason: str
```

## Directory diff

```python
class DirectoryDiff(BaseModel):
    directory_id: int
    path: Path

    previous_bytes: int | None
    current_bytes: int | None
    delta_bytes: int | None

    state: str
    confidence: str
    confidence_reason: str | None = None
```

## Comparison summary

```python
class ScanDiffSummary(BaseModel):
    previous_scan_id: int
    current_scan_id: int

    directories_compared: int
    directories_grown: int
    directories_reduced: int
    directories_unchanged: int
    directories_new: int
    directories_removed: int
    directories_incomplete: int

    total_positive_growth_bytes: int
    total_reduction_bytes: int
    net_change_bytes: int
```

## Full report

```python
class ScanDiffReport(BaseModel):
    summary: ScanDiffSummary
    results: list[DirectoryDiff]
    generated_at: datetime
    measurement_type: str = "direct_logical_size"
```

---

# 32. Testing Requirements

Use temporary folders and temporary SQLite databases.

## 32.1 Baseline creation

Run one Phase 2 scan.

Expected:

```text
comparison status = baseline_created
no growth report generated
```

## 32.2 No filesystem changes

Run two scans without changing files.

Expected:

```text
all comparable deltas = 0
net change = 0
```

## 32.3 New file

Baseline:

```text
Folder size = 0
```

Current:

```text
Create 100 MB file
```

Expected:

```text
folder delta = +100 MB
```

## 32.4 File grows

Baseline:

```text
file = 100 MB
```

Current:

```text
file = 150 MB
```

Expected:

```text
folder delta = +50 MB
```

## 32.5 File shrinks

Baseline:

```text
file = 150 MB
```

Current:

```text
file = 75 MB
```

Expected:

```text
folder delta = -75 MB
```

## 32.6 Same-size rewrite

Rewrite a file without changing its size.

Expected:

```text
folder delta = 0
```

This is a required regression test against the old timestamp behavior.

## 32.7 File deleted

Baseline:

```text
file = 100 MB
```

Current:

```text
file removed
```

Expected:

```text
folder delta = -100 MB
```

## 32.8 File moved

Move a 100 MB file from Folder A to Folder B.

Expected:

```text
Folder A = -100 MB
Folder B = +100 MB
Net change = 0
```

Do not require confirmed move classification.

## 32.9 New folder

Create a new folder with a 100 MB direct file.

Expected:

```text
state = new
delta = +100 MB
```

## 32.10 Removed folder

Remove a folder containing a 100 MB direct file.

Expected:

```text
state = removed
delta = -100 MB
```

## 32.11 New empty folder

Expected:

```text
state = new
delta = 0
```

## 32.12 Removed empty folder

Expected:

```text
state = removed
delta = 0
```

## 32.13 Inaccessible current folder

Baseline measurement is complete.

Current scan cannot access the folder.

Expected:

```text
state = incomplete
delta = NULL
```

It must not report the full previous size as deleted.

## 32.14 Inaccessible baseline folder

Current scan is complete, but baseline measurement was incomplete.

Expected:

```text
state = incomplete
delta = NULL
```

## 32.15 Cancelled scan exclusion

Create:

```text
completed scan
cancelled scan
completed scan
```

Expected:

The newest completed scan compares against the earlier completed scan, not the cancelled scan.

## 32.16 Configuration mismatch

Change an exclusion or measurement-affecting setting.

Expected:

```text
automatic baseline not selected
new baseline created
```

or comparison marked incompatible.

## 32.17 Reporting-threshold change

Run scans with different reporting thresholds but identical measurement settings.

Expected:

Scans remain comparable because threshold does not affect persisted measurements.

## 32.18 Old Phase 1 scan

Attempt to compare against a timestamp-only Phase 1 scan.

Expected:

```text
not comparable
```

The first Phase 2 scan becomes the new baseline.

## 32.19 Summary total

Create several positive and negative folder changes.

Verify:

```text
positive growth total
reduction total
net change
```

are mathematically correct.

## 32.20 Comparison failure

Simulate a comparison service exception.

Expected:

* scan remains completed;
* comparison status becomes failed;
* scan data remains available;
* comparison can be retried.

---

# 33. Migration and Historical Data

The Phase 2 migration must preserve all Phase 1 records.

Existing Phase 1 observations do not contain reliable full direct-size snapshots unless Phase 1 already stored them independently.

Do not reinterpret `matching_bytes` as direct folder size.

Recommended migration behavior:

* add new columns as nullable;
* mark old scans with measurement algorithm version `1`;
* mark new Phase 2 scans with version `2`;
* exclude algorithm version `1` scans from automatic baseline selection;
* retain old scan history for reference.

Do not attempt to derive historical folder size from the timestamp-based metric.

---

# 34. Compatibility Requirements

Phase 2 must preserve:

* Phase 0 modular architecture;
* Phase 1 database history;
* scan IDs and UUIDs;
* scan lifecycle behavior;
* cancellation;
* interruption recovery;
* persisted warnings;
* volume observations;
* existing configuration loading;
* GUI responsiveness;
* CLI database inspection;
* existing text report files.

The meaning of the primary report intentionally changes from recent file activity to true snapshot difference.

This change must be clearly documented.

---

# 35. Documentation Requirements

Update `README.md` with:

* explanation of baseline scans;
* explanation of direct logical folder size;
* explanation of scan-to-scan comparison;
* first-run behavior;
* compatible baseline rules;
* difference between logical size and allocated size;
* limitations caused by inaccessible paths;
* explanation that recursive inclusive size is deferred to Phase 3;
* updated GUI and CLI commands;
* deprecation of `HistoryDays`.

Include a clear example:

```text
Scan 1:
C:\Data = 1.0 GB

Scan 2:
C:\Data = 1.4 GB

Reported direct logical change:
+0.4 GB
```

Also include:

```text
Changing a file without changing its size produces zero folder growth.
```

---

# 36. Acceptance Criteria

Phase 2 is complete when all of the following are true:

1. Every successfully analyzed folder stores its current direct logical size.
2. Current measurements include all direct files, regardless of timestamp.
3. The old history-window metric no longer drives the primary report.
4. The first compatible scan creates a baseline without claiming growth.
5. A later compatible scan automatically selects the previous successful baseline.
6. Cancelled, failed, and interrupted scans are not selected as baselines.
7. Configuration compatibility is validated.
8. Reporting-threshold changes do not invalidate comparability.
9. Phase 1 timestamp-only scans are not treated as valid Phase 2 baselines.
10. Same-size file modifications produce zero delta.
11. File growth produces only the actual size increase.
12. File shrinkage produces the actual size reduction.
13. New files and directories are reported correctly.
14. Deleted files and directories are reported correctly.
15. File moves produce offsetting folder changes and zero net logical change.
16. Inaccessible folders produce unknown deltas rather than false growth or deletion.
17. Positive growth, reduction, and net totals are calculated correctly.
18. Comparison logic is outside the scanner and GUI.
19. The GUI displays true net change.
20. The CLI supports comparison reports.
21. Text reports identify both current and baseline scan IDs.
22. Reports clearly label the metric as logical size.
23. Existing Phase 1 database records remain readable.
24. A comparison failure does not invalidate a completed scan.
25. All previous tests continue to pass.
26. All Phase 2 tests pass with:

```powershell
uv run pytest
```

27. The application is prepared for Phase 3 direct and inclusive hierarchy measurements.

---

# 37. Coding-Agent Assignment

Implement Phase 2 only.

Replace the timestamp-based recent-file metric as the primary reporting method with true scan-to-scan differences.

For every successfully analyzed directory, calculate and persist the logical size of all files directly contained in that directory. Do not filter files by modification time or creation time.

Add a measurement algorithm version so new Phase 2 scans are not automatically compared with old Phase 1 timestamp-only scans.

Create a baseline-selection service that chooses the most recent earlier completed scan with the same normalized target and compatible measurement configuration. Do not select cancelled, failed, interrupted, partial, or incompatible scans.

When no comparable scan exists, save the current scan as the new baseline and do not report growth.

Create a comparison service that compares all directories present in either scan and classifies each as:

* grown;
* reduced;
* unchanged;
* new;
* removed;
* incomplete;
* not comparable.

Calculate:

```text
delta =
    current direct logical bytes
    - previous direct logical bytes
```

Do not substitute zero when a measurement is inaccessible or incomplete.

Use the configured threshold only as a report filter. Persist every directory measurement regardless of threshold.

Update the GUI, CLI, and text reports to show:

* current scan;
* baseline scan;
* previous direct size;
* current direct size;
* net logical change;
* state;
* confidence.

Deprecate the history-window language and do not describe timestamp-based activity as folder growth.

Do not implement inclusive recursive folder size, allocated size, file identity, reparse-point resolution, hard-link handling, volume reconciliation, retention, scheduling, or file-level move detection.

The completed Phase 2 application must report actual logical folder-size differences between comparable scans and must produce zero growth when a file is modified without changing size.
