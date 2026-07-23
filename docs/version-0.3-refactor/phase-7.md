Phase 7 turns the application from a folder-difference monitor into a practical forensic tool: it can show not only where storage changed, but which files changed and whether those changes actually consumed new physical space.

# Phase 7 Technical Specification

Implement Phase 7 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 7. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## File-Level Forensics, Stable Identity, and Hard-Link Awareness

**Project:** `windows-folder-sizes-diff`
**Phase:** 7 — File-Level Forensics
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Windows integration:** pywin32 and Windows filesystem APIs
**Prerequisites:** Phases 0–6 completed

---

# 1. Objective

Add targeted file-level tracking so the application can identify which individual files caused folder and volume changes.

The application currently knows:

* which folders changed;
* their logical-size deltas;
* their allocated-size deltas;
* how those changes propagate through the folder hierarchy;
* how much volume-space change remains unexplained.

It does not yet reliably distinguish between:

* a newly created file;
* a deleted file;
* a resized file;
* a file moved between folders;
* a file renamed in place;
* a file rewritten without changing size;
* multiple paths referencing the same hard-linked physical file.

At the end of Phase 7, the application must answer:

> Which large or significant files explain each folder change, and did they appear, disappear, resize, move, rename, or reference already-counted physical data?

Example:

```text
C:\Users\brad\AppData\Roaming\Notion
    Allocated growth: +1.49 GB

    Largest contributors:
    +497.62 MB  New file
    +497.46 MB  New file
    +497.35 MB  New file
```

Another example:

```text
C:\Data\Archive\backup.vhdx
    Previous path: C:\Temp\backup.vhdx
    Current path:  C:\Data\Archive\backup.vhdx
    Logical delta: 0
    Allocated delta: 0
    Classification: Moved
```

Phase 7 must improve attribution without requiring the daily scanner to permanently catalog every small file.

---

# 2. Prerequisite Behavior

Phase 6 is expected to provide:

* logical and allocated file-size measurement;
* direct and inclusive folder snapshots;
* scan-to-scan folder differences;
* metric-specific baselines;
* reparse-point protection;
* canonical path handling;
* volume reconciliation;
* allocation coverage;
* structured warnings;
* scan history;
* GUI, CLI, and text reports;
* SQLite persistence;
* Alembic migrations.

Phase 7 must extend these capabilities without changing their established meanings.

---

# 3. Phase 7 Scope

Implement:

* configurable file-level tracking;
* persistent file identities;
* per-scan file observations;
* Windows volume and file-ID capture;
* logical and allocated file-size history;
* new, deleted, resized, moved, renamed, and unchanged classifications;
* probable identity classification when physical IDs are unavailable;
* hard-link path tracking;
* hard-link-aware physical totals;
* large-file contributor reporting;
* file-level confidence and warnings;
* forensic scan mode;
* migration and compatibility handling;
* GUI, CLI, and text-report updates;
* automated tests.

Do not implement:

* file-content hashing by default;
* continuous filesystem monitoring;
* USN Journal ingestion;
* deleted-file recovery;
* duplicate-content detection;
* Volume Shadow Copy inspection;
* pagefile or hibernation attribution;
* antivirus or malware analysis;
* retention rollups;
* scheduled execution.

Those may be considered in later phases.

---

# 4. Tracking Strategy

Phase 7 must support two file-tracking modes.

## 4.1 Targeted daily tracking

Track files that meet at least one configured criterion.

Recommended default:

```text
Logical size >= 100 MB
or
Allocated size >= 100 MB
```

Additional optional criteria:

* file extension;
* path prefix;
* unusually large file delta;
* folder flagged above the reporting threshold;
* sparse file;
* compressed file;
* VHD, VHDX, database, archive, cache, or installer file type.

Purpose:

* keep daily scans fast;
* preserve the files most likely to explain meaningful disk changes;
* avoid storing millions of small-file records unnecessarily.

## 4.2 Forensic tracking

Track every successfully measured file within the scan target.

Purpose:

* detailed investigations;
* exact file attribution;
* move and rename analysis;
* hard-link analysis;
* validation of folder-level findings.

Forensic mode may be substantially slower and produce much larger databases.

---

# 5. Configuration Changes

Add:

```yaml
FileTrackingMode: targeted
LargeFileThresholdMB: 100
TrackSparseFiles: true
TrackCompressedFiles: true
TrackFileExtensions:
  - .vhd
  - .vhdx
  - .db
  - .sqlite
  - .zip
  - .7z
  - .iso
TrackPaths: []
EnableFileIdentity: true
EnableHardLinkTracking: true
AllowProbableMoveDetection: true
```

Recommended Pydantic fields:

