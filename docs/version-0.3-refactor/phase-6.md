# Phase 6 Technical Specification

Implement Phase 6 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 6. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Allocated-Size Measurement and Physical Disk Consumption

**Project:** `windows-folder-sizes-diff`
**Phase:** 6 — Allocated-Size Measurement
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Windows integration:** pywin32 and Windows filesystem APIs
**Prerequisites:** Phases 0–5 completed

---

# 1. Objective

Add physical allocation measurement so the application can distinguish between:

* a file’s logical length;
* the number of bytes the file actually occupies on disk.

The application currently compares logical file sizes using `st_size`. Logical size is useful, but it does not always equal physical disk consumption.

Examples include:

* sparse files;
* compressed NTFS files;
* filesystem cluster rounding;
* partially allocated virtual disk files;
* cloud placeholders;
* deduplicated or specialized filesystem content;
* files with alternate allocation behavior.

At the end of Phase 6, the application must answer:

> How much physical disk allocation changed between scans, and how does that differ from logical file-size change?

Example:

```text
Logical folder growth:       +10.00 GB
Allocated folder growth:      +2.15 GB
Observed volume growth:       +2.30 GB
Unexplained difference:       +0.15 GB
```

Allocated bytes must become the preferred measurement for disk-consumption reporting when reliable data is available.

Logical size must remain available for comparison, diagnostics, and compatibility.

---

# 2. Prerequisite Behavior

Phase 5 is expected to provide:

* true scan-to-scan logical-size differences;
* direct and inclusive hierarchy measurements;
* reparse-point and alias protection;
* volume observations;
* volume reconciliation;
* explained and unexplained deltas;
* scan scope classification;
* confidence reporting;
* GUI, CLI, and text reports;
* SQLite persistence;
* Alembic migrations;
* structured warnings;
* configuration compatibility hashes.

Phase 6 must extend those capabilities without removing logical-size reporting.

---

# 3. Phase 6 Scope

Implement:

* Windows allocated-size measurement;
* separate logical and allocated byte fields;
* direct allocated-size folder snapshots;
* inclusive allocated-size hierarchy aggregation;
* scan-to-scan allocated-size differences;
* allocated-size reconciliation;
* measurement coverage tracking;
* fallbacks and confidence rules;
* selectable measurement modes;
* migration and compatibility handling;
* GUI, CLI, and report updates;
* automated tests;
* performance benchmarking.

Do not implement:

* hard-link physical-byte deduplication;
* full file-level historical cataloging;
* file move detection;
* Volume Shadow Copy analysis;
* pagefile attribution;
* hibernation-file attribution;
* NTFS metadata parsing;
* deduplication-service analysis;
* file-content hashing;
* retention policies;
* scheduling.

Hard-link handling and file-level forensics belong to later phases.

---

# 4. Terminology

Use the following terms consistently.

## 4.1 Logical size

The file length reported by standard file metadata.

Typically:

```python
stat_result.st_size
```

A sparse file may have a very large logical size but occupy much less physical space.

Preferred field suffix:

```text
logical_bytes
```

## 4.2 Allocated size

The number of bytes allocated to the file by the filesystem.

Preferred field suffix:

```text
allocated_bytes
```

## 4.3 Allocation unit

The filesystem cluster size or allocation granularity used to store file data.

Do not assume a fixed value such as 4 KB.

## 4.4 Allocation coverage

The proportion of measured logical content for which a reliable allocated-size result was obtained.

## 4.5 Estimated allocated size

An approximation used only when explicitly enabled and clearly labeled.

Estimated values must not be silently mixed with measured allocated values.

## 4.6 Measurement mode

The selected scan behavior:

```text
logical_only
allocated_preferred
allocated_required
```

---

# 5. Measurement Modes

Add three explicit scan modes.

## 5.1 `logical_only`

Behavior:

* calculate logical size;
* do not call allocated-size APIs;
* store allocated size as `NULL`;
* use logical deltas for reporting and reconciliation.

Use case:

* faster scans;
* compatibility;
* troubleshooting;
* systems where allocated-size APIs are unavailable.

## 5.2 `allocated_preferred`

Recommended default after Phase 6.

Behavior:

* calculate logical size;
* attempt allocated-size lookup;
* retain logical size if allocated lookup fails;
* mark allocation coverage and confidence;
* use allocated values where complete enough;
* clearly identify fallback results.

## 5.3 `allocated_required`

Behavior:

* calculate logical and allocated size;
* mark a file or folder incomplete if allocated size cannot be obtained;
* do not substitute logical size;
* exclude unknown allocated deltas from trusted allocated totals.

