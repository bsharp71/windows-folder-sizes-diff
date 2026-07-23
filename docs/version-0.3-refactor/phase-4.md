# Phase 4 Technical Specification

Implement Phase 4 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 4. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Reparse-Point Protection and Canonical Directory Identity

**Project:** `windows-folder-sizes-diff`
**Phase:** 4 — Reparse-Point and Alias Protection
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Windows integration:** pywin32
**Prerequisites:** Phases 0–3 completed

---

# 1. Objective

Prevent the application from scanning and counting the same physical directory tree through multiple Windows paths.

Phase 4 must address duplicate and unsafe traversal caused by:

* directory junctions;
* symbolic links;
* mount points;
* other Windows reparse points;
* compatibility aliases;
* path-format differences;
* traversal cycles;
* repeated references to the same target.

The original application produced duplicate entries such as:

```text
C:\ProgramData\AppControl
C:\Users\All Users\AppControl
```

`C:\Users\All Users` is a compatibility junction that redirects to `C:\ProgramData`.

Without explicit reparse-point handling, the same underlying content may be:

* scanned more than once;
* stored under multiple directory identities;
* reported as separate growth;
* included multiple times in totals;
* revisited through a cycle.

At the end of Phase 4, the application must:

* detect Windows reparse points explicitly;
* skip traversal through them by default;
* persist reparse-point metadata;
* preserve the source path as an observed filesystem object;
* distinguish normal directories from aliases and links;
* use one consistent canonical path representation;
* prevent traversal cycles and duplicate target scans;
* expose clear reporting about skipped aliases;
* preserve all Phase 3 direct and inclusive comparison behavior.

---

# 2. Prerequisite Behavior

Phase 3 is expected to provide:

* direct logical-size snapshots;
* true scan-to-scan deltas;
* parent-child directory relationships;
* directory depth;
* inclusive subtree measurements;
* hierarchy validation;
* direct and inclusive comparison results;
* non-overlapping direct-growth totals;
* GUI and CLI reports;
* SQLite persistence;
* path-based directory identity;
* scan configuration hashes;
* structured warnings.

Phase 4 must extend those capabilities without changing their meaning.

---

# 3. Phase 4 Scope

Implement:

* explicit Windows reparse-point detection;
* reparse-tag capture;
* default skip behavior for directory reparse points;
* storage of source path and resolved target where available;
* canonical path normalization;
* duplicate-target detection;
* cycle prevention;
* reparse-aware hierarchy handling;
* configuration compatibility for reparse policy;
* GUI, CLI, and text-report visibility;
* migration and tests.

Do not implement:

* allocated physical size;
* hard-link deduplication;
* file-level NTFS identity;
* file move detection;
* volume reconciliation;
* retention policies;
* VSS analysis;
* NTFS metadata parsing;
* following reparse points by default;
* network-share crawling through aliases.

Those belong to later phases or optional advanced features.

---

# 4. Terminology

Use these terms consistently.

## 4.1 Reparse point

A filesystem object with the Windows reparse-point attribute.

Common examples:

* junction;
* symbolic link;
* mount point;
* cloud placeholder;
* application-specific reparse object.

## 4.2 Junction

A directory reparse point that redirects to another directory.

Example:

```text
C:\Users\All Users
→ C:\ProgramData
```

## 4.3 Symbolic link

A filesystem object that redirects to another file or directory.

## 4.4 Mount point

A directory that redirects traversal to another mounted volume.

## 4.5 Source path

The path encountered during traversal.

Example:

```text
C:\Users\All Users
```

## 4.6 Target path

The resolved destination of a link or junction.

Example:

```text
C:\ProgramData
```

## 4.7 Canonical path

The normalized path representation used for database comparison and identity.

Canonical path does not necessarily mean that all reparse targets have been followed.

## 4.8 Physical identity

A filesystem identity based on volume and file identifiers rather than path text.

Phase 4 may use physical directory identity where accessible, but full NTFS object identity is not required for all files.

---

# 5. Default Policy

The default scan policy must be:

```text
Detect directory reparse points.
Record them.
Do not recurse into them.
Do not include their target contents in the source directory’s inclusive size.
```

This policy prevents duplicate-tree traversal while preserving awareness that the alias exists.

Example:

```text
C:\Users\All Users
```

Expected behavior:

* directory identity stored;
* marked as a reparse point;
* target recorded as `C:\ProgramData` when resolvable;
* traversal skipped;
* no descendant observations created through this path;
* target content counted only through its normal scanned path, if within the target root;
* warning or informational event emitted.

---

# 6. Configuration Changes

Add reparse-point settings.

Recommended configuration:

```yaml
FollowReparsePoints: false
RecordReparseTargets: true
PreventDuplicateTargets: true
AllowCrossVolumeReparseTargets: false
```

Recommended Pydantic fields:

```python
class AppSettings(BaseModel):
    follow_reparse_points: bool = False
    record_reparse_targets: bool = True
    prevent_duplicate_targets: bool = True
    allow_cross_volume_reparse_targets: bool = False
```

Phase 4 must support only safe behavior by default.

If `FollowReparsePoints` is enabled:

* duplicate-target detection remains mandatory;
* cycle protection remains mandatory;
* cross-volume targets remain blocked unless explicitly enabled;
* report confidence must be downgraded when target identity is uncertain.

Do not expose a mode that follows reparse points without duplicate and cycle protection.

---

# 7. Configuration Hash Changes

Add these settings to the measurement compatibility hash:

```text
follow_reparse_points
record_reparse_targets
prevent_duplicate_targets
allow_cross_volume_reparse_targets
reparse_detection_version
canonical_path_version
```

Scans with different traversal policies must not be considered automatically comparable.

Example:

```python
payload = {
    "target_path": normalized_target_path,
    "measurement_algorithm_version": 2,
    "hierarchy_algorithm_version": 1,
    "reparse_detection_version": 1,
    "canonical_path_version": 2,
    "follow_reparse_points": False,
    "prevent_duplicate_targets": True,
    "allow_cross_volume_reparse_targets": False,
    "exclusions": normalized_exclusions,
}
```

---

# 8. Database Changes

Create a new Alembic migration.

Do not modify prior migration files.

## 8.1 `directories` table changes

Add:

```text
is_reparse_point         BOOLEAN NOT NULL DEFAULT 0
reparse_tag              INTEGER NULL
reparse_type             TEXT NULL
reparse_target_path      TEXT NULL
normalized_target_path   TEXT NULL
target_volume_id         TEXT NULL
filesystem_object_id     TEXT NULL
identity_status          TEXT NOT NULL DEFAULT 'path_only'
traversal_status         TEXT NOT NULL DEFAULT 'normal'
```

Recommended `reparse_type` values:

```text
junction
symbolic_link
mount_point
cloud_placeholder
other
unknown
```

Recommended `identity_status` values:

```text
path_only
canonical_path
volume_and_file_id
target_resolved
target_unresolved
identity_failed
```

Recommended `traversal_status` values:

```text
normal
skipped_reparse
followed_reparse
duplicate_target
cycle_prevented
cross_volume_blocked
target_unavailable
```

## 8.2 Optional dedicated `reparse_points` table

A dedicated table is recommended if reparse metadata may vary by scan.

Suggested schema:

```text
id                       INTEGER PRIMARY KEY
scan_id                  INTEGER NOT NULL
directory_id             INTEGER NOT NULL
source_path              TEXT NOT NULL
normalized_source_path   TEXT NOT NULL
reparse_tag              INTEGER NULL
reparse_type             TEXT NOT NULL
target_path              TEXT NULL
normalized_target_path   TEXT NULL
source_volume_id         TEXT NULL
target_volume_id         TEXT NULL
followed                  BOOLEAN NOT NULL DEFAULT 0
decision                  TEXT NOT NULL
decision_reason           TEXT NULL
detected_at               DATETIME NOT NULL
```

Constraint:

```text
UNIQUE(scan_id, directory_id)
```

This table is preferred because:

* a link target may change between scans;
* the decision to follow or skip depends on scan configuration;
* scan history should preserve what was observed at that time.

The `directories` table may retain only stable or latest-known identity fields.

## 8.3 Indexes

Add:

```text
directories(is_reparse_point)
directories(filesystem_object_id)
reparse_points(scan_id)
reparse_points(normalized_target_path)
reparse_points(decision)
```

Do not assume `filesystem_object_id` is always available or unique across volumes.

---

# 9. Windows Reparse-Point Detection

Create a dedicated Windows filesystem abstraction.

Recommended structure:

```text
scanner/windows_fs.py
scanner/reparse_points.py
scanner/path_identity.py
```

Recommended protocol:

```python
class ReparsePointInspector(Protocol):
    def inspect(self, path: Path) -> ReparsePointInfo:
        ...
```