```python
class AppSettings(BaseModel):
    file_tracking_mode: Literal[
        "disabled",
        "targeted",
        "forensic",
    ] = "targeted"

    large_file_threshold_mb: int = Field(default=100, ge=0)

    track_sparse_files: bool = True
    track_compressed_files: bool = True
    track_file_extensions: list[str] = []
    track_paths: list[Path] = []

    enable_file_identity: bool = True
    enable_hard_link_tracking: bool = True
    allow_probable_move_detection: bool = True
```

`disabled` must preserve all folder-level functionality from Phases 0–6.

---

# 6. Configuration Compatibility

Include these settings in file-level comparison compatibility:

```text
file_tracking_mode
large_file_threshold_mb
tracked extensions
tracked paths
file identity provider
file identity algorithm version
hard-link tracking policy
probable move detection policy
logical measurement version
allocated measurement provider and version
```

Two scans may remain folder-compatible while not being file-compatible.

Example:

```text
Folder comparison: compatible
File comparison: incompatible
```

Do not invalidate folder-level reports solely because file-tracking settings changed.

---

# 7. File Identity Principles

Maintain separate concepts.

## 7.1 Path identity

The normalized current path to a file.

Path identity changes when a file is renamed or moved.

## 7.2 Physical file identity

A stable filesystem identity derived from:

```text
volume identity
file ID or NTFS file reference
```

Recommended key:

```text
volume_id:file_id
```

This identity may remain stable when the file is:

* renamed;
* moved within the same volume;
* accessed through another hard link.

## 7.3 Probable identity

A fallback inference when physical identity is unavailable.

Possible signals:

* same logical size;
* same allocated size;
* same creation timestamp;
* disappearance and appearance between scans;
* similar filename;
* compatible path change;
* optional lightweight metadata.

Probable identity must never be presented as certain.

## 7.4 Content identity

Cryptographic hashing is outside Phase 7’s default scope.

Do not hash large files automatically.

---

# 8. Windows File Identity Provider

Create a dedicated provider.

Recommended interface:

```python
class FileIdentityProvider(Protocol):
    name: str
    version: int

    def identify(
        self,
        path: Path,
    ) -> "FileIdentityResult":
        ...
```

Recommended result:

```python
class FileIdentityResult(BaseModel):
    volume_id: str | None
    file_id: str | None
    physical_identity_key: str | None

    hard_link_count: int | None
    status: str

    error_code: int | None = None
    error_message: str | None = None
```

Recommended statuses:

```text
identified
path_only
unsupported
inaccessible
disappeared
failed
```

Use an appropriate Windows file-information API.

Requirements:

* support 64-bit file identifiers;
* combine volume and file ID;
* open files with minimum necessary access;
* allow directories to share the same provider abstraction where useful;
* close handles promptly;
* support long paths;
* avoid following reparse points unexpectedly.

---

# 9. Database Changes

Create a new Alembic migration.

Do not modify previous migration files.

## 9.1 `files`

Create one persistent row per known physical file identity where available, otherwise per path-based identity.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
volume_id                TEXT NULL
file_id                  TEXT NULL
physical_identity_key    TEXT NULL

current_normalized_path  TEXT NOT NULL
current_display_path     TEXT NOT NULL
current_directory_id     INTEGER NULL
current_filename         TEXT NOT NULL

identity_status          TEXT NOT NULL
first_seen_scan_id       INTEGER NOT NULL
last_seen_scan_id        INTEGER NOT NULL

created_at               DATETIME NOT NULL
updated_at               DATETIME NOT NULL
```

Recommended constraints:

```text
UNIQUE(physical_identity_key)
```

when physical identity is non-null.

Path-only records require a separate uniqueness strategy.

Do not assume the same path always refers to the same physical file across time.

## 9.2 `file_paths`

Create a history of paths associated with a file.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
file_id                  INTEGER NOT NULL
scan_id                  INTEGER NOT NULL

normalized_path          TEXT NOT NULL
display_path             TEXT NOT NULL
directory_id             INTEGER NULL
filename                 TEXT NOT NULL

is_primary_path          BOOLEAN NOT NULL DEFAULT 1
is_hard_link_path        BOOLEAN NOT NULL DEFAULT 0

observed_at              DATETIME NOT NULL
```

Constraint:

```text
UNIQUE(scan_id, normalized_path)
```

A physical file may have multiple paths in one scan when hard links exist.

## 9.3 `file_observations`

Create one measurement per file path or physical file per scan according to the selected storage design.

Recommended fields:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
file_id                  INTEGER NOT NULL
file_path_id             INTEGER NOT NULL

logical_bytes            INTEGER NOT NULL
allocated_bytes          INTEGER NULL