Use case:

* forensic scans;
* validation;
* physical disk investigations.

---

# 6. Configuration Changes

Add:

```yaml
MeasurementMode: allocated_preferred
AllocatedSizeProvider: windows_compressed_file_size
AllocationCoverageThresholdPercent: 99.0
AllowEstimatedAllocatedSize: false
TrackAllocationFailures: true
```

Recommended Pydantic fields:

```python
class AppSettings(BaseModel):
    measurement_mode: Literal[
        "logical_only",
        "allocated_preferred",
        "allocated_required",
    ] = "allocated_preferred"

    allocated_size_provider: str = "windows_compressed_file_size"

    allocation_coverage_threshold_percent: float = Field(
        default=99.0,
        ge=0.0,
        le=100.0,
    )

    allow_estimated_allocated_size: bool = False
    track_allocation_failures: bool = True
```

Do not use an allocation estimate by default.

---

# 7. Configuration Compatibility

Include these settings in the scan compatibility hash:

```text
measurement_mode
allocated_size_provider
allocated_size_algorithm_version
allow_estimated_allocated_size
allocation_coverage_threshold_percent
filesystem_allocation_policy_version
```

Logical values may remain comparable across scans when logical measurement behavior is unchanged.

Allocated values may only be compared automatically when:

* both scans used compatible allocated-size providers;
* both scans used compatible algorithm versions;
* both scans have sufficient allocation coverage;
* both scans refer to compatible volume and filesystem types.

A scan in `logical_only` mode must not automatically serve as an allocated-size baseline.

---

# 8. Allocated-Size Provider Abstraction

Create a dedicated provider interface.

```python
class AllocatedSizeProvider(Protocol):
    name: str
    version: int

    def measure(
        self,
        path: Path,
        stat_result: os.stat_result,
    ) -> "AllocatedSizeResult":
        ...
```

Recommended result model:

```python
class AllocatedSizeResult(BaseModel):
    allocated_bytes: int | None
    status: str
    provider: str
    is_estimated: bool = False
    error_code: int | None = None
    error_message: str | None = None
```

Recommended statuses:

```text
measured
zero_length
sparse_measured
compressed_measured
estimated
unsupported
inaccessible
disappeared
failed
```

The scanner must not contain Windows API details directly.

---

# 9. Windows Implementation Strategy

Implement allocated-size measurement using an appropriate Windows API.

The preferred initial provider should use the Windows equivalent of:

```text
GetCompressedFileSizeW
```

Despite its name, this API returns the disk storage used by a file and is also applicable to non-compressed files.

Implementation requirements:

* support 64-bit values;
* combine high and low result words correctly;
* distinguish a valid `0xFFFFFFFF` low result from an API error;
* call `GetLastError()` correctly;
* support long paths;
* handle files disappearing between enumeration and lookup;
* close any opened handles;
* preserve exact integer-byte values.

The provider may use:

* `ctypes`;
* pywin32;
* or another thin Windows API wrapper.

Use the simplest reliable implementation.

---

# 10. Alternative Provider Support

The architecture must allow a future provider using:

```text
FSCTL_GET_RETRIEVAL_POINTERS
file allocation information
extent enumeration
```

Do not implement multiple complex providers in Phase 6 unless necessary.

The initial implementation should favor:

* correctness;
* stability;
* low handle overhead;
* acceptable performance.

Record the provider name and version with every scan.

---

# 11. File Measurement Rules

For every successfully statted direct file:

1. Obtain logical size from `st_size`.
2. If mode is not `logical_only`, request allocated size.
3. Store both results separately.
4. Record status and warning when allocation lookup fails.
5. Do not silently assign logical size to allocated size.

Example:

```text
Logical size:      100,000 bytes
Allocated size:    102,400 bytes
```

For an empty file:

```text
Logical size:      0
Allocated size:    0
Status:            zero_length
```

For a sparse file:

```text
Logical size:      100 GB
Allocated size:    2 GB
Status:            sparse_measured
```

---

# 12. Directory Observation Changes

Extend the per-directory observation table.

Add:

```text
direct_allocated_bytes             INTEGER NULL
allocated_file_count               INTEGER NOT NULL DEFAULT 0
allocation_failed_file_count       INTEGER NOT NULL DEFAULT 0
allocation_estimated_file_count    INTEGER NOT NULL DEFAULT 0
allocation_unknown_logical_bytes   INTEGER NOT NULL DEFAULT 0
allocation_coverage_percent        REAL NULL
allocation_measurement_status      TEXT NOT NULL DEFAULT 'not_requested'
```

Retain:

```text
direct_logical_bytes
direct_file_count
files_examined
```

