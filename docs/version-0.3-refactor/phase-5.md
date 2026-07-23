# Phase 5 Technical Specification

Implement Phase 5 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 5. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Volume Reconciliation and Unexplained Disk Usage

**Project:** `windows-folder-sizes-diff`
**Phase:** 5 — Volume Reconciliation
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Windows integration:** pywin32
**Prerequisites:** Phases 0–4 completed

---

# 1. Objective

Add volume-level reconciliation so the application can compare:

1. the actual change in used space on the scanned volume; and
2. the net folder-size change explained by the directory snapshots.

The application currently identifies folder-level logical-size changes. It does not yet tell the user whether those changes account for the actual loss or gain of free disk space.

At the end of Phase 5, the application must answer:

> How much did total used space on the volume change, how much of that change is explained by scanned folders, and how much remains unexplained?

Example:

```text
Observed volume growth:       10.20 GB
Explained folder growth:       7.85 GB
Unexplained/system growth:     2.35 GB
```

The application must not imply that unexplained growth is an error. It may represent:

* files changing while the scan was running;
* inaccessible directories;
* logical-versus-allocated-size differences;
* pagefile or hibernation changes;
* restore points or shadow copies;
* filesystem metadata;
* sparse or compressed files;
* system-managed storage;
* content outside the scan target;
* another process modifying the disk during the scan.

Phase 5 introduces reconciliation and confidence reporting. It does not yet introduce allocated-size measurement.

---

# 2. Prerequisite Behavior

Phase 4 is expected to provide:

* durable scan records;
* direct logical folder measurements;
* true scan-to-scan deltas;
* parent-child hierarchy;
* inclusive folder measurements;
* non-overlapping direct totals;
* reparse-point detection;
* junction and alias protection;
* duplicate-target prevention;
* compatible baseline selection;
* volume observations captured before and after scans;
* GUI, CLI, and text reports;
* structured warnings and confidence states.

Phase 5 must extend those capabilities without changing their core meaning.

---

# 3. Phase 5 Scope

Implement:

* authoritative volume-space observations;
* used-space calculation;
* observed volume-space delta between comparable scans;
* explained logical folder delta;
* unexplained delta;
* reconciliation status and confidence;
* target-scope awareness;
* scan-timing metadata;
* reconciliation warnings;
* GUI, CLI, and report updates;
* database migration;
* automated tests.

Do not implement:

* allocated physical file size;
* pagefile-specific measurement;
* hibernation-file-specific measurement;
* Volume Shadow Copy enumeration;
* restore-point analysis;
* NTFS metadata inspection;
* hard-link deduplication;
* file-level forensics;
* sparse-file analysis;
* retention policies;
* scheduling.

Those belong to later phases.

---

# 4. Core Reconciliation Model

For a volume:

```text
used_bytes =
    total_bytes - free_bytes
```

For two comparable scans:

```text
observed_volume_delta =
    current_used_bytes - previous_used_bytes
```

The folder-level explained change is:

```text
explained_folder_delta =
    sum of all comparable direct logical-size deltas
```

Because direct folder measurements are non-overlapping, they may be summed safely.

The unexplained difference is:

```text
unexplained_delta =
    observed_volume_delta - explained_folder_delta
```

Example:

```text
Previous used space:       400.00 GB
Current used space:        410.00 GB
Observed volume delta:     +10.00 GB

Explained folder delta:     +7.50 GB
Unexplained delta:          +2.50 GB
```

---

# 5. Terminology

Use these terms consistently.

## 5.1 Observed volume change

The change in total used bytes on the volume between comparable scans.

Preferred field name:

```text
observed_volume_delta_bytes
```

## 5.2 Explained folder change

The sum of comparable direct logical-size deltas within the scan scope.

Preferred field name:

```text
explained_folder_delta_bytes
```

## 5.3 Unexplained change

The difference between observed volume change and explained folder change.

Preferred field name:

```text
unexplained_delta_bytes
```

## 5.4 Reconciliation coverage

The fraction of observed volume change accounted for by folder measurements.