created_time             DATETIME NULL
modified_time            DATETIME NULL
accessed_time             DATETIME NULL

file_attributes          INTEGER NULL
is_sparse                BOOLEAN NOT NULL DEFAULT 0
is_compressed            BOOLEAN NOT NULL DEFAULT 0
is_reparse_point         BOOLEAN NOT NULL DEFAULT 0

hard_link_count          INTEGER NULL

measurement_status       TEXT NOT NULL
identity_status          TEXT NOT NULL
allocation_status        TEXT NOT NULL

observed_at              DATETIME NOT NULL
warning_count            INTEGER NOT NULL DEFAULT 0
```

Constraint:

```text
UNIQUE(scan_id, file_path_id)
```

## 9.4 `file_diffs`

Persisting file differences is optional.

The preferred initial implementation is to calculate them from file observations.

If persisted, include:

```text
baseline_scan_id
current_scan_id
file_id
previous_path
current_path
logical_delta
allocated_delta
classification
confidence
```

## 9.5 `hard_link_groups`

Optional but recommended:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
physical_identity_key    TEXT NOT NULL
link_count               INTEGER NOT NULL
primary_file_path_id     INTEGER NULL
logical_bytes            INTEGER NOT NULL
allocated_bytes          INTEGER NULL
status                   TEXT NOT NULL
```

This allows physical allocation to be counted once per hard-linked file.

---

# 10. File Tracking Eligibility

Create a dedicated policy service.

Recommended interface:

```python
class FileTrackingPolicy:
    def should_track(
        self,
        *,
        path: Path,
        logical_bytes: int,
        allocated_bytes: int | None,
        attributes: "FileAttributes",
        settings: AppSettings,
    ) -> bool:
        ...
```

A file should be tracked in targeted mode when any enabled rule matches.

Recommended rules:

* logical size at or above threshold;
* allocated size at or above threshold;
* sparse;
* compressed;
* configured extension;
* configured path prefix.

Do not let GUI reporting thresholds determine persistence eligibility.

File tracking threshold and folder reporting threshold are separate concepts.

---

# 11. Scanner Changes

For each direct file:

1. Obtain logical size.
2. Obtain allocated size according to Phase 6 settings.
3. Determine whether the file meets tracking criteria.
4. If tracked:

   * obtain physical identity where enabled;
   * obtain hard-link count where enabled;
   * capture timestamps and attributes;
   * emit a structured file observation.
5. Continue folder-level aggregation exactly as before.

Recommended event:

```python
class FileObserved(BaseModel):
    scan_id: int
    path: Path
    directory_path: Path

    logical_bytes: int
    allocated_bytes: int | None

    volume_id: str | None
    file_id: str | None
    physical_identity_key: str | None
    hard_link_count: int | None

    created_time: datetime | None
    modified_time: datetime | None
    accessed_time: datetime | None

    is_sparse: bool
    is_compressed: bool

    measurement_status: str
    identity_status: str
    allocation_status: str

    observed_at: datetime
```

Do not pass open file handles through events.

---

# 12. File Persistence Strategy

File observations must be persisted in batches.

Recommended batch size:

```text
500–5000 files
```

Use:

* bulk path lookup;
* bulk physical identity lookup;
* SQLite conflict handling;
* bulk inserts;
* bounded transactions.

Do not perform:

```text
query identity
insert file
commit
```

for every file individually.

Maintain scan-scoped caches:

```python
physical_identity_to_file_id: dict[str, int]
normalized_path_to_file_path_id: dict[str, int]
```

Memory use must remain bounded in forensic mode.

---

# 13. File Classification

Classify file changes between compatible scans.

Required classifications:

```text
new
deleted
resized
moved
renamed
moved_and_renamed
unchanged
rewritten_same_size
hard_link_added
hard_link_removed
identity_changed
incomplete
not_comparable
probable_move
```

---

# 14. Classification Rules

## 14.1 New

Present in the current scan but no matching physical identity or prior path exists.

```text
previous size = 0
current size = current value
```

## 14.2 Deleted

Present in the baseline but no matching physical identity or current path exists.

```text
current size = 0
delta = -previous value
```

## 14.3 Resized

Same physical identity and same path, but logical or allocated size changed.

## 14.4 Moved

Same physical identity, same filename, different parent directory.

## 14.5 Renamed

Same physical identity and parent directory, but filename changed.

## 14.6 Moved and renamed

Same physical identity, different directory and filename.

## 14.7 Unchanged

Same physical identity, same path, same logical and allocated size.

## 14.8 Rewritten same size

Same path and identity, same logical and allocated size, but modification metadata changed.