Recommended result model:

```python
class ReparsePointInfo(BaseModel):
    path: Path
    is_reparse_point: bool
    reparse_tag: int | None
    reparse_type: str | None
    target_path: Path | None
    target_volume_id: str | None
    filesystem_object_id: str | None
    identity_status: str
```

Use pywin32 or Windows APIs where necessary.

Do not rely exclusively on:

```python
entry.is_symlink()
```

Windows junctions may not behave like ordinary symbolic links in all Python APIs.

At minimum, inspect:

```text
FILE_ATTRIBUTE_REPARSE_POINT
```

and retrieve the reparse tag where possible.

---

# 10. Reparse-Type Classification

Map known Windows reparse tags to application types.

At minimum, distinguish:

```text
symbolic_link
mount_point_or_junction
other
unknown
```

If reliably distinguishable, separate:

```text
junction
mount_point
```

Unknown reparse tags must not be treated as normal directories.

Default behavior for unknown directory reparse points:

```text
record and skip
```

Do not recurse merely because the application does not recognize the tag.

---

# 11. Canonical Path Normalization

Replace Phase 1’s basic path normalization with a versioned canonicalization service.

Recommended interface:

```python
class PathCanonicalizer:
    version = 2

    def canonicalize(self, path: Path | str) -> CanonicalPath:
        ...
```

Recommended model:

```python
class CanonicalPath(BaseModel):
    display_path: str
    absolute_path: str
    normalized_path: str
    comparison_key: str
    long_path: str | None
    volume_root: str | None
```

Canonicalization should:

* make the path absolute;
* normalize separators;
* remove redundant `.` and `..`;
* normalize trailing separators;
* normalize drive-letter casing;
* apply case-insensitive comparison;
* preserve the original display path;
* support long paths;
* avoid blindly resolving through reparse points.

Do not use `Path.resolve()` as the sole identity function because it may:

* follow links;
* fail on inaccessible paths;
* change the intended source path;
* create inconsistent behavior.

---

# 12. Path Identity Rules

Maintain separate concepts:

```text
source path identity
target path identity
physical object identity
```

## 12.1 Source path identity

Used to record that a filesystem entry exists at a particular location.

Example:

```text
C:\Users\All Users
```

## 12.2 Target identity

Used to determine whether traversal would reach a location already scanned.

Example:

```text
C:\ProgramData
```

## 12.3 Physical object identity

When available, combine:

```text
volume serial number
file index or file reference number
```

Recommended identity key:

```text
volume_id:file_id
```

Use this only when retrieved reliably.

Do not merge directories across different volumes using file ID alone.

---

# 13. Traversal Decision Service

Create a dedicated service.

Recommended interface:

```python
class TraversalPolicy:
    def decide(
        self,
        *,
        source_path: Path,
        reparse_info: ReparsePointInfo,
        visited_paths: set[str],
        visited_objects: set[str],
        active_ancestry: set[str],
        settings: AppSettings,
    ) -> TraversalDecision:
        ...
```

Recommended model:

```python
class TraversalDecision(BaseModel):
    action: str
    reason: str
    record_target: bool
    confidence: str
```

Allowed actions:

```text
traverse
skip_reparse
skip_duplicate_target
skip_cycle
skip_cross_volume
skip_unresolved_target
```

The decision logic must be independent of GUI presentation.

---

# 14. Default Traversal Rules

## Normal directory

```text
action = traverse
```

## Reparse point with default settings

```text
action = skip_reparse
```

## Reparse point whose target is already visited

```text
action = skip_duplicate_target
```

## Reparse point whose target is in the active ancestor chain

```text
action = skip_cycle
```

## Reparse point targeting another volume while cross-volume traversal is disabled

```text
action = skip_cross_volume
```

## Reparse point whose target cannot be resolved

Default:

```text
action = skip_unresolved_target
```

Do not guess.

---

# 15. Duplicate-Target Detection

Maintain scan-scoped sets for:

```text
visited canonical path keys
visited physical object IDs
active ancestry object IDs
```

Preferred duplicate detection order:

1. Physical object identity when available.
2. Normalized resolved target path.
3. Canonical source path fallback.

If a target has already been scanned:

* record the alias;
* do not traverse it again;
* mark traversal status `duplicate_target`;
* do not count its target content again.

Example:

```text
C:\ProgramData
C:\Users\All Users → C:\ProgramData
```