Recommended calculation when meaningful:

```text
coverage_ratio =
    explained_folder_delta_bytes
    / observed_volume_delta_bytes
```

Coverage ratios must be interpreted carefully when either value is zero or has the opposite sign.

## 5.5 Scan scope

The directory tree intentionally included in the scan.

Example:

```text
C:\
```

or:

```text
C:\Users\brad
```

A partial-volume scan cannot be expected to reconcile completely with whole-volume usage.

---

# 6. Important Scope Rule

Volume reconciliation is only authoritative when the scan target covers the entire volume.

For example:

```text
Target: C:\
```

may support full-volume reconciliation.

But:

```text
Target: C:\Users\brad
```

does not cover:

* Windows;
* Program Files;
* ProgramData;
* pagefile;
* hibernation file;
* System Volume Information;
* other users;
* filesystem metadata.

Therefore, add a scope classification:

```text
full_volume
partial_volume
cross_volume
unknown
```

Reconciliation must be interpreted differently by scope.

## Full-volume scan

May compare explained folder changes against total volume change.

## Partial-volume scan

May show both values, but must state:

```text
The scan target does not cover the entire volume.
Unexplained change includes all activity outside the target tree.
```

## Cross-volume scan

Full reconciliation is unavailable unless each volume is reconciled independently.

## Unknown

Do not claim complete reconciliation.

---

# 7. Database Changes

Create a new Alembic migration.

Do not modify prior migration files.

## 7.1 `volume_observations` changes

Phase 1 may already contain one volume observation per scan.

Extend it with:

```text
volume_id                  TEXT NULL
mount_point                TEXT NULL
filesystem_name            TEXT NULL

total_bytes_before         INTEGER NULL
free_bytes_before          INTEGER NULL
used_bytes_before          INTEGER NULL

total_bytes_after          INTEGER NULL
free_bytes_after           INTEGER NULL
used_bytes_after           INTEGER NULL

captured_before_at         DATETIME NULL
captured_after_at          DATETIME NULL

capture_duration_seconds   REAL NULL
scope_type                 TEXT NOT NULL DEFAULT 'unknown'
status                     TEXT NOT NULL DEFAULT 'pending'
warning_count              INTEGER NOT NULL DEFAULT 0
```

If prior fields include:

```text
total_bytes
free_bytes_before
free_bytes_after
```

migrate carefully without deleting historical information.

## 7.2 `scan_reconciliations` table

Create a dedicated reconciliation table.

Recommended schema:

```text
id                               INTEGER PRIMARY KEY
current_scan_id                  INTEGER NOT NULL UNIQUE
baseline_scan_id                 INTEGER NOT NULL

volume_id                        TEXT NULL
scope_type                       TEXT NOT NULL

previous_used_bytes              INTEGER NULL
current_used_bytes               INTEGER NULL
observed_volume_delta_bytes      INTEGER NULL

explained_folder_delta_bytes     INTEGER NULL
unexplained_delta_bytes          INTEGER NULL

comparable_directory_count       INTEGER NOT NULL DEFAULT 0
incomplete_directory_count       INTEGER NOT NULL DEFAULT 0
excluded_directory_count         INTEGER NOT NULL DEFAULT 0

coverage_ratio                   REAL NULL
reconciliation_status            TEXT NOT NULL
confidence                       TEXT NOT NULL
confidence_reason                TEXT NULL

calculated_at                    DATETIME NOT NULL
algorithm_version                INTEGER NOT NULL DEFAULT 1
warning_count                    INTEGER NOT NULL DEFAULT 0
```

Recommended foreign keys:

```text
current_scan_id → scans.id
baseline_scan_id → scans.id
```

## 7.3 Reconciliation statuses

Use:

```text
not_started
running
completed
completed_with_warnings
partial_scope
not_available
failed
```

## 7.4 Indexes

Add:

```text
scan_reconciliations(current_scan_id)
scan_reconciliations(baseline_scan_id)
scan_reconciliations(reconciliation_status)
volume_observations(volume_id)
```