This classification is informational.

It must contribute:

```text
0 bytes growth
```

## 14.9 Hard link added

Same physical identity gains an additional path.

Physical allocated storage must not be counted again.

## 14.10 Hard link removed

A path disappears, but the same physical identity remains through another path.

Physical allocated storage must not be reported as deleted.

## 14.11 Identity changed

The same path now refers to a different physical file ID.

Treat as:

```text
old file deleted
new file created
```

for byte accounting, while also reporting the path reuse.

## 14.12 Incomplete

One or both observations are insufficient for reliable classification.

---

# 15. Probable Move Detection

When physical identity is unavailable, optionally infer a probable move.

Candidate requirements may include:

* one deleted path;
* one new path;
* identical logical size;
* identical allocated size where available;
* compatible timestamps;
* compatible scan interval;
* no stronger candidate.

Assign a confidence score.

Recommended classifications:

```text
probable_move_high
probable_move_medium
probable_move_low
```

Only display high or medium candidates by default.

Do not alter physical totals based solely on a low-confidence probable move.

---

# 16. Hard-Link Accounting

A hard-linked file may appear through multiple directory paths while occupying physical storage once.

Phase 7 must distinguish:

```text
path-level size
physical allocated size
```

## Path-level logical reporting

Each directory path may show the file as directly present.

This is useful for namespace analysis.

## Physical allocation reporting

Allocated bytes must be counted once per physical identity for volume-level totals.

Designate one observed path as the physical accounting path.

Recommended deterministic choice:

* lexicographically lowest normalized path; or
* first path encountered after stable sorting.

Store the selected primary path.

All other paths should show:

```text
hard-link reference
physical allocated contribution = 0
```

Do not imply that the file itself occupies zero bytes.

---

# 17. Folder Totals and Hard Links

Phase 6 folder totals may have counted allocated bytes once per path.

Phase 7 must add hard-link-aware alternatives.

Recommended metrics:

```text
direct_allocated_bytes_path_based
direct_allocated_bytes_physical
inclusive_allocated_bytes_path_based
inclusive_allocated_bytes_physical
```

Retain existing Phase 6 fields for compatibility if necessary.

Do not silently change historical field meaning.

Preferred physical reporting after Phase 7:

```text
physical allocated bytes
```

Path-based totals should remain available as a diagnostic view.

---

# 18. Hard-Link-Aware Reconciliation

Extend reconciliation with:

```text
explained_allocated_delta_path_based
explained_allocated_delta_physical
selected_allocated_accounting
```

Preferred selected accounting:

```text
physical
```

when:

* file identity coverage is sufficient;
* hard-link tracking is enabled;
* identity confidence is adequate.

Otherwise, retain Phase 6 path-based allocated reconciliation and explain the limitation.

---

# 19. File Identity Coverage

Track file-identity coverage separately from allocated-size coverage.

Recommended calculation:

```text
identity_coverage_percent =
    tracked logical bytes with stable physical identity
    / total tracked logical bytes
    × 100
```

Also track:

```text
tracked_file_count
identified_file_count
path_only_file_count
identity_failure_count
```

Do not calculate coverage by averaging folder percentages.

---

# 20. Daily Mode Limitations

Targeted daily tracking does not explain every small-file change.

Reports must state:

```text
File-level attribution includes only files matching the configured tracking policy.
Folder-level totals remain authoritative for all measured files.
```

The difference between folder delta and tracked-file delta should be shown as:

```text
unattributed small-file change
```

Example:

```text
Folder allocated growth:         +1.50 GB
Tracked-file contributors:       +1.31 GB
Unattributed smaller-file change: +0.19 GB
```

---

# 21. File Attribution Service

Create a dedicated service.

Recommended interface:

```python
class FileAttributionService:
    def analyze(
        self,
        baseline_scan_id: int,
        current_scan_id: int,
        directory_id: int | None = None,
    ) -> "FileAttributionReport":
        ...
```

Recommended result:

```python
class FileAttributionReport(BaseModel):
    baseline_scan_id: int
    current_scan_id: int
    directory_id: int | None

    logical_folder_delta_bytes: int
    allocated_folder_delta_bytes: int | None

    tracked_logical_delta_bytes: int
    tracked_allocated_delta_bytes: int | None

    unattributed_logical_delta_bytes: int
    unattributed_allocated_delta_bytes: int | None

    files: list["FileDiff"]
    confidence: str
    confidence_reason: str
```

---

# 22. File Difference Model

Recommended model:

```python
class FileDiff(BaseModel):
    file_record_id: int | None

    previous_path: Path | None
    current_path: Path | None

    previous_logical_bytes: int | None
    current_logical_bytes: int | None
    logical_delta_bytes: int | None

    previous_allocated_bytes: int | None
    current_allocated_bytes: int | None
    allocated_delta_bytes: int | None

    physical_identity_key: str | None
    hard_link_count_previous: int | None
    hard_link_count_current: int | None

    classification: str
    confidence: str
    confidence_reason: str
```

---

# 23. Metric Accounting Rules

## New physical file

Contributes positive logical and allocated delta.

## Deleted physical file

Contributes negative logical and allocated delta.

## Move on same volume

Contributes:

```text
source folder: negative path-level delta
destination folder: positive path-level delta
volume physical delta: zero
```

## Rename in same folder

Folder delta:

```text
zero
```

## Hard link added

Path-level destination folder may show an additional reference.

Physical volume delta:

```text
zero
```

## Hard link removed

Path-level source folder loses a reference.

Physical volume delta:

```text
zero
```

## Resize

Contributes only the actual logical and allocated difference.

## Same-size rewrite

Contributes zero.

---

# 24. Directory Contributor Reports

For every significant folder diff, allow the application to list:

* largest new files;
* largest deleted files;
* largest resized files;
* largest allocated-size increases;
* largest moves into the folder;
* largest moves out;
* hard-link changes;
* unattributed remainder.

Recommended ranking:

```text
absolute allocated delta descending
```

Fallback:

```text
absolute logical delta descending
```

Do not rank same-size rewrites as growth contributors.

---

# 25. File Tracking Baselines

File-level baseline selection must be metric and policy aware.

Required compatibility:

* same target;
* compatible tracking mode;
* compatible threshold;
* compatible extension and path policies;
* compatible identity provider;
* compatible identity algorithm;
* compatible logical and allocated measurement algorithms;
* compatible reparse policy.

A forensic scan should not automatically compare file records against a targeted scan as though both had complete file coverage.

Folder comparisons may still proceed.

---

# 26. Migration and Historical Data

Pre-Phase 7 scans do not have file-level identity history.

Do not attempt to reconstruct past files from folder totals.

The first Phase 7-compatible scan establishes a file baseline.

Display:

```text
Folder comparison is available.
File-level attribution requires one more compatible scan.
```

Historical folder and volume reports must remain readable.

---

# 27. Scan Lifecycle Changes

Recommended sequence:

```text
scan starts
→ folder and file enumeration
→ logical and allocated measurement
→ file identity capture for eligible files
→ batch file persistence
→ folder hierarchy aggregation
→ folder comparison
→ file comparison
→ hard-link accounting
→ volume reconciliation
→ file attribution
→ report generation
```

File comparison failure must not invalidate:

* folder snapshots;
* folder comparison;
* volume reconciliation.

Mark file analysis separately:

```text
not_started
baseline_created
running
completed
completed_with_warnings
partial
failed
```

---

# 28. Database Performance

For forensic mode, database volume may increase substantially.

Requirements:

* use bulk inserts;
* use indexed identity lookups;
* avoid ORM lazy loading;
* stream large comparisons;
* avoid loading every file record into memory;
* use bounded transactions;
* permit cancellation;
* report persistence progress.

Recommended indexes:

```text
files(physical_identity_key)
files(current_normalized_path)
file_paths(scan_id, normalized_path)
file_paths(file_id, scan_id)
file_observations(scan_id, file_id)
file_observations(file_id, scan_id)
file_observations(scan_id, logical_bytes)
file_observations(scan_id, allocated_bytes)
```

---

# 29. Optional Staging Tables

For large forensic comparisons, temporary or staging tables may be used.

Possible structure:

```text
current_file_identity
baseline_file_identity
file_comparison_candidates
```

Do not add complexity unless benchmarks show direct indexed joins are insufficient.

---

# 30. File Comparison Performance

The comparison must avoid:

```text
one query per file
```

Recommended strategies:

* join by physical identity;
* separately match path-only files;
* process unmatched new and deleted candidates;
* run probable-move matching only on bounded candidate sets;
* limit expensive inference to files above the tracking threshold.

Do not perform quadratic matching across all unmatched files.

---

# 31. Probable Move Candidate Bounding

Group unmatched files by:

```text
logical size
allocated size
volume
```

Then compare only within matching groups.

Optional secondary signals:

* creation timestamp;
* extension;
* filename similarity;
* directory proximity.

Set a maximum candidate-group size.

If too many candidates are indistinguishable:

```text
classification = ambiguous
```

Do not guess.

---

# 32. GUI Requirements

Add file-level detail without overcrowding the main folder report.

## 32.1 Folder details

Add a tab or panel:

```text
File contributors
```

Display:

```text
File
Classification
Logical Change
Allocated Change
Previous Path
Current Path
Confidence
```

## 32.2 Summary

Display:

```text
Tracked files
Files identified physically
Identity coverage
New files
Deleted files
Resized files
Moved files
Renamed files
Hard links added
Hard links removed
Unattributed folder change
```

## 32.3 Filters

Support:

```text
New
Deleted
Resized
Moved
Renamed
Hard links
Same-size rewrites
Incomplete
```

## 32.4 File detail

Display:

```text
Physical identity
Volume
File ID
Current path
Previous path
Logical size history
Allocated size history
Hard-link count
Sparse/compressed status
Classification
Confidence
Warnings
```

---

# 33. CLI Requirements

Extend the Typer CLI.

## File contributors

```powershell
uv run folder-diff-cli file-contributors --scan-id 15
```

Options:

```text
--folder PATH
--classification
--metric logical
--metric allocated
--limit
--include-incomplete
```

## File history

```powershell
uv run folder-diff-cli file-history "C:\Data\archive.vhdx"
```

When physical identity is available, show history across moves and renames.

## Moves

```powershell
uv run folder-diff-cli file-moves --scan-id 15
```

## Hard links

```powershell
uv run folder-diff-cli hard-links --scan-id 15
```

## Forensic scan

```powershell
uv run folder-diff-cli scan --file-tracking forensic
```

## JSON output

Recommended:

```powershell
uv run folder-diff-cli file-contributors --scan-id 15 --json
```

---

# 34. Text Report Changes

Add:

```text
FILE-LEVEL ATTRIBUTION
------------------------------------------------------------
Tracking mode:              Targeted
Tracked threshold:          100 MB
Tracked files:              421
Physical identities found:  397
Identity coverage:          97.6%

New files:                   18
Deleted files:               6
Resized files:              11
Moved files:                 4
Renamed files:               2
Hard links added:            3
Hard links removed:          1
```

Example contributor section:

```text
C:\Users\brad\AppData\Roaming\Notion
    Folder allocated growth:          +1.49 GB
    Tracked-file contribution:        +1.49 GB
    Unattributed remainder:             0 MB

    +497.62 MB  New
    +497.46 MB  New
    +497.35 MB  New
```

Include limitation:

```text
Targeted tracking does not catalog every small file.
Unattributed remainder represents changes not explained by tracked files.
```

---

# 35. Hard-Link Report Language

Use clear language:

```text
This path references physical data already counted through another hard link.
```

Avoid:

```text
This file uses no disk space.
```

Path-level and physical-level reporting must remain distinct.

---

# 36. Confidence Model

## High confidence

* stable physical identity available;
* baseline and current observations complete;
* logical and allocated measurements available;
* same volume;
* hard-link information available.

## Medium confidence

* stable physical identity available;
* one measurement has minor warnings;
* allocated size incomplete but logical size complete.

## Low confidence

* path-only matching;
* probable move inference;
* incomplete identity coverage;
* ambiguous hard-link information.

## Unavailable

* observations incomplete;
* incompatible tracking policies;
* path reused by a different identity;
* no reliable match.

Always provide a reason.

---

# 37. Error Handling

Persist warnings for:

```text
identify_file
query_file_id
query_hard_link_count
persist_file_identity
persist_file_observation
compare_files
detect_move
detect_hard_links
calculate_file_attribution
```

File-level failures must not stop folder scanning unless a broader filesystem error occurs.

---

# 38. Privacy and Storage Considerations

File-level tracking stores filenames and paths.

Add documentation explaining that the SQLite database may contain:

* personal filenames;
* project names;
* application data paths;
* document locations.

Do not transmit data externally.

Do not store file contents.

Do not hash contents by default.

Provide a configuration option to disable file tracking.

---

# 39. Retention Preparation

Phase 7 does not implement retention, but schema design must support later cleanup.

Ensure file observations can be deleted by scan without deleting stable identity records required by retained scans.

Do not cascade-delete a physical file identity while retained observations still reference it.

---

# 40. Suggested Domain Models

## File observation

```python
class TrackedFileObservation(BaseModel):
    scan_id: int
    path: Path
    directory_id: int

    logical_bytes: int
    allocated_bytes: int | None

    volume_id: str | None
    file_id: str | None
    physical_identity_key: str | None

    hard_link_count: int | None

    created_time: datetime | None
    modified_time: datetime | None

    is_sparse: bool
    is_compressed: bool

    measurement_status: str
    identity_status: str
    observed_at: datetime
```

## File comparison summary