Recommended allocation statuses:

```text
not_requested
complete
complete_with_warnings
partial
unavailable
failed
```

---

# 13. Scan-Level Measurement Metadata

Add to `scans`:

```text
measurement_mode                    TEXT NOT NULL
allocated_size_provider             TEXT NULL
allocated_size_algorithm_version    INTEGER NULL
allocation_coverage_percent         REAL NULL
allocation_failure_count            INTEGER NOT NULL DEFAULT 0
allocated_measurement_status        TEXT NOT NULL DEFAULT 'not_requested'
```

Recommended scan-level statuses:

```text
not_requested
complete
complete_with_warnings
partial
failed
```

---

# 14. Hierarchy Fields

Extend directory hierarchy snapshots with:

```text
inclusive_allocated_bytes           INTEGER NULL
inclusive_allocation_coverage_percent REAL NULL
inclusive_allocation_status         TEXT NOT NULL DEFAULT 'not_requested'
```

Direct and inclusive logical fields must remain unchanged.

Do not overload logical columns with allocated values.

---

# 15. Comparison Fields

Extend directory diff models with:

```text
previous_direct_allocated_bytes
current_direct_allocated_bytes
direct_allocated_delta_bytes

previous_inclusive_allocated_bytes
current_inclusive_allocated_bytes
inclusive_allocated_delta_bytes

allocated_confidence
allocated_confidence_reason
```

Logical comparison fields must remain available.

---

# 16. Database Migration

Create a new Alembic migration.

Do not modify previous migrations.

Add the new logical-versus-allocated fields as nullable where historical data does not exist.

Historical scans should retain:

```text
allocated_measurement_status = not_requested
```

Do not derive historical allocated size from logical size.

The first allocated-compatible scan must establish a new allocated baseline.

Logical comparisons may continue using prior logical-compatible scans where appropriate.

---

# 17. Allocation Coverage

Calculate allocation coverage using successfully measured file content.

Recommended direct folder calculation:

```text
allocation_coverage_percent =
    logical bytes represented by files with measured allocated size
    / total successfully measured logical bytes
    × 100
```

Alternative count-based coverage may also be stored, but byte-weighted coverage is preferred.

Track:

```text
allocated_file_count
allocation_failed_file_count
allocation_unknown_logical_bytes
```

For a directory with no files:

```text
allocation coverage = 100%
```

provided enumeration completed successfully.

---

# 18. Scan-Level Coverage

Calculate scan-level coverage using non-overlapping direct file measurements.

```text
scan_allocation_coverage_percent =
    total logical bytes with measured allocation
    / total direct logical bytes
    × 100
```

Do not calculate scan coverage by averaging directory percentages.

That would overweight small folders.

Use byte-weighted aggregation.

---

# 19. Coverage Threshold

The configured threshold determines whether allocated totals are considered usable.

Example:

```text
AllocationCoverageThresholdPercent: 99.0
```

If scan coverage is at least 99%:

```text
allocated status = complete or complete_with_warnings
```

If below threshold:

```text
allocated status = partial
```

Do not round coverage before comparing it with the threshold.

---

# 20. Estimated Allocation

If `AllowEstimatedAllocatedSize` is enabled, an estimate may use:

```text
ceil(logical_bytes / allocation_unit) × allocation_unit
```

Only use this for ordinary non-sparse, non-compressed files when the allocation unit is known.

Estimated values must be marked:

```text
is_estimated = true
status = estimated
```

Do not use estimated values when:

* the file is sparse;
* the file is compressed;
* the allocation unit is unknown;
* the file has unusual attributes;
* the provider returned an ambiguous failure.

Measured and estimated totals must be distinguishable.

---

# 21. Filesystem Allocation Unit

Create a volume-allocation information provider.

Recommended model:

```python
class VolumeAllocationInfo(BaseModel):
    volume_id: str | None
    filesystem_name: str | None
    sectors_per_cluster: int | None
    bytes_per_sector: int | None
    allocation_unit_bytes: int | None
    status: str
```

Use Windows APIs such as the equivalent of:

```text
GetDiskFreeSpaceW
```

Do not assume all scanned paths use the same allocation unit when cross-volume traversal is enabled.

---

# 22. Sparse Files

Sparse files are a primary reason to measure allocation.

Requirements:

* preserve logical size;
* record allocated size returned by the provider;
* identify sparse-file attributes when available;
* do not estimate allocation from logical size;
* include measured allocated bytes in totals;
* expose logical-versus-allocated difference in detail reports.

Recommended metadata:

```text
is_sparse
is_compressed
```