---

# 8. Volume Identity

Create a dedicated volume information provider.

Recommended interface:

```python
class VolumeInfoProvider(Protocol):
    def inspect(self, path: Path) -> VolumeInfo:
        ...
```

Recommended model:

```python
class VolumeInfo(BaseModel):
    root_path: Path
    volume_id: str | None
    mount_point: Path | None
    filesystem_name: str | None

    total_bytes: int | None
    free_bytes: int | None
    used_bytes: int | None

    captured_at: datetime
    status: str
    warning: str | None = None
```

Use Windows APIs or `shutil.disk_usage()` where appropriate.

pywin32 may be used for:

* volume serial number;
* volume root;
* filesystem name;
* mount-point information.

Do not identify a volume only by drive letter.

A drive letter may be reassigned.

Preferred identity should include a volume serial or stable volume identifier when available.

---

# 9. Capture Timing

Volume usage must be captured at controlled points.

For every scan:

## Before scan

Capture volume state immediately before filesystem traversal begins.

Store:

```text
captured_before_at
total_bytes_before
free_bytes_before
used_bytes_before
```

## After scan

Capture volume state immediately after scanning and snapshot persistence complete.

Store:

```text
captured_after_at
total_bytes_after
free_bytes_after
used_bytes_after
```

These observations describe the volume during the scan window.

However, the comparison between scans should use a consistent point.

Recommended baseline comparison:

```text
previous volume state =
    previous scan's after-scan observation

current volume state =
    current scan's after-scan observation
```

This produces:

```text
observed_volume_delta =
    current.after.used
    - previous.after.used
```

Use after-scan observations because they align most closely with persisted completed snapshots.

---

# 10. Intra-Scan Volume Change

Also calculate the volume change during the scan itself:

```text
intra_scan_delta =
    used_bytes_after - used_bytes_before
```

This is useful because large activity during a long scan reduces reconciliation confidence.

Example:

```text
Used space changed by 3.2 GB while the scan was running.
```

Add:

```text
intra_scan_delta_bytes
```

either to `volume_observations` or calculated dynamically.

If the intra-scan change is large relative to the final observed comparison delta, downgrade reconciliation confidence.

---

# 11. Full-Volume Target Detection

Create a deterministic function:

```python
def classify_scan_scope(
    target_path: Path,
    volume_root: Path,
    crossed_volumes: bool,
) -> str:
    ...
```

Rules:

## Full-volume

The normalized scan target equals the volume root.

Examples:

```text
C:\
D:\
```

## Partial-volume

The target is a child path on one volume.

Examples:

```text
C:\Users
C:\ProgramData
```

## Cross-volume

Traversal included another volume through an explicitly followed mount point.

## Unknown

Volume root or target identity cannot be determined.

Do not classify a target as full-volume merely because it begins with a drive letter.

---

# 12. Explained Folder Delta

The explained value must use non-overlapping direct measurements.

Use:

```text
explained_folder_delta =
    sum(all trusted direct deltas)
```

Include:

* grown directories;
* reduced directories;
* new directories;
* removed directories;
* unchanged directories, which contribute zero.

Exclude:

* incomplete comparisons;
* inaccessible measurements;
* incompatible observations;
* intentionally skipped branches that are outside scan coverage;
* unknown deltas.

Do not use inclusive deltas.

Do not sum parent and child subtree values.

---

# 13. Incomplete Coverage

Track how much of the directory tree was not reliably compared.

Recommended metrics:

```text
comparable_directory_count
incomplete_directory_count
excluded_directory_count
unavailable_directory_count
```

Optionally track known prior sizes for incomplete folders:

```text
unresolved_previous_bytes
unresolved_current_bytes
```

Do not fabricate a numeric adjustment for inaccessible folders.

Instead, explain:

```text
31 directories could not be compared reliably.
The unexplained delta may include changes within those directories.
```

---

# 14. Excluded Paths

Phase 4 may support exclusions and skipped reparse targets.

The reconciliation service must distinguish:

* paths intentionally outside scan scope;
* paths skipped because of reparse policy;
* paths inaccessible unexpectedly.

For full-volume scans, intentional exclusions reduce reconciliation completeness.

Example:

```text
Target: C:\
Excluded: C:\Windows.old
```

This scan is technically rooted at the volume root but does not cover the entire volume.

Recommended scope classification:

```text
partial_volume
```

or:

```text
full_volume_with_exclusions
```

Preferred Phase 5 values:

```text
full_volume
full_volume_with_exclusions
partial_volume
cross_volume
unknown
```

---

# 15. Reconciliation Calculation Service

Create a dedicated service.

Recommended interface:

```python
class ReconciliationService:
    def reconcile(
        self,
        baseline_scan_id: int,
        current_scan_id: int,
    ) -> ReconciliationResult:
        ...
```

Recommended result model:

```python
class ReconciliationResult(BaseModel):
    baseline_scan_id: int
    current_scan_id: int

    scope_type: str
    previous_used_bytes: int | None
    current_used_bytes: int | None
    observed_volume_delta_bytes: int | None

    explained_folder_delta_bytes: int | None
    unexplained_delta_bytes: int | None

    intra_scan_delta_bytes: int | None
    comparable_directory_count: int
    incomplete_directory_count: int
    excluded_directory_count: int

    coverage_ratio: float | None
    status: str
    confidence: str
    confidence_reason: str
    warnings: list[str]
```

The service must not format GUI or CLI output.

---

# 16. Reconciliation Rules

## 16.1 Compatible full-volume scans

When both scans:

* target the same volume;
* use compatible measurement configuration;
* are full-volume scans;
* have usable after-scan volume observations;
* have a completed folder comparison;

calculate full reconciliation.

## 16.2 Partial-volume scans

Calculate:

* observed whole-volume change;
* explained target-tree change;
* unexplained remainder.

But mark:

```text
status = partial_scope
confidence = low or medium
```

Display that the remainder includes all activity outside the scan target.

## 16.3 Different volumes

Do not reconcile.

```text
status = not_available
reason = scans refer to different volumes
```

## 16.4 Missing volume observation

Do not invent values.

```text
observed_volume_delta = NULL
unexplained_delta = NULL
status = not_available
```

## 16.5 Incompatible scan settings

Do not reconcile automatically.

## 16.6 Comparison unavailable

If no Phase 2 folder comparison exists, reconciliation cannot proceed.

## 16.7 Reconciliation failure

A failure must not invalidate:

* the completed scan;
* folder snapshots;
* folder comparison results.

Mark reconciliation failed and allow retry.

---

# 17. Coverage Ratio

Coverage ratio is useful only in certain cases.

Recommended:

```text
coverage_ratio =
    explained_folder_delta
    / observed_volume_delta
```

But only calculate when:

* observed volume delta is not zero;
* explained and observed values have the same sign;
* scope is full-volume or full-volume-with-exclusions;
* both values are available.

If:

```text
observed volume delta = 0
```

set coverage ratio to `NULL`.

If values have opposite signs, do not show a misleading percentage.

Example:

```text
Observed volume: +2 GB
Explained folders: -1 GB
```

This is not “-50% coverage.”

Instead report:

```text
Folder observations and volume usage moved in opposite directions.
```

---

# 18. Confidence Model

Assign reconciliation confidence separately from folder comparison confidence.

## High confidence

* same volume identity;
* both scans complete;
* full-volume target;
* no exclusions;
* compatible scan configuration;
* all major directories comparable;
* after-scan volume observations available;
* small intra-scan volume change;
* no cross-volume traversal.

## Medium confidence

* full-volume scan with minor exclusions;
* small number of incomplete folders;
* logical-size measurement only;
* moderate intra-scan activity;
* reparse targets skipped safely.

## Low confidence

* partial-volume target;
* significant exclusions;
* many inaccessible paths;
* large intra-scan volume change;
* scan duration long relative to activity;
* forced compatibility override;
* cross-volume topology differences.

## Unavailable