```python
class FileDiffSummary(BaseModel):
    baseline_scan_id: int
    current_scan_id: int

    files_compared: int
    files_new: int
    files_deleted: int
    files_resized: int
    files_moved: int
    files_renamed: int
    hard_links_added: int
    hard_links_removed: int
    files_incomplete: int

    tracked_logical_delta_bytes: int
    tracked_allocated_delta_bytes: int | None
```

---

# 41. Service Boundaries

Recommended structure:

```text
scanner/file_identity.py
- Windows physical identity provider
- hard-link count provider

scanner/file_tracking.py
- tracking eligibility policy

scanner/folder_scanner.py
- emits file observations
- retains folder aggregation

db/file_repositories.py
- file identity and observation persistence

analysis/file_differ.py
- classification
- move and rename detection

analysis/hard_links.py
- hard-link grouping
- physical accounting

analysis/file_attribution.py
- explains folder deltas

analysis/reconciliation.py
- uses hard-link-aware physical totals

reporting/
- file contributor reports

gui/
- file contributor and history views
```

The scanner must not perform historical classification.

The GUI must not calculate file deltas.

---

# 42. Testing Requirements

Use temporary files, temporary SQLite databases, mocks, and Windows-specific fixtures.

## 42.1 New tracked file

Create a file above the threshold after the baseline.

Expected:

```text
classification = new
delta = current size
```

## 42.2 Deleted tracked file

Expected:

```text
classification = deleted
delta = negative previous size
```

## 42.3 Resized file

Increase file size.

Expected:

```text
classification = resized
logical and allocated deltas accurate
```

## 42.4 Same-size rewrite

Modify content without changing size.

Expected:

```text
classification = rewritten_same_size
growth contribution = 0
```

## 42.5 Move within same volume

Move a tracked file to another directory.

Expected:

```text
same physical identity
classification = moved
volume physical delta = 0
source folder path delta negative
destination folder path delta positive
```

## 42.6 Rename in same folder

Expected:

```text
classification = renamed
folder size delta = 0
```

## 42.7 Move and rename

Expected:

```text
classification = moved_and_renamed
physical delta = 0
```

## 42.8 Path reused by new file

Delete a file and create another at the same path.

Expected:

```text
identity_changed
old file deleted
new file created
```

## 42.9 Hard link added

Create a second hard link.

Expected:

```text
hard_link_added
path count increases
physical allocated total unchanged
```

## 42.10 Hard link removed

Remove one link while another remains.

Expected:

```text
hard_link_removed
physical allocated total unchanged
```

## 42.11 Final hard link removed

Remove the last path.

Expected:

```text
physical file deleted
allocated delta negative
```

## 42.12 Hard-link folder accounting

The same file is linked into two folders.

Expected:

* both paths visible;
* path-based totals reflect both references;
* physical total counts bytes once.

## 42.13 Targeted threshold

A file below the threshold is not persisted unless another rule matches.

## 42.14 Extension rule

A configured `.vhdx` file below the size threshold is still tracked.

## 42.15 Sparse-file rule

Sparse file is tracked when enabled.

## 42.16 Forensic mode

All successfully measured files are persisted.

## 42.17 Disabled mode

No file observations are stored.

Folder-level results remain complete.

## 42.18 Physical identity unavailable

Expected:

* path-only identity;
* lower confidence;
* scan continues.

## 42.19 Probable move

Mock identity failure and matching new/deleted candidates.

Expected:

```text
probable_move
confidence explicitly labeled
```

## 42.20 Ambiguous probable move

Multiple indistinguishable candidates.

Expected:

```text
classification = ambiguous or unmatched
```

Do not guess.

## 42.21 Cross-volume move

Move a file to another volume.

Expected:

* physical identity changes or is unavailable;
* report as deleted and new unless reliable cross-volume evidence exists;
* do not claim confirmed move.

## 42.22 Contributor accounting

Folder delta:

```text
+1000 MB
```

Tracked files explain:

```text
+800 MB
```

Expected:

```text
unattributed remainder = +200 MB
```

## 42.23 Hard-link-aware reconciliation

Path-based allocated delta differs from physical delta.

Expected:

* physical accounting selected when identity coverage is sufficient;
* no hard-link double counting.

## 42.24 File baseline

First compatible file-tracking scan creates file baseline.

Second compatible scan generates attribution.

## 42.25 Tracking-policy mismatch

Expected:

* folder comparison remains available;
* file comparison marked incompatible.

## 42.26 Incomplete file measurement

Expected:

* classification incomplete;
* unknown delta excluded from trusted totals.

## 42.27 Long path

File identity and persistence support long paths.

## 42.28 File disappears during identity lookup

Expected:

* warning persisted;
* no crash;
* observation marked disappeared or incomplete.

## 42.29 Batch persistence

Verify no per-file commit behavior.