These may be stored at file-event level in forensic mode later. Phase 6 may aggregate counts without permanently cataloging each file.

---

# 23. Compressed Files

For NTFS-compressed files:

* logical size remains the uncompressed file length;
* allocated size reflects physical storage;
* provider status should indicate compressed measurement where detectable;
* report both values;
* do not treat the difference as missing data.

Example:

```text
Logical size:      1.00 GB
Allocated size:    430 MB
```

---

# 24. Cloud Placeholders and Offline Files

Do not hydrate cloud files solely to measure allocation.

For placeholder or offline files:

* record logical size;
* attempt a non-hydrating allocated-size query;
* if unavailable, mark allocation unknown;
* do not open file content;
* do not trigger downloads;
* downgrade coverage accordingly.

Reparse-point policy from Phase 4 remains in effect.

---

# 25. Hard Links

Phase 6 must not claim that allocated file totals are deduplicated across hard links.

If two directory entries reference the same physical file, naïvely summing allocated size may count the allocation more than once.

Therefore, all allocated reports must state:

```text
Allocated folder totals do not yet deduplicate hard-linked files.
```

Hard-link handling belongs to a later phase.

The reconciliation service should reduce confidence when known hard-link-heavy paths are present, but it must not guess at the amount.

---

# 26. Direct Folder Measurement

For a directory:

```text
direct_logical_bytes =
    sum(logical size of successfully measured direct files)
```

```text
direct_allocated_bytes =
    sum(measured or explicitly permitted estimated allocated size
        of direct files)
```

Unknown allocated values must not be treated as zero.

Track the logical bytes associated with unknown allocation separately.

---

# 27. Inclusive Aggregation

Extend the Phase 3 bottom-up hierarchy aggregation.

For each directory:

```text
inclusive_allocated_bytes =
    direct_allocated_bytes
    + sum(child inclusive allocated bytes)
```

Only produce a complete inclusive allocated value when:

* direct allocated status is complete enough;
* all included descendants have usable allocated values;
* hierarchy is valid.

Otherwise:

```text
inclusive allocation status = partial
```

The numeric value may still be stored as the known subtotal, but it must be clearly labeled incomplete.

---

# 28. Allocated Delta Rules

For comparable scans:

```text
direct_allocated_delta =
    current_direct_allocated_bytes
    - previous_direct_allocated_bytes
```

Only calculate a trusted delta when both values are usable.

If either value is incomplete or unavailable:

```text
direct_allocated_delta = NULL
```

Do not substitute the logical delta.

Logical and allocated deltas must remain separate.

---

# 29. New and Removed Directories

## New directory

When current allocated measurement is usable:

```text
previous allocated = 0
current allocated = measured value
allocated delta = current allocated
```

## Removed directory

When previous allocated measurement is usable:

```text
previous allocated = measured value
current allocated = 0
allocated delta = -previous allocated
```

If allocation was incomplete in the relevant scan, the allocated delta is unavailable.

Logical state may still be reportable.

---

# 30. Primary Reporting Metric

When measurement mode is `allocated_preferred` and coverage is sufficient:

* rank primary disk-consumption reports by direct allocated delta;
* retain logical delta as a secondary column.

When allocation coverage is insufficient:

* default to logical reporting;
* display a warning that physical allocation coverage was incomplete;
* do not mix allocated and logical values in one total.

When mode is `allocated_required`:

* omit incomplete allocated deltas from trusted totals;
* show incomplete counts prominently.

---

# 31. Measurement Selection Service

Create a dedicated service to determine which metric drives a report.

Recommended interface:

```python
class MeasurementSelector:
    def select_for_comparison(
        self,
        baseline_scan_id: int,
        current_scan_id: int,
    ) -> "MeasurementSelection":
        ...
```

Recommended result:

```python
class MeasurementSelection(BaseModel):
    primary_metric: str
    logical_available: bool
    allocated_available: bool
    allocated_coverage_percent: float | None
    confidence: str
    reason: str
```

Possible primary metrics:

```text
allocated
logical
none
```

---

# 32. Volume Reconciliation Changes

Phase 5 reconciliation currently uses logical folder deltas.

Extend reconciliation to support:

```text
explained_logical_delta_bytes
explained_allocated_delta_bytes
selected_explained_delta_bytes
selected_measurement_type
```

When allocated data is sufficiently complete:

```text
unexplained_delta =
    observed_volume_delta
    - explained_allocated_delta
```

Otherwise, retain logical reconciliation.

Do not overwrite historical logical reconciliation fields without migration.

---

# 33. Reconciliation Table Changes

Extend `scan_reconciliations` with:

```text
explained_logical_delta_bytes       INTEGER NULL
explained_allocated_delta_bytes     INTEGER NULL
selected_explained_delta_bytes      INTEGER NULL
selected_measurement_type           TEXT NOT NULL DEFAULT 'logical'
allocated_coverage_percent          REAL NULL
allocation_incomplete_directory_count INTEGER NOT NULL DEFAULT 0
allocation_warning_count            INTEGER NOT NULL DEFAULT 0
```

Historical records should retain:

```text
selected_measurement_type = logical
```

---

# 34. Reconciliation Confidence

Allocated reconciliation may receive high confidence when:

* full-volume scope;
* compatible allocated providers;
* coverage meets threshold;
* few or no allocation failures;
* no cross-volume ambiguity;
* no significant hard-link uncertainty;
* low intra-scan activity;
* volume identity matches;
* scan and hierarchy complete.

Medium confidence when:

* coverage is high but not complete;
* estimated allocation is present;
* minor provider failures occurred;
* logical and allocated results differ substantially but plausibly.

Low confidence when:

* coverage below threshold;
* many unknown allocated bytes;
* significant hard-link uncertainty;
* partial-volume scope;
* cross-volume activity;
* large intra-scan change.

---

# 35. Logical-to-Allocated Difference

Calculate and expose:

```text
allocation_difference_bytes =
    logical_bytes - allocated_bytes
```

This value is descriptive.

It may be positive or, because of cluster rounding, allocated size may exceed logical size for small files.

Do not label all difference as compression.

Possible causes include:

* sparse allocation;
* compression;
* cluster rounding;
* unknown allocation;
* hard-link duplication;
* filesystem behavior.

---

# 36. Scan Lifecycle Changes

Recommended sequence:

```text
scan starts
→ volume-before capture
→ logical and allocated measurement
→ direct snapshot persistence
→ hierarchy aggregation
→ volume-after capture
→ logical comparison
→ allocated comparison
→ measurement selection
→ volume reconciliation
→ report generation
```

If allocated measurement fails globally:

* retain logical scan results;
* mark allocated status failed;
* continue logical comparison and reconciliation;
* do not fail the entire scan unless mode is `allocated_required` and the specification requires failure.

Recommended `allocated_required` behavior:

* scan may complete with incomplete allocated measurement;
* allocated comparison unavailable;
* logical results retained;
* prominent error status shown.

---

# 37. Progress Events

Add progress information:

```text
files with allocation measured
allocation failures
allocated bytes measured
logical bytes awaiting allocation
allocation coverage percentage
```

Recommended event fields:

```python
class AllocationProgress(BaseModel):
    scan_id: int
    files_attempted: int
    files_measured: int
    files_failed: int
    logical_bytes_measured: int
    logical_bytes_with_allocation: int
    coverage_percent: float | None
```

Throttle events to avoid GUI overhead.

---

# 38. Scanner Performance

Allocated-size lookup may add one Windows API call per file.

Requirements:

* call the provider only once per file;
* reuse the existing stat result;
* avoid opening persistent file handles;
* avoid provider calls in `logical_only` mode;
* batch observation persistence;
* measure performance impact;
* allow cancellation during large directories;
* preserve GUI responsiveness.

Do not parallelize filesystem measurement in Phase 6 unless profiling proves it necessary and thread safety is well understood.

---

# 39. Performance Benchmarking

Benchmark at least:

* 10,000 small files;
* 1,000 medium files;
* a directory with sparse files;
* a directory with compressed files where practical;
* logical-only versus allocated-preferred mode.

Record:

```text
files per second
directories per second
provider failures
scan duration
database write duration
memory usage
```

Document the expected overhead.

---

# 40. Error Handling

Persist warnings for:

```text
query_allocated_size
query_allocation_unit
inspect_sparse_attribute
inspect_compressed_attribute
calculate_allocation_coverage
aggregate_allocated_size
compare_allocated_snapshots
reconcile_allocated_delta
```

Common failures include:

* access denied;
* file disappeared;
* unsupported filesystem;
* invalid path;
* long-path API issue;
* cloud placeholder unavailable;
* Windows API failure.

Do not terminate the scan for isolated provider failures.

---

# 41. Unsupported Filesystems

The provider must report when allocated measurement is unsupported.

Possible cases include:

* network shares;
* non-Windows filesystems;
* virtual providers;
* special devices;
* inaccessible mounts.

Behavior:

* retain logical size;
* mark allocation unavailable;
* downgrade scan coverage;
* do not estimate unless explicitly allowed and safe;
* report the filesystem name when known.

---

# 42. Network Paths