* different volumes;
* missing volume observation;
* no valid baseline;
* failed folder comparison;
* incompatible scan configuration.

Always provide a confidence reason.

---

# 19. Tolerance and Rounding

All calculations must use integer bytes.

Human-readable formatting must happen only in reporting.

Do not round before subtracting.

Add an optional reconciliation tolerance for presentation.

Example:

```text
tolerance_bytes = 16 MB
```

If the unexplained difference is within tolerance:

```text
status may display as closely reconciled
```

But retain the exact byte value.

Do not force unexplained delta to zero.

---

# 20. Interpretation Categories

Add a user-facing interpretation based on the unexplained delta.

Recommended categories:

```text
closely_reconciled
partially_reconciled
large_unexplained_growth
large_unexplained_reduction
opposite_direction
not_available
```

Example rules may use:

* absolute byte threshold;
* percentage of observed change;
* scope;
* confidence.

Do not hard-code alarming language for small differences.

---

# 21. System-Managed Storage Categories

Phase 5 does not yet measure specific system-managed categories.

However, the report should identify likely classes of unexplained change:

```text
Possible contributors include:
- pagefile.sys
- hiberfil.sys
- System Restore
- Volume Shadow Copies
- Windows reserved storage
- filesystem metadata
- inaccessible directories
- files changing during the scan
- sparse or compressed allocation differences
```

Present these as possibilities, not confirmed causes.

Do not claim a specific subsystem caused the unexplained delta without direct measurement.

---

# 22. Scan Lifecycle Changes

After folder comparison completes:

1. Verify baseline and current scan compatibility.
2. Load after-scan volume observations.
3. Classify scan scope.
4. Calculate observed volume delta.
5. Calculate explained direct logical delta.
6. Calculate unexplained delta.
7. assess confidence.
8. persist reconciliation.
9. generate report output.

Recommended lifecycle:

```text
scan completed
→ folder comparison completed
→ reconciliation running
→ reconciliation completed
```

If reconciliation fails:

```text
folder comparison remains valid
reconciliation status = failed
```

---

# 23. Configuration Hash

Add reconciliation-relevant settings to metadata where needed:

```text
volume_provider_version
scope_classification_version
reconciliation_algorithm_version
```

Do not include display thresholds.

The same folder snapshots may be reconciled again with a newer reconciliation algorithm if versioning is supported.

---

# 24. GUI Requirements

Add a reconciliation summary panel.

## 24.1 Required values

Display:

```text
Previous volume used space
Current volume used space
Observed volume change

Explained folder change
Unexplained change

Scan scope
Reconciliation confidence
```

## 24.2 Example

```text
Volume change
Observed used-space growth:   +10.20 GB

Folder explanation
Explained logical growth:      +7.85 GB
Unexplained difference:        +2.35 GB

Scope: Full volume
Confidence: Medium
```

## 24.3 Partial target warning

For a partial-volume scan:

```text
This scan covers only C:\Users\brad.

The unexplained value includes all disk activity outside that folder.
```

## 24.4 Intra-scan activity

When significant:

```text
Used space changed by 1.8 GB while this scan was running.
This may reduce reconciliation accuracy.
```

## 24.5 Incomplete comparisons

Display:

```text
27 directories could not be compared reliably.
```

Do not hide them from the user.

---

# 25. CLI Requirements

Extend the Typer CLI.

## 25.1 Reconciliation report

```powershell
uv run folder-diff-cli reconcile
```

Default:

* use newest completed comparison;
* display reconciliation summary;
* show confidence;
* show warnings.

## 25.2 Explicit scan

```powershell
uv run folder-diff-cli reconcile --scan-id 15
```

## 25.3 JSON output

Optional but recommended:

```powershell
uv run folder-diff-cli reconcile --scan-id 15 --json
```

This should emit structured reconciliation data.

## 25.4 Scan detail

Extend:

```powershell
uv run folder-diff-cli scan-show 15
```

to include:

```text
Volume identity
Scope classification
Observed volume delta
Explained folder delta
Unexplained delta
Reconciliation status
Confidence
```