## 42.30 Large synthetic comparison

Generate at least 100,000 file observations.

Verify:

* bounded memory use;
* indexed comparison;
* no quadratic candidate matching.

## 42.31 Historical scan

Pre-Phase 7 folder reports remain readable.

## 42.32 Cancellation

Cancellation during forensic scanning must:

* stop promptly;
* produce one terminal event;
* mark file analysis partial;
* preserve consistent folder results.

---

# 43. Performance Requirements

Targeted mode should add acceptable overhead to normal daily scans.

Forensic mode may be slower, but must remain bounded and cancellable.

Measure:

```text
files scanned per second
file identities per second
database insert throughput
comparison duration
peak memory
database growth
```

Document the observed difference between:

```text
file tracking disabled
targeted
forensic
```

---

# 44. Acceptance Criteria

Phase 7 is complete when all of the following are true:

1. File tracking can be disabled, targeted, or forensic.
2. Targeted tracking uses independent persistence criteria.
3. Every tracked file stores logical size.
4. Every tracked file stores allocated size when available.
5. Stable Windows file identity is captured where available.
6. Physical identity combines volume and file ID.
7. File paths are stored historically.
8. Moves within a volume can be recognized.
9. Renames can be recognized.
10. Move-and-rename operations can be recognized.
11. Same-size rewrites contribute zero growth.
12. New and deleted files are classified correctly.
13. Resized files report actual deltas.
14. Path reuse by a new physical file is detected.
15. Hard-link paths are recorded.
16. Hard-linked allocated bytes can be counted once physically.
17. Path-level and physical-level totals remain distinguishable.
18. Adding a hard link does not increase physical allocation.
19. Removing a non-final hard link does not decrease physical allocation.
20. Removing the final hard link reports physical deletion.
21. Probable move detection is explicitly uncertain.
22. Ambiguous move candidates are not guessed.
23. Tracked-file contributions can be compared with folder deltas.
24. Unattributed smaller-file change is shown.
25. File-level compatibility is independent of folder compatibility.
26. The first Phase 7-compatible scan creates a file baseline.
27. Folder reports remain available when file analysis fails.
28. File observations are persisted in batches.
29. Large comparisons avoid per-file queries.
30. GUI shows file contributors and classifications.
31. CLI supports contributors, moves, history, and hard links.
32. Text reports include file attribution.
33. Privacy implications are documented.
34. Historical folder data remains readable.
35. All previous tests continue to pass.
36. All Phase 7 tests pass with:

```powershell
uv run pytest
```

37. The application is prepared for Phase 8 retention, maintenance, automation, and long-term operation.

---

# 45. Coding-Agent Assignment

Implement Phase 7 only.

Add configurable file-level tracking with these modes:

```text
disabled
targeted
forensic
```

In targeted mode, persist files that meet configured size, extension, path, sparse-file, or compressed-file criteria.

In forensic mode, persist every successfully measured file.

Create a Windows file-identity provider that captures:

* volume identity;
* stable file ID where available;
* physical identity key;
* hard-link count.

Store file identities separately from their observed paths so the same physical file can be recognized after a move or rename.

Persist:

* file identity;
* path history;
* directory;
* filename;
* logical size;
* allocated size;
* timestamps;
* file attributes;
* sparse and compressed status;
* hard-link count;
* measurement and identity status.

Create a file comparison service that classifies:

* new;
* deleted;
* resized;
* moved;
* renamed;
* moved and renamed;
* unchanged;
* rewritten at the same size;
* hard link added;
* hard link removed;
* identity changed;
* incomplete;
* probable move.

Use physical identity for definitive move and rename detection.

When physical identity is unavailable, probable-move inference must be explicitly labeled and must not guess among ambiguous candidates.

Add hard-link-aware physical accounting. Multiple paths to the same physical file may appear in path-level reports, but allocated bytes must be counted once in physical totals.

Extend folder reporting so significant folder changes list their largest file contributors and show any unattributed remainder caused by untracked smaller files.

Extend volume reconciliation to use hard-link-aware allocated totals when file-identity coverage is sufficient. Retain Phase 6 path-based reconciliation as a fallback.

Update GUI, CLI, and text reports with:

* tracked file count;
* identity coverage;
* new, deleted, resized, moved, and renamed files;
* hard-link changes;
* largest file contributors;
* unattributed folder change;
* confidence and warnings.

Do not implement continuous monitoring, USN Journal ingestion, file-content hashing, duplicate-content detection, Volume Shadow Copy analysis, system-file attribution, retention, or scheduling.

The completed Phase 7 application must identify which significant files explain folder changes while distinguishing namespace changes from actual physical disk growth.