Expected:

```text
C:\ProgramData scanned normally
C:\Users\All Users recorded as alias
C:\Users\All Users descendants not scanned
```

---

# 16. Cycle Prevention

A cycle may occur through nested links.

Example:

```text
C:\A\LinkToB → C:\B
C:\B\LinkToA → C:\A
```

The scanner must terminate safely.

Maintain an active ancestry set separate from the general visited set.

If a target points to an active ancestor:

```text
decision = cycle_prevented
```

Record a structured warning.

Do not continue traversal.

Do not rely only on maximum depth as cycle protection.

A depth limit may exist as a secondary safety measure but not as the primary mechanism.

---

# 17. Cross-Volume Behavior

A junction or mount point may redirect to another volume.

Default behavior:

```text
record and skip
```

unless:

```text
AllowCrossVolumeReparseTargets = true
```

When cross-volume traversal is enabled:

* record source and target volume IDs;
* include the target volume in scan metadata;
* ensure physical identity keys include volume identity;
* prevent duplicate traversal on the target volume;
* clearly report that the scan crossed volumes;
* downgrade comparability if baseline scans used different volume topology.

Phase 4 does not need to support multi-volume reconciliation.

---

# 18. Cloud and Application Reparse Points

Some reparse points may represent:

* OneDrive placeholders;
* cloud files;
* application virtualization;
* deduplicated storage;
* third-party filesystem filters.

Do not assume every reparse point is a directory alias.

Default behavior for unfamiliar tags:

```text
record metadata
skip traversal
mark type other or unknown
```

Do not attempt to hydrate cloud files.

Do not trigger network downloads.

Do not treat placeholder logical size as authoritative physical disk usage.

---

# 19. Scanner Changes

The scanner must inspect directory entries before adding them to the traversal queue.

Recommended flow:

1. Enumerate entry.
2. Determine whether entry is a directory without following links.
3. Check reparse-point attributes.
4. Inspect reparse metadata.
5. Record directory observation metadata.
6. Apply traversal policy.
7. Enqueue only when action is `traverse`.

Do not enqueue first and inspect later.

Recommended event:

```python
class ReparsePointDetected(BaseModel):
    scan_id: int
    source_path: Path
    reparse_tag: int | None
    reparse_type: str
    target_path: Path | None
    decision: str
    reason: str
    detected_at: datetime
```

---

# 20. Hierarchy Behavior

Skipped reparse points remain visible as directory nodes but must not inherit the target’s children.

Example:

```text
C:\Users
└── All Users  [junction → C:\ProgramData, skipped]
```

Expected hierarchy:

* `All Users` has its real source parent `C:\Users`;
* no target descendants are attached beneath it;
* direct size may be zero or unavailable depending on enumeration behavior;
* inclusive size must not include `C:\ProgramData`;
* hierarchy status should indicate skipped reparse traversal.

Recommended hierarchy status:

```text
skipped_reparse
```

Skipped reparse nodes must not make the rest of the parent hierarchy partial unless their skipped target was intentionally part of the configured scan scope.

Because skipping is policy-driven and expected, distinguish:

```text
intentionally skipped
```

from:

```text
inaccessible or failed
```

---

# 21. Measurement Status Changes

Add statuses where needed:

```text
skipped_reparse
duplicate_target
cycle_prevented
cross_volume_blocked
target_unresolved
```

These states must not be treated as zero-byte complete measurements.

For direct size:

* a reparse-point directory may have no meaningful direct measurement;
* store `NULL` when not measured;
* do not invent zero unless the source object was safely enumerated and truly contained no direct files.

For inclusive size:

```text
NULL or explicitly unavailable
```

when traversal was intentionally skipped.

---

# 22. Comparison Rules

Two reparse-point observations may be compared when:

* the source path identity is the same;
* the reparse policy is compatible;
* the reparse type is compatible;
* the target identity is unchanged or the change is explicitly reported.

Recommended reparse comparison states:

```text
unchanged_alias
target_changed
new_alias
removed_alias
policy_changed
not_comparable
```

Do not treat a changed target as ordinary folder growth.

Example:

Previous:

```text
C:\Alias → C:\DataA
```

Current:

```text
C:\Alias → C:\DataB
```

Expected:

```text
state = target_changed
delta = unavailable
```

The target trees may be compared separately through their real paths if scanned.

---

# 23. Confidence Rules

## High confidence