UNC paths may be scanned logically if the application already supports them.

Allocated-size behavior for network paths must be conservative.

Default:

```text
attempt provider only when supported
otherwise mark unavailable
```

Do not assume remote allocation corresponds to local disk consumption.

Volume reconciliation should remain unavailable for network paths unless a reliable provider exists.

---

# 43. GUI Requirements

Add a measurement selector or display mode.

Recommended control:

```text
Measurement:
- Physical allocation
- Logical size
- Both
```

## 43.1 Main table

Recommended columns:

```text
Folder
Allocated Change
Logical Change
Current Allocated
Current Logical
Allocation Coverage
Confidence
```

Default columns may remain compact, with additional fields available in detail view.

## 43.2 Summary panel

Display:

```text
Logical net change
Allocated net change
Observed volume change
Allocated explained change
Unexplained change
Allocation coverage
Allocation failures
Primary measurement
```

## 43.3 Folder detail

Display:

```text
Previous logical size
Current logical size
Logical delta

Previous allocated size
Current allocated size
Allocated delta

Allocation coverage
Unknown logical bytes
Estimated allocated bytes
Sparse/compressed indicators where available
Confidence
```

## 43.4 Warning behavior

If allocated coverage is incomplete:

```text
Physical allocation was measured for 96.4% of logical bytes.
The physical-growth total is incomplete.
```

---

# 44. CLI Requirements

Extend the Typer CLI.

## Scan mode

```powershell
uv run folder-diff-cli scan --measurement allocated-preferred
```

Supported options:

```text
--measurement logical-only
--measurement allocated-preferred
--measurement allocated-required
```

## Report mode

```powershell
uv run folder-diff-cli report --metric allocated
```

Options:

```text
--metric logical
--metric allocated
--metric both
--include-incomplete
```

## Allocation summary

```powershell
uv run folder-diff-cli allocation-summary --scan-id 15
```

Display:

```text
Provider
Algorithm version
Coverage
Files measured
Failures
Estimated files
Unknown logical bytes
```

## JSON output

Recommended:

```powershell
uv run folder-diff-cli report --metric both --json
```

---

# 45. Text Report Changes

Add:

```text
MEASUREMENT SUMMARY
------------------------------------------------------------
Mode:                         Allocated preferred
Allocated-size provider:      Windows compressed-file-size API
Allocation coverage:          99.72%
Allocation failures:          38
Unknown logical bytes:        112.4 MB
Estimated allocation:         Disabled
```

Add comparison:

```text
SIZE CHANGE SUMMARY
------------------------------------------------------------
Logical net change:           +8.42 GB
Allocated net change:         +2.31 GB
Observed volume change:       +2.44 GB
Unexplained difference:       +0.13 GB
```

Add limitation:

```text
Allocated totals do not yet deduplicate hard-linked files.
```

---

# 46. Migration and Baseline Behavior

The first Phase 6 allocated scan establishes a new allocated baseline.

Do not compare allocated values against pre-Phase 6 scans.

Logical comparison may continue against a compatible prior logical baseline.

A scan may therefore have:

```text
Logical baseline:    scan 14
Allocated baseline:  none
```

After another allocated-compatible scan:

```text
Logical baseline:    scan 15
Allocated baseline:  scan 15
```

The database design may use one baseline scan when both metrics align, but comparison services must recognize metric-specific compatibility.

---

# 47. Metric-Specific Baselines

Create or extend baseline selection so it can select by metric.

Recommended interface:

```python
class BaselineSelector:
    def find_previous_comparable_scan(
        self,
        current_scan_id: int,
        metric: Literal["logical", "allocated"],
    ) -> ScanRecord | None:
        ...
```

Allocated baseline selection must require:

* compatible provider;
* compatible algorithm version;
* usable allocation status;
* sufficient coverage;
* same volume and scan target;
* compatible reparse and hierarchy settings.

---

# 48. Historical Data

Do not backfill allocated size from logical size.

Historical records should show:

```text
Allocated measurement: Not available
```

Do not remove or invalidate historical logical snapshots.

---

# 49. Domain Models

## Allocated size result

```python
class AllocatedSizeResult(BaseModel):
    allocated_bytes: int | None
    provider: str
    status: str
    is_estimated: bool
    error_code: int | None = None
    error_message: str | None = None
```

## Folder measurement

```python
class FolderMeasurement(BaseModel):
    logical_bytes: int
    allocated_bytes: int | None

    file_count: int
    allocated_file_count: int
    allocation_failed_file_count: int

    allocation_unknown_logical_bytes: int
    allocation_coverage_percent: float | None
    allocation_status: str
```