## 25.5 Volume history

Optional:

```powershell
uv run folder-diff-cli volume-history --limit 20
```

Columns:

```text
Scan
Captured
Used
Free
Delta
Scope
Status
```

---

# 26. Text Report Changes

Add a section:

```text
VOLUME RECONCILIATION
------------------------------------------------------------
Volume:                     C:
Scope:                      Full volume
Baseline scan:              14
Current scan:               15

Previous used space:        410.25 GB
Current used space:         420.45 GB
Observed volume change:     +10.20 GB

Explained folder change:     +7.85 GB
Unexplained difference:      +2.35 GB

Directories compared:       708,421
Incomplete comparisons:          27
Excluded directories:             0

Confidence: Medium
Reason: Logical-size measurements do not yet account for
physical allocation and 27 directories were incomplete.
```

For partial scope:

```text
This scan covers only part of the volume.
Unexplained change includes activity outside the target directory.
```

Include:

```text
Folder changes are based on logical file size.
Allocated disk-space measurement is planned for a later phase.
```

---

# 27. Baseline and Migration Behavior

The first Phase 5 scan may reconcile against a Phase 4 baseline if:

* both scans already contain valid after-scan volume observations;
* both use compatible folder measurement rules;
* both refer to the same volume;
* the Phase 4 data is sufficient.

If prior volume observations are incomplete or inconsistent:

```text
reconciliation unavailable
```

Do not create a new folder baseline solely because reconciliation was added.

Reconciliation may begin when two scans contain compatible volume data.

---

# 28. Historical Backfill

Do not automatically fabricate missing historical volume observations.

If prior scans contain:

```text
total_bytes
free_bytes_after
```

a migration may derive:

```text
used_bytes_after =
    total_bytes - free_bytes_after
```

Only backfill when the source values are trustworthy.

Do not infer missing timestamps.

Mark backfilled records explicitly if useful:

```text
observation_source = migrated
```

---

# 29. Performance Requirements

Reconciliation should be inexpensive relative to scanning.

Requirements:

* calculate explained delta with a database aggregate query where possible;
* do not load every directory diff into memory solely to sum totals;
* query counts and sums directly;
* avoid ORM lazy loading;
* persist one reconciliation record per current scan;
* allow recalculation without rescanning.

Recommended aggregate query:

```text
SUM(comparable direct deltas)
COUNT(comparable directories)
COUNT(incomplete directories)
```

---

# 30. Failure Handling

Capture and persist failures for:

```text
capture_volume_before
capture_volume_after
identify_volume
classify_scope
calculate_observed_delta
calculate_explained_delta
persist_reconciliation
```

If pre-scan volume capture fails but post-scan succeeds:

* retain post-scan observation;
* comparison against another scan may still be possible.

If post-scan capture fails:

* current scan cannot support full reconciliation.

Do not fail the entire folder scan because volume capture fails.

---

# 31. Service Boundaries

Recommended structure:

```text
scanner/
- captures before and after volume state
- no reconciliation logic

analysis/differ.py
- calculates folder deltas

analysis/reconciliation.py
- calculates volume reconciliation
- assigns confidence and interpretation

scanner/volume_info.py
- volume identity and usage provider

db/
- persists observations and reconciliation

reporting/
- formats reconciliation output

gui/
- presents results
```

Do not place reconciliation arithmetic in:

* GUI widgets;
* SQLAlchemy models;
* scanner traversal code;
* report templates.

---

# 32. Suggested Domain Models

## Volume snapshot

```python
class VolumeSnapshot(BaseModel):
    volume_id: str | None
    root_path: Path
    filesystem_name: str | None

    total_bytes: int | None
    free_bytes: int | None
    used_bytes: int | None

    captured_at: datetime
    status: str
```

## Scope classification

```python
class ScopeClassification(BaseModel):
    scope_type: str
    target_path: Path
    volume_root: Path | None
    exclusions_present: bool
    crossed_volumes: bool
    reason: str
```

## Reconciliation summary