* reparse point detected explicitly;
* tag known;
* target resolved;
* physical or canonical target identity available;
* traversal skipped by policy;
* no duplicate content counted.

## Medium confidence

* reparse attribute detected;
* target path resolved;
* physical object ID unavailable;
* duplicate detection relies on canonical target path.

## Low confidence

* target resolution failed;
* reparse type unknown;
* physical identity unavailable;
* user forced traversal.

## Unavailable

* reparse metadata could not be read;
* traversal decision could not be determined safely.

Default to skipping when confidence is insufficient.

---

# 24. GUI Requirements

Add reparse-point visibility without overwhelming the main report.

## 24.1 Summary panel

Display:

```text
Reparse points detected
Reparse points skipped
Duplicate targets prevented
Cycles prevented
Cross-volume targets blocked
Unresolved targets
```

## 24.2 Folder table

Add optional indicators:

```text
Alias
Junction
Symlink
Mount point
Skipped
Duplicate target
```

Do not add all reparse metadata as default columns.

## 24.3 Detail panel

For a selected reparse-point directory, display:

```text
Source path
Reparse type
Reparse tag
Target path
Source volume
Target volume
Traversal decision
Decision reason
Identity confidence
```

## 24.4 Settings

Add advanced controls:

```text
Follow reparse points
Allow cross-volume targets
```

These controls must include warning text.

Recommended default:

```text
Follow reparse points: Off
```

---

# 25. CLI Requirements

Extend the Typer CLI.

## 25.1 List reparse points

```powershell
uv run folder-diff-cli reparse-points --scan-id 14
```

Columns:

```text
Source
Type
Target
Decision
Reason
```

Options:

```text
--decision
--type
--unresolved-only
--limit
```

## 25.2 Show one reparse point

```powershell
uv run folder-diff-cli reparse-show --scan-id 14 "C:\Users\All Users"
```

Display full metadata.

## 25.3 Scan options

If CLI scanning exists:

```powershell
uv run folder-diff-cli scan --follow-reparse-points
```

Require explicit confirmation or a second flag when following links:

```text
--allow-risky-traversal
```

A simpler acceptable design is to keep following disabled in Phase 4 CLI and only prepare the setting.

## 25.4 Report summary

Include:

```text
Aliases skipped
Duplicate targets prevented
Cycle blocks
```

---

# 26. Text Report Changes

Add a section:

```text
REPARSE-POINT SUMMARY
------------------------------------------------------------
Detected:                   182
Skipped by policy:          176
Duplicate targets blocked:    4
Cycles prevented:             1
Cross-volume targets blocked: 1
Unresolved targets:           0
```

Add detailed entries only when useful:

```text
C:\Users\All Users
    Type:      Junction
    Target:    C:\ProgramData
    Decision:  Skipped
    Reason:    Default reparse-point policy
```

Include a statement:

```text
Skipped reparse-point targets are not included in source-path folder totals.
Their contents are counted only through independently scanned real paths.
```

---

# 27. Migration and Historical Data

Older Phase 3 scans do not contain explicit reparse metadata.

Recommended behavior:

* add nullable metadata fields;
* mark prior scan reparse-detection version as `0`;
* mark new Phase 4 scans as version `1`;
* do not treat Phase 3 and Phase 4 scans as fully comparable when traversal behavior could differ;
* require a new Phase 4 baseline for automatic comparison.

Display:

```text
A new baseline is required because reparse-point handling changed.
```

Do not attempt to infer old junction behavior from stored paths alone.

---

# 28. Baseline Behavior

The first scan using Phase 4 traversal policy should become a new baseline.

Reason:

* directory coverage may change;
* duplicate aliases may disappear from descendant observations;
* hierarchy shape may change;
* totals may decrease because duplicate trees are no longer traversed.

Do not report the difference between a pre-Phase 4 scan and the first Phase 4 scan as ordinary folder reduction.

Mark:

```text
comparison_status = baseline_created
reason = reparse policy version changed
```

---

# 29. Performance Requirements

Reparse inspection adds filesystem calls.

Requirements:

* inspect only directory candidates;
* cache target identity within the scan;
* avoid resolving the same target repeatedly;
* batch persistence of reparse records;
* keep visited identity sets lightweight;
* throttle progress events;
* avoid opening persistent handles for every directory.

Recommended scan-scoped caches:

```python
source_path_cache: dict[str, ReparsePointInfo]
target_identity_cache: dict[str, str]
visited_object_ids: set[str]
visited_target_paths: set[str]
active_ancestry_ids: set[str]
```

Do not retain OS handles after identity inspection is complete.

---

# 30. Failure Handling

Failure to inspect a suspected reparse point must not cause unsafe traversal.

Default:

```text
inspection failed
→ record warning
→ skip traversal
```

Recommended warning operations:

```text
inspect_reparse_point
resolve_reparse_target
query_file_identity
query_volume_identity
apply_traversal_policy
```

Do not downgrade an inspection failure into normal traversal.

---

# 31. Service Boundaries

Recommended structure:

```text
scanner/folder_scanner.py
- traversal orchestration

scanner/reparse_points.py
- Windows reparse detection
- tag classification
- target extraction

scanner/path_identity.py
- canonical path
- volume identity
- physical directory identity

scanner/traversal_policy.py
- follow or skip decisions
- duplicate prevention
- cycle prevention

analysis/hierarchy.py
- treats skipped aliases as terminal nodes

db/
- persists directory and reparse metadata

reporting/
- formats reparse summaries

gui/
- displays metadata and settings
```

Do not place reparse logic inside:

* GUI widgets;
* SQLAlchemy models;
* report templates;
* scan-difference code.

---

# 32. Suggested Domain Models

## Reparse information

```python
class ReparsePointInfo(BaseModel):
    source_path: Path
    is_reparse_point: bool
    reparse_tag: int | None
    reparse_type: str | None
    target_path: Path | None
    source_volume_id: str | None
    target_volume_id: str | None
    filesystem_object_id: str | None
    identity_status: str
```

## Traversal decision

```python
class TraversalDecision(BaseModel):
    action: str
    reason: str
    followed: bool
    confidence: str
```

## Reparse summary

```python
class ReparseScanSummary(BaseModel):
    scan_id: int
    detected: int
    skipped: int
    followed: int
    duplicate_targets: int
    cycles_prevented: int
    cross_volume_blocked: int
    unresolved_targets: int
```

---

# 33. Testing Requirements

Use temporary directories and Windows-specific test helpers.

Skip tests gracefully when Windows features or privileges are unavailable.

## 33.1 Junction detection

Create:

```text
Root\Data
Root\Alias → Root\Data
```

Expected:

* `Alias` detected as reparse point;
* target resolved;
* `Data` scanned once;
* `Alias` descendants not scanned;
* alias record persisted.

## 33.2 Compatibility alias pattern

Simulate or test equivalent behavior to:

```text
C:\Users\All Users → C:\ProgramData
```

Expected:

* no duplicate target traversal;
* source alias visible;
* target counted once.

## 33.3 Symbolic-link detection

Create a directory symbolic link when permissions permit.

Expected:

* detected;
* classified;
* skipped by default.

## 33.4 Unknown reparse tag

Mock an unrecognized tag.

Expected:

* classified as unknown;
* skipped;
* warning or informational event recorded.

## 33.5 Duplicate target through two aliases

Create:

```text
AliasA → Data
AliasB → Data
```

Expected:

* `Data` scanned once;
* both aliases recorded;
* neither causes duplicate descendants;
* duplicate target count reflects policy.

## 33.6 Cycle

Create or mock:

```text
A\ToB → B
B\ToA → A
```

Expected:

* scan terminates;
* cycle recorded;
* no infinite traversal;
* no duplicated descendants.

## 33.7 Cross-volume mount point

Mock or conditionally test a target on another volume.

Expected with default policy:

```text
cross_volume_blocked
```

## 33.8 Unresolved target

Mock target-resolution failure.

Expected:

* traversal skipped;
* status `target_unavailable`;
* warning persisted;
* scan continues.

## 33.9 Path casing

Observe the same path with different casing.

Expected:

* one canonical directory identity;
* display path preserved;
* no duplicate observation.

## 33.10 Trailing separators

Expected:

```text
C:\Data
C:\Data\
```

map to the same path identity.

## 33.11 Long path

Create a deep path where supported.

Expected:

* canonicalization succeeds;
* path not truncated;
* comparison key stable.

## 33.12 Phase 4 baseline

Upgrade from Phase 3 and run first Phase 4 scan.

Expected:

* new baseline created;
* no false reduction report;
* reparse version stored.

## 33.13 Hierarchy behavior

A skipped alias inside a parent should:

* remain a terminal node;
* not include target descendants;
* not make the normal target branch duplicate;
* not inflate inclusive totals.