## Metric comparison

```python
class MetricDiff(BaseModel):
    previous_bytes: int | None
    current_bytes: int | None
    delta_bytes: int | None
    confidence: str
    confidence_reason: str
```

## Directory diff

```python
class DirectoryDiff(BaseModel):
    path: Path
    logical: MetricDiff
    allocated: MetricDiff
    state: str
```

---

# 50. Service Boundaries

Recommended structure:

```text
scanner/allocated_size.py
- provider abstraction
- Windows allocated-size implementation

scanner/volume_allocation.py
- cluster and allocation-unit information

scanner/folder_scanner.py
- orchestrates logical and allocated measurement
- no historical comparison logic

analysis/hierarchy.py
- aggregates logical and allocated values

analysis/differ.py
- compares logical and allocated snapshots

analysis/measurement_selector.py
- chooses primary metric

analysis/reconciliation.py
- reconciles selected metric with volume change

db/
- persists measurement fields

reporting/
- formats logical and allocated results

gui/
- presents measurement selection and coverage
```

---

# 51. Testing Requirements

Use temporary files, temporary SQLite databases, mocks, and Windows-specific fixtures.

## 51.1 Normal file

Create a regular file.

Verify:

* logical size recorded;
* allocated size is non-null;
* allocated size is at least zero;
* allocated size aligns with filesystem allocation behavior.

Do not require exact cluster size unless the test obtains it dynamically.

## 51.2 Empty file

Expected:

```text
logical = 0
allocated = 0
```

## 51.3 Small file

A one-byte file may occupy one allocation unit.

Expected:

```text
logical = 1
allocated >= 1
```

## 51.4 Sparse file

Create a sparse file where privileges and filesystem support permit.

Expected:

```text
logical size significantly greater than allocated size
```

## 51.5 Compressed file

Conditionally test NTFS compression.

Expected:

* logical and allocated values stored separately;
* allocated size may be lower;
* status indicates measured.

## 51.6 Same logical size, changed allocation

Where practical, create a case in which allocation changes without logical size changing.

Expected:

```text
logical delta = 0
allocated delta != 0
```

If difficult to create reliably, test with mocked provider results.

## 51.7 File growth

Baseline:

```text
logical = 100 MB
allocated = 100 MB
```

Current:

```text
logical = 150 MB
allocated = 150 MB
```

Expected:

```text
logical delta = +50 MB
allocated delta = +50 MB
```

## 51.8 Sparse logical growth

Baseline:

```text
logical = 1 GB
allocated = 100 MB
```

Current:

```text
logical = 10 GB
allocated = 120 MB
```

Expected:

```text
logical delta = +9 GB
allocated delta = +20 MB
```

## 51.9 Provider failure

Mock allocation lookup failure.

Expected:

* logical size retained;
* allocated size `NULL`;
* failure count incremented;
* coverage reduced;
* warning persisted.

## 51.10 Logical-only mode

Expected:

* no provider calls;
* allocated values `NULL`;
* allocated status `not_requested`.

## 51.11 Allocated-preferred mode

Expected:

* provider attempted;
* logical fallback remains available;
* scan may complete with partial allocation.

## 51.12 Allocated-required mode

Expected:

* unknown allocated values remain unavailable;
* no logical substitution;
* allocated confidence downgraded;
* logical results retained.

## 51.13 Coverage calculation

Verify byte-weighted coverage.

Example:

```text
File A: 900 bytes, allocation measured
File B: 100 bytes, allocation failed
```

Expected:

```text
coverage = 90%
```

Not 50%.

## 51.14 Empty-directory coverage

Expected:

```text
coverage = 100%
```

when enumeration completed.

## 51.15 Inclusive allocated aggregation

Create nested directories.

Verify:

* direct allocated values;
* inclusive allocated values;
* no parent/child double counting in totals.

## 51.16 Allocated comparison baseline

First allocated scan:

```text
allocated baseline created
```

Second compatible scan:

```text
allocated comparison available
```

## 51.17 Provider version mismatch

Expected:

```text
allocated scans not automatically comparable
```

## 51.18 Coverage below threshold

Expected:

* allocated total marked partial;
* logical metric selected as primary in preferred mode.

## 51.19 Coverage above threshold

Expected:

* allocated metric selected as primary.

## 51.20 Reconciliation

Observed volume:

```text
+200 MB
```

Logical explained:

```text
+1 GB
```

Allocated explained:

```text
+190 MB
```

Expected:

```text
selected metric = allocated
unexplained = +10 MB
```

## 51.21 Hard-link disclaimer

Verify reports include the limitation when allocated reporting is active.