```python
class ReconciliationSummary(BaseModel):
    current_scan_id: int
    baseline_scan_id: int

    observed_volume_delta_bytes: int | None
    explained_folder_delta_bytes: int | None
    unexplained_delta_bytes: int | None

    scope_type: str
    confidence: str
    confidence_reason: str
    status: str
```

---

# 33. Testing Requirements

Use temporary SQLite databases and mocked volume providers where appropriate.

## 33.1 Exact reconciliation

Previous:

```text
used volume = 1000 bytes
```

Current:

```text
used volume = 1300 bytes
```

Folder direct net change:

```text
+300 bytes
```

Expected:

```text
observed = +300
explained = +300
unexplained = 0
```

## 33.2 Partial explanation

Observed:

```text
+1000 bytes
```

Explained:

```text
+700 bytes
```

Expected:

```text
unexplained = +300 bytes
```

## 33.3 Unexplained reduction

Observed:

```text
-1000 bytes
```

Explained:

```text
-600 bytes
```

Expected:

```text
unexplained = -400 bytes
```

## 33.4 Opposite directions

Observed:

```text
+1000 bytes
```

Explained:

```text
-200 bytes
```

Expected:

```text
unexplained = +1200 bytes
coverage ratio = NULL
interpretation = opposite_direction
```

## 33.5 Zero observed change

Observed:

```text
0 bytes
```

Explained:

```text
+200 bytes
```

Expected:

```text
unexplained = -200 bytes
coverage ratio = NULL
```

## 33.6 Full-volume scope

Target equals volume root.

Expected:

```text
scope = full_volume
```

## 33.7 Partial-volume scope

Target:

```text
C:\Users\brad
```

Expected:

```text
scope = partial_volume
confidence downgraded
```

## 33.8 Full-volume with exclusions

Target:

```text
C:\
```

Excluded:

```text
C:\Windows.old
```

Expected:

```text
scope = full_volume_with_exclusions
```

## 33.9 Cross-volume scan

Expected:

```text
scope = cross_volume
reconciliation unavailable or per-volume only
```

## 33.10 Different volume identities

Baseline and current scan refer to different volume IDs.

Expected:

```text
status = not_available
```

## 33.11 Missing post-scan observation

Expected:

```text
observed delta = NULL
unexplained delta = NULL
```

## 33.12 Incomplete directory comparisons

Expected:

* comparable count correct;
* incomplete count correct;
* explained total excludes unknown deltas;
* confidence downgraded.

## 33.13 Large intra-scan activity

Mock:

```text
used before = 100 GB
used after = 105 GB
```

Expected:

* intra-scan delta stored;
* confidence downgraded;
* warning displayed.

## 33.14 Threshold independence

Changing the display threshold must not alter explained net folder delta.

## 33.15 Inclusive values ignored

Create parent and child inclusive deltas.

Expected:

* reconciliation uses only direct deltas;
* no double counting.

## 33.16 Reparse alias ignored

Alias path and real target exist.

Expected:

* explained delta counted once.

## 33.17 Reconciliation failure

Mock database or calculation failure.

Expected:

* scan remains completed;
* folder comparison remains completed;
* reconciliation status becomes failed;
* retry remains possible.

## 33.18 Historical backfill

Where valid prior fields exist:

```text
used = total - free
```

Verify migrated value.

## 33.19 Byte precision

Verify no rounding before arithmetic.

## 33.20 CLI report

Verify:

* correct values;
* confidence shown;
* partial-scope warning shown;
* unavailable reconciliation handled cleanly.

---

# 34. Compatibility Requirements

Phase 5 must preserve:

* direct logical snapshots;
* scan-to-scan folder differences;
* hierarchy measurements;
* non-overlapping totals;
* reparse-point safety;
* baseline selection;
* scan lifecycle behavior;
* database history;
* GUI responsiveness;
* CLI scan history;
* text reports;
* structured warnings.

A reconciliation failure must never invalidate a completed folder scan or comparison.

---

# 35. Documentation Requirements

Update `README.md` with:

* observed volume change;
* explained folder change;
* unexplained change;
* full-volume versus partial-volume scans;
* logical size versus allocated size;
* intra-scan activity;
* confidence rules;
* limitations;
* CLI examples;
* interpretation examples.

Include:

```text
Observed volume change measures how much total used space changed.

Explained folder change measures the net change in directly contained logical file sizes found by the scan.

The difference is reported as unexplained change.
```

Also include:

```text
Unexplained change is not necessarily an error.
It may represent system-managed storage, inaccessible paths,
physical allocation differences, or activity during the scan.
```

---

# 36. Acceptance Criteria

Phase 5 is complete when all of the following are true:

1. Volume identity is captured where available.
2. Total, free, and used bytes are stored.
3. Volume state is captured before and after each scan.
4. After-scan observations are used for cross-scan reconciliation.
5. Intra-scan volume change is calculated.
6. Scan scope is classified.
7. Full-volume and partial-volume scans are distinguished.
8. Exclusions affect scope classification.
9. Cross-volume scans are identified.
10. Observed volume delta is calculated correctly.
11. Explained folder delta uses direct measurements only.
12. Inclusive values are never used in reconciliation totals.
13. Incomplete directory comparisons are excluded from numeric totals.
14. Unexplained delta is calculated correctly.
15. Opposite-direction changes are reported clearly.
16. Coverage ratio is not shown when misleading.
17. Reconciliation confidence includes a reason.
18. Partial-volume scans display a clear warning.
19. Large intra-scan changes reduce confidence.
20. Missing volume data produces unavailable results rather than invented values.
21. Reconciliation is persisted per current scan.
22. Reconciliation can be recalculated without rescanning.
23. Reconciliation failure does not invalidate scan or folder comparison data.
24. GUI displays reconciliation summary.
25. CLI exposes reconciliation results.
26. Text reports include observed, explained, and unexplained values.
27. Historical scans remain readable.
28. All prior tests continue to pass.
29. All Phase 5 tests pass with:

```powershell
uv run pytest
```

30. The application is prepared for Phase 6 allocated-size measurement.

---

# 37. Coding-Agent Assignment

Implement Phase 5 only.

Add volume-level reconciliation using the scan’s persisted volume observations and Phase 2–4 direct folder differences.

Capture and persist total, free, and used bytes before and after each scan. Use the after-scan volume observation from the baseline and current scan to calculate:

```text
observed_volume_delta =
    current used bytes
    - baseline used bytes
```

Calculate explained folder change using only trusted direct logical-size deltas:

```text
explained_folder_delta =
    sum of comparable direct deltas
```

Do not use inclusive hierarchy values.

Calculate:

```text
unexplained_delta =
    observed_volume_delta
    - explained_folder_delta
```

Create persistent reconciliation records containing:

* baseline scan ID;
* current scan ID;
* volume identity;
* scope type;
* previous and current used bytes;
* observed volume delta;
* explained folder delta;
* unexplained delta;
* comparable and incomplete directory counts;
* confidence;
* confidence reason;
* status;
* algorithm version.

Classify scan scope as:

* full volume;
* full volume with exclusions;
* partial volume;
* cross volume;
* unknown.

Partial-volume scans may display reconciliation values, but must clearly state that unexplained change includes activity outside the scan target.

Calculate intra-scan volume change using before and after observations. Downgrade confidence when used space changes substantially while the scan is running.

Do not identify unexplained change as a specific system cause. Present pagefile, hibernation, restore points, shadow copies, filesystem metadata, inaccessible folders, and allocation differences only as possible contributors.

Update GUI, CLI, and text reports to show:

* observed volume change;
* explained folder change;
* unexplained change;
* scan scope;
* confidence;
* incomplete directory count;
* intra-scan activity warning where relevant.

Do not implement allocated-size measurement, system-file attribution, VSS analysis, hard-link deduplication, file-level forensics, retention, or scheduling.

The completed Phase 5 application must clearly distinguish between total volume-space change and the portion explained by logical folder-size snapshots.