## 33.14 Forced follow mode

When enabled in tests:

* target traversed once;
* visited identity recorded;
* second alias blocked;
* cycle checks remain active.

## 33.15 Inspection failure

Mock Windows API failure.

Expected:

* scanner skips suspected reparse point;
* warning emitted;
* no unsafe fallback traversal.

---

# 34. Compatibility Requirements

Phase 4 must preserve:

* direct logical snapshots;
* true scan-to-scan deltas;
* direct and inclusive hierarchy measurements;
* non-overlapping direct totals;
* scan lifecycle states;
* cancellation behavior;
* warning persistence;
* GUI responsiveness;
* CLI history;
* text reports;
* prior database records.

The first Phase 4 scan may intentionally establish a new baseline.

No historical scan data should be deleted.

---

# 35. Documentation Requirements

Update `README.md` with:

* definition of Windows reparse points;
* junction and symbolic-link behavior;
* default skip policy;
* duplicate-target prevention;
* cycle prevention;
* cross-volume policy;
* why `C:\Users\All Users` must not duplicate `C:\ProgramData`;
* effect on scan comparability;
* new baseline requirement;
* CLI commands;
* limitations of path-based and physical identity.

Include this example:

```text
C:\ProgramData is scanned normally.

C:\Users\All Users is detected as a junction to C:\ProgramData.

The junction is recorded but not traversed, so the underlying content is counted once.
```

---

# 36. Acceptance Criteria

Phase 4 is complete when all of the following are true:

1. Directory reparse points are explicitly detected.
2. Reparse tags are stored when available.
3. Reparse types are classified.
4. Reparse targets are recorded when resolvable.
5. Reparse points are skipped by default.
6. Unknown reparse points are not treated as normal directories.
7. The scanner does not duplicate `ProgramData` through `Users\All Users`.
8. Duplicate targets are detected.
9. Traversal cycles are prevented.
10. Cross-volume targets are blocked by default.
11. Source paths remain visible in reports.
12. Skipped aliases do not inherit target descendants.
13. Inclusive totals do not include skipped target content.
14. Canonical path comparison is case-insensitive.
15. Trailing separators do not create duplicate identities.
16. Long paths are preserved.
17. Inspection failures result in safe skipping.
18. Reparse metadata is persisted per scan.
19. Traversal policy is included in configuration compatibility.
20. The first Phase 4 scan creates a new baseline.
21. Pre-Phase 4 scans remain readable.
22. GUI exposes reparse summary information.
23. CLI can list and inspect reparse points.
24. Text reports explain skipped aliases.
25. Forced follow mode retains duplicate and cycle protection.
26. All prior tests continue to pass.
27. All Phase 4 tests pass with:

```powershell
uv run pytest
```

28. The application is prepared for Phase 5 volume reconciliation.

---

# 37. Coding-Agent Assignment

Implement Phase 4 only.

Add explicit Windows reparse-point detection using pywin32 or appropriate Windows APIs.

Detect directory junctions, symbolic links, mount points, and unknown reparse-point types before adding directories to the traversal queue.

By default:

```text
record reparse point
resolve target when possible
do not recurse into target
do not include target descendants in source-path inclusive size
```

Persist reparse metadata per scan, including:

* source path;
* reparse tag;
* reparse type;
* target path;
* source and target volume identity where available;
* traversal decision;
* decision reason.

Create a versioned canonical path service. Normalize path casing, separators, redundant components, trailing separators, drive letters, and long-path forms without blindly following reparse targets.

Maintain scan-scoped sets of visited canonical targets and physical directory identities where available.

Prevent:

* duplicate target traversal;
* active ancestry cycles;
* cross-volume traversal by default;
* unsafe traversal when target resolution fails.

Treat skipped reparse points as terminal hierarchy nodes. Do not attach the target directory’s children beneath the source alias.

Add reparse-point configuration to the scan compatibility hash. The first Phase 4 scan must establish a new baseline rather than comparing directly against pre-Phase 4 scans.

Update GUI, CLI, and text reports with reparse-point summaries and details.

Do not implement allocated size, hard-link deduplication, file-level identity tracking, volume reconciliation, retention, scheduling, or NTFS metadata parsing.

The completed Phase 4 application must ensure that aliases such as:

```text
C:\Users\All Users
C:\ProgramData
```

cannot cause the same underlying directory tree to be scanned or counted twice.