## 51.22 Historical scan

Verify pre-Phase 6 scan remains readable and allocated values display as unavailable.

## 51.23 Long path

Verify allocated provider supports long paths.

## 51.24 File disappears

Expected:

* logical or allocated warning;
* no crash;
* incomplete status.

## 51.25 Unsupported filesystem

Expected:

* logical measurement available;
* allocated unavailable;
* clear provider status.

## 51.26 Cancellation

Verify cancellation during allocation measurement:

* stops promptly;
* emits one terminal event;
* partial results remain consistently marked.

## 51.27 Performance benchmark

Verify no accidental multiple provider calls per file.

---

# 52. Acceptance Criteria

Phase 6 is complete when all of the following are true:

1. Logical and allocated sizes are stored separately.
2. Allocated size is measured through a dedicated provider abstraction.
3. The Windows provider supports 64-bit allocation values.
4. Long paths are supported.
5. Provider errors are distinguished from valid zero results.
6. Logical size is never silently substituted for allocated size.
7. Logical-only mode makes no allocation API calls.
8. Allocated-preferred mode falls back transparently.
9. Allocated-required mode preserves unknown values as unknown.
10. Folder observations store direct allocated bytes.
11. Hierarchy aggregation stores inclusive allocated bytes.
12. Allocation coverage is byte weighted.
13. Scan-level coverage is calculated from non-overlapping direct values.
14. Unknown allocated bytes are tracked.
15. Estimated values are disabled by default.
16. Estimated values are clearly labeled when enabled.
17. Sparse files can show logical size greater than allocated size.
18. Compressed files retain separate logical and allocated values.
19. Allocated deltas are calculated only between compatible scans.
20. The first allocated-compatible scan creates a new allocated baseline.
21. Historical logical comparisons remain available.
22. Primary reporting uses allocated delta when coverage is sufficient.
23. Reporting falls back to logical delta when allocation is insufficient.
24. Logical and allocated totals are never mixed silently.
25. Reconciliation can use allocated direct deltas.
26. Reconciliation retains logical results for comparison.
27. Inclusive allocated values are not summed across hierarchy levels.
28. Provider failures do not invalidate logical scan results.
29. GUI displays metric, coverage, and failures.
30. CLI supports logical, allocated, and combined reports.
31. Text reports include logical and allocated summaries.
32. Reports disclose that hard links are not yet deduplicated.
33. Existing database history remains readable.
34. All prior tests continue to pass.
35. All Phase 6 tests pass with:

```powershell
uv run pytest
```

36. The application is prepared for Phase 7 file-level forensics and physical identity.

---

# 53. Coding-Agent Assignment

Implement Phase 6 only.

Add physical allocated-size measurement while preserving all existing logical-size measurements.

Create an `AllocatedSizeProvider` abstraction and implement a Windows provider using an appropriate Windows API such as the equivalent of `GetCompressedFileSizeW`.

For every direct file:

1. obtain logical size from the existing stat result;
2. attempt allocated-size measurement according to the configured mode;
3. store logical and allocated values separately;
4. record failures without substituting logical size for allocated size.

Add these measurement modes:

```text
logical_only
allocated_preferred
allocated_required
```

In `logical_only` mode, do not call allocated-size APIs.

In `allocated_preferred` mode, retain logical results when allocation lookup fails and select allocated reporting only when coverage meets the configured threshold.

In `allocated_required` mode, preserve unknown allocated values as unavailable and exclude them from trusted allocated totals.

Persist:

* direct allocated bytes;
* inclusive allocated bytes;
* allocation file counts;
* allocation failure counts;
* unknown logical bytes;
* allocation coverage;
* provider name;
* provider version;
* measurement status.

Extend hierarchy aggregation and scan comparison to calculate logical and allocated values independently.

Add metric-specific baseline compatibility. Pre-Phase 6 scans may remain logical baselines but cannot serve as allocated baselines.

Extend volume reconciliation to retain:

* explained logical delta;
* explained allocated delta;
* selected explained delta;
* selected measurement type.

Use allocated direct deltas for reconciliation when allocation coverage is sufficient. Otherwise, retain logical reconciliation and explain the fallback.

Update GUI, CLI, and text reports to show:

* logical change;
* allocated change;
* allocation coverage;
* allocation failures;
* primary measurement;
* observed volume change;
* unexplained difference.

Do not implement hard-link deduplication, file-level historical cataloging, move detection, VSS analysis, system-file attribution, retention, or scheduling.

The completed Phase 6 application must distinguish between the logical size of files and the physical bytes they occupy, while clearly communicating measurement coverage and uncertainty.
