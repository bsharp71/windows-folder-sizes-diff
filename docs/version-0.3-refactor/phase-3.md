# Phase 3 Technical Specification

Implement Phase 3 using the attached specification as the governing document.

Before changing code:

1. Inspect the current repository and confirm the prerequisite phases are present.
2. Identify any conflicts or assumptions that differ from the specification.
3. Create a concise implementation checklist mapped to the acceptance criteria.
4. Implement only Phase 3. Do not begin later-phase features.
5. Run the complete test suite and report any failures.
6. At completion, provide:

   * files added or changed;
   * architectural decisions made;
   * migrations or commands I must run;
   * test results;
   * acceptance criteria not fully satisfied;
   * any technical debt deferred to the next phase.

Preserve existing working behavior unless the specification explicitly changes it.

## Hierarchical Folder Sizing and Double-Count Prevention

**Project:** `windows-folder-sizes-diff`
**Phase:** 3 — Hierarchical Accuracy
**Language:** Python 3.12+
**Database:** SQLite
**Database layer:** SQLAlchemy 2.x
**Migrations:** Alembic
**Prerequisites:** Phase 0, Phase 1, and Phase 2 completed

---

# 1. Objective

Add hierarchical directory measurements so the application can distinguish between:

* disk activity directly inside a folder; and
* disk activity anywhere inside that folder’s entire subtree.

Phase 3 must eliminate the parent-and-child double counting seen in the original report.

Example of the current problem:

```text
C:\Windows\Temp\Whesvc                  610.5 MB
C:\Windows\Temp\Whesvc\perf\trace-a     204.0 MB
C:\Windows\Temp\Whesvc\perf\trace-b     198.5 MB
C:\Windows\Temp\Whesvc\power\trace-c    208.0 MB
```

The three child folders total 610.5 MB. Reporting the parent and children as independent contributions produces 1.22 GB of apparent growth even though only 610.5 MB exists.

At the end of Phase 3, the application must:

* store direct and inclusive folder measurements separately;
* calculate direct and inclusive deltas between scans;
* rank the primary report using non-overlapping direct growth;
* support an inclusive tree view for understanding broader folder impact;
* prevent totals from summing parent and descendant inclusive values together;
* preserve all Phase 2 snapshot-diff behavior.

---

# 2. Prerequisite Behavior

Phase 2 is expected to provide:

* durable completed scans;
* comparable baseline selection;
* actual folder-size measurements for each scan;
* current and previous logical-size values;
* net directory differences;
* directory result states such as:

  * grown;
  * reduced;
  * new;
  * removed;
  * unchanged;
  * incomplete;
* configuration compatibility checks;
* GUI and CLI comparison reports.

Phase 3 must extend these capabilities rather than replacing them.

---

# 3. Phase 3 Scope

Implement:

* persistent parent-child directory relationships;
* directory depth;
* direct folder measurements;
* inclusive folder measurements;
* bottom-up hierarchy aggregation;
* direct and inclusive deltas;
* hierarchy-aware comparison results;
* non-overlapping report totals;
* inclusive tree navigation;
* detection of hierarchy inconsistencies;
* updated GUI, CLI, and text reports;
* tests for hierarchy calculations and double-count prevention.

Do not implement:

* Windows reparse-point resolution;
* physical directory identity using NTFS file IDs;
* allocated-size measurement;
* hard-link handling;
* file-level forensics;
* volume reconciliation;
* retention and rollups;
* scheduled execution.

Reparse-point and alias protection remain Phase 4 work unless basic skipping already exists.

---

# 4. Terminology

Use these terms consistently throughout code, database fields, reports, and documentation.

## 4.1 Direct size

The total size of files located immediately inside a directory.

Direct size does not include files in child directories.

Also called:

```text
exclusive size
```

Preferred application term:

```text
direct size
```

## 4.2 Inclusive size

The total size of:

* direct files in the directory; plus
* all files in every descendant directory.

Also called:

```text
recursive size
subtree size
```

Preferred application term:

```text
inclusive size
```

## 4.3 Direct growth

The difference between current and previous direct size:

```text
direct_growth =
    current_direct_size - previous_direct_size
```

## 4.4 Inclusive growth

The difference between current and previous inclusive size:

```text
inclusive_growth =
    current_inclusive_size - previous_inclusive_size
```

## 4.5 Non-overlapping total

A total calculated from direct measurements only.

Because each file belongs directly to one directory, direct measurements may be summed across the hierarchy without counting the same bytes through every ancestor.

---

# 5. Core Measurement Rules

For a directory `D`:

```text
direct_size(D) =
    sum(size of files immediately inside D)
```

```text
inclusive_size(D) =
    direct_size(D)
    + sum(inclusive_size(each direct child directory))
```

For example:

```text
C:\Example
├── root.bin             100 MB
├── ChildA
│   └── a.bin            250 MB
└── ChildB
    └── b.bin            150 MB
```

Expected measurements:

| Directory           | Direct size | Inclusive size |
| ------------------- | ----------: | -------------: |
| `C:\Example`        |      100 MB |         500 MB |
| `C:\Example\ChildA` |      250 MB |         250 MB |
| `C:\Example\ChildB` |      150 MB |         150 MB |

The inclusive values must not be summed together for a volume or scan total.

Incorrect:

```text
500 + 250 + 150 = 900 MB
```

Correct non-overlapping total:

```text
100 + 250 + 150 = 500 MB
```

---

# 6. Database Changes

Create a new Alembic migration for Phase 3.

Do not modify an already-applied Phase 1 or Phase 2 migration.

## 6.1 `directories` table changes

Add:

```text
parent_directory_id    INTEGER NULL
depth                  INTEGER NOT NULL DEFAULT 0
```

Recommended foreign key:

```text
parent_directory_id → directories.id
```

Add an index:

```text
directories(parent_directory_id)
```

Add an index where useful:

```text
directories(depth)
```

The root target directory must have:

```text
parent_directory_id = NULL
depth = 0
```

A direct child of the root has:

```text
depth = 1
```

## 6.2 Snapshot or observation table changes

Phase 2 should already have a per-directory per-scan measurement table. Extend that table with explicit direct and inclusive fields.

Recommended fields:

```text
direct_logical_bytes       INTEGER NULL
inclusive_logical_bytes    INTEGER NULL

direct_file_count          INTEGER NOT NULL DEFAULT 0
inclusive_file_count       INTEGER NULL

direct_child_count         INTEGER NOT NULL DEFAULT 0
descendant_directory_count INTEGER NULL

hierarchy_status           TEXT NOT NULL DEFAULT 'pending'
```

If Phase 2 already stores a generic field such as:

```text
logical_bytes
current_size_bytes
folder_size_bytes
```

Migrate or rename it deliberately.

The previous Phase 2 value should become:

```text
direct_logical_bytes
```

if it measured files immediately inside the folder.

Do not keep ambiguous field names.

## 6.3 Hierarchy status values

Use values such as:

```text
pending
complete
partial
orphaned
invalid_parent
cycle_detected
```

Definitions:

* `pending`: Direct measurement exists, but inclusive aggregation has not completed.
* `complete`: Inclusive totals were calculated successfully.
* `partial`: One or more descendant measurements were incomplete.
* `orphaned`: Parent directory was expected but could not be resolved.
* `invalid_parent`: Stored parent relationship conflicts with the current path hierarchy.
* `cycle_detected`: A hierarchy cycle was found.

Cycles should not occur in a normal path-based tree, but the application must fail safely if corrupt data creates one.

---

# 7. Directory Parent Identity

Every scanned directory must be associated with its immediate parent within the scan target.

Example:

```text
Directory:
C:\Users\brad\AppData\Local\Notion\Cache

Parent:
C:\Users\brad\AppData\Local\Notion
```

## 7.1 Root behavior

The configured scan target is the hierarchy root.

Its database row must have:

```text
parent_directory_id = NULL
depth = 0
```

Do not attach the scan target to a parent outside the target tree.

For example, when scanning:

```text
C:\Users\brad
```

do not assign:

```text
C:\Users
```

as the root’s parent.

## 7.2 Parent assignment

When discovering a child directory:

1. Normalize the child path.
2. Resolve or create its directory identity.
3. Assign the currently scanned directory as its parent.
4. Set:

```text
child.depth = parent.depth + 1
```

Prefer parent identity derived from traversal context rather than repeatedly parsing path strings.

## 7.3 Existing directory rows

A directory may already exist from an earlier scan.

When observed again:

* verify the expected parent;
* update `parent_directory_id` if the prior value is missing;
* do not silently overwrite a conflicting parent without recording a warning;
* verify depth consistency.

Path-based identity means that moving a directory currently creates a different directory identity. Move detection is outside Phase 3.

---

# 8. Scanner Data Requirements

The scanner must emit or persist direct measurements for every successfully analyzed directory.

Each directory observation must include at least:

```python
class FolderObservation(BaseModel):
    scan_id: int
    directory_path: Path
    parent_path: Path | None
    depth: int

    direct_logical_bytes: int
    direct_file_count: int
    direct_child_count: int

    observed_at: datetime
    status: str
    warning_count: int = 0
```

Do not calculate inclusive measurements during direct file enumeration unless the scanner already uses a safe recursive traversal that naturally returns child totals.

The recommended implementation is:

1. scan and persist direct measurements;
2. construct or query the hierarchy;
3. aggregate inclusive measurements bottom-up.

This keeps traversal and hierarchy analysis separate.

---

# 9. Bottom-Up Aggregation

Create a dedicated hierarchy aggregation service.

Recommended interface:

```python
class HierarchyAggregator:
    def aggregate_scan(self, scan_id: int) -> HierarchyAggregationResult:
        ...
```

The service must calculate inclusive values from deepest directories toward the root.

## 9.1 Algorithm

For the current scan:

1. Load directory measurements and hierarchy information.
2. Order directories by `depth DESC`.
3. Initialize each directory:

```text
inclusive_logical_bytes = direct_logical_bytes
inclusive_file_count = direct_file_count
descendant_directory_count = 0
```

4. For each directory from deepest to shallowest:

   * finalize its current inclusive values;
   * add those values to its parent;
   * add one plus its descendant count to its parent.

Conceptually:

```python
for node in directories_sorted_by_depth_desc:
    inclusive[node] += direct[node]

    if node.parent_id is not None:
        inclusive[node.parent_id] += inclusive[node]
        inclusive_files[node.parent_id] += inclusive_files[node]
        descendants[node.parent_id] += 1 + descendants[node]
```

The exact implementation may aggregate in Python or SQL.

For Phase 3, a Python aggregation pass is acceptable if memory usage is controlled.

## 9.2 Memory requirements

The application may scan hundreds of thousands of directories.

Do not construct deeply nested Python objects for every directory.

Use compact structures such as:

```python
dict[int, int]
dict[int, DirectoryAggregate]
```

Avoid storing full ORM objects for all directories when lightweight rows or tuples will work.

## 9.3 Database updates

Persist inclusive results in batches.

Do not issue one commit per directory.

Recommended batch size:

```text
500–5000 rows
```

Use SQLAlchemy bulk updates or temporary staging techniques where practical.

---

# 10. Partial and Incomplete Hierarchies

Inclusive results are only as reliable as their descendants.

If a child directory is:

* inaccessible;
* disappeared;
* partially scanned;
* missing an observation;
* recorded with an error status;

then its ancestors’ inclusive measurements may be understated.

## 10.1 Propagation rule

An incomplete child must reduce the confidence of every ancestor up to the scan root.

Example:

```text
C:\Root
└── Child
    └── Restricted
```

If `Restricted` is inaccessible:

* `Restricted` is incomplete.
* `Child` inclusive result is partial.
* `Root` inclusive result is partial.

Direct measurements for `Root` and `Child` may still be complete.

## 10.2 Required fields

Each directory result should distinguish:

```text
direct_measurement_status
inclusive_measurement_status
```

A folder can have:

```text
direct = complete
inclusive = partial
```

This distinction is important and must be visible in detailed reports.

---

# 11. Hierarchy Validation

Before or during aggregation, validate the directory tree.

Check:

* root has no parent;
* every non-root node has a known parent within the scan;
* child depth equals parent depth plus one;
* no directory references itself as parent;
* no cycle exists;
* every directory has at most one parent;
* every observation belongs to the current scan;
* parent and child are on the same scan target hierarchy.

Record hierarchy warnings rather than silently fabricating totals.

## 11.1 Orphan behavior

If a directory observation has no resolvable parent:

* retain its direct measurement;
* mark hierarchy status `orphaned`;
* do not attach it to the root automatically unless path evidence supports doing so;
* include it in direct-growth totals;
* exclude it from ancestor inclusive aggregation;
* record a warning.

## 11.2 Cycle behavior

If a cycle is detected:

* mark involved nodes `cycle_detected`;
* do not continue aggregation through the cycle;
* record an error;
* mark the scan’s hierarchy aggregation incomplete;
* prevent inclusive totals from being presented as reliable.

---

# 12. Comparison Model Changes

Extend the Phase 2 directory comparison model.

Recommended model:

```python
class DirectoryDiff(BaseModel):
    directory_id: int
    path: Path
    parent_directory_id: int | None
    depth: int

    previous_direct_bytes: int | None
    current_direct_bytes: int | None
    direct_delta_bytes: int

    previous_inclusive_bytes: int | None
    current_inclusive_bytes: int | None
    inclusive_delta_bytes: int | None

    state: str
    direct_confidence: str
    inclusive_confidence: str
    warning_count: int
```

## 12.1 Direct delta

```text
direct_delta =
    current_direct_bytes - previous_direct_bytes
```

## 12.2 Inclusive delta

```text
inclusive_delta =
    current_inclusive_bytes - previous_inclusive_bytes
```

Only calculate inclusive delta when both snapshots have usable inclusive measurements.

Otherwise:

```text
inclusive_delta = NULL
inclusive_confidence = unavailable
```

Do not substitute zero for an unavailable value.

---

# 13. New and Removed Directory Behavior

## 13.1 New directory

A directory present only in the current scan:

```text
previous_direct_bytes = 0
current_direct_bytes = current value
direct_delta = current value
```

If inclusive current data is complete:

```text
previous_inclusive_bytes = 0
current_inclusive_bytes = current value
inclusive_delta = current value
```

State:

```text
new
```

## 13.2 Removed directory

A directory present only in the previous scan:

```text
previous_direct_bytes = previous value
current_direct_bytes = 0
direct_delta = -previous value
```

If previous inclusive data is complete:

```text
inclusive_delta = -previous inclusive value
```

State:

```text
removed
```

Removed directories must retain their previous hierarchy information for reporting.

Do not delete historical directory rows when a directory disappears.

---

# 14. Primary Ranking Strategy

The main ranked growth report must use:

```text
direct_delta_bytes descending
```

This answers:

> In which folders did the bytes directly appear?

Because direct measurements do not overlap, they can be summed safely.

Do not rank the default report by inclusive growth alone.

Inclusive growth often causes every ancestor to appear as though it independently consumed the same bytes.

Example:

```text
C:\Users                              +2 GB inclusive
C:\Users\brad                         +2 GB inclusive
C:\Users\brad\AppData                 +2 GB inclusive
C:\Users\brad\AppData\Roaming         +2 GB inclusive
C:\Users\brad\AppData\Roaming\Notion  +2 GB direct
```

The default ranked report should identify Notion as the direct contributor.

The hierarchy view may show how that growth propagates upward.

---

# 15. Threshold Behavior

The configured growth threshold must apply to:

```text
absolute direct delta
```

for the primary report.

Recommended default filter:

```text
direct_delta_bytes >= threshold
```

Optional filters may include:

```text
inclusive_delta_bytes >= threshold
direct_delta_bytes <= -threshold
```

Do not suppress a child because its parent also exceeds the inclusive threshold.

Do not use inclusive values to calculate the primary report total.

---

# 16. Report Totals

The report must contain explicit totals.

## 16.1 Direct growth total

```text
sum of positive direct deltas
```

## 16.2 Direct reduction total

```text
absolute sum of negative direct deltas
```

## 16.3 Net direct change

```text
sum of all direct deltas
```

These values are non-overlapping and may be summed safely.

## 16.4 Inclusive values

Inclusive values are descriptive hierarchy metrics.

Do not provide a grand total created by summing inclusive values.

Include a warning or help text:

```text
Inclusive values overlap across parent and child folders and are not summed.
```

---

# 17. Hierarchical Report Modes

Support two distinct report modes.

## 17.1 Direct growth view

Purpose:

> Identify the folders where bytes were directly added or removed.

Columns:

```text
Folder
Direct Growth
Previous Direct Size
Current Direct Size
State
Confidence
Warnings
```

Default sorting:

```text
Direct Growth descending
```

This is the primary view.

## 17.2 Inclusive tree view

Purpose:

> Show how direct changes affect larger folder trees.

Columns:

```text
Folder
Direct Growth
Inclusive Growth
Current Inclusive Size
Hierarchy Status
Confidence
```

Behavior:

* display folders as a tree;
* allow expansion and collapse;
* indent by hierarchy depth;
* do not sum visible inclusive rows;
* optionally show only branches containing significant change.

---

# 18. GUI Requirements

Update the GUI result area to support direct and inclusive measurements.

## 18.1 Default result table

Recommended columns:

```text
Folder
Direct Growth
Current Direct Size
Previous Direct Size
State
Confidence
```

The default view should remain concise.

## 18.2 Hierarchy toggle

Add a control such as:

```text
View:
- Direct growth
- Folder tree
```

The folder tree may be implemented with:

* an existing tree widget;
* a custom hierarchical list;
* an indented result table.

Do not block Phase 3 on a complex visual tree if the current UI framework makes that difficult.

An indented expandable list is sufficient.

## 18.3 Folder detail panel

When a folder is selected, display:

```text
Direct previous size
Direct current size
Direct net change

Inclusive previous size
Inclusive current size
Inclusive net change

Direct file count
Inclusive file count
Direct child count
Descendant directory count

Direct measurement status
Inclusive hierarchy status
Warnings
```

## 18.4 Summary panel

Add:

```text
Total direct growth
Total direct reduction
Net direct change
Directories with direct growth
Directories with inclusive growth
Partial hierarchy count
Hierarchy warning count
```

Do not display a summed inclusive total.

---

# 19. CLI Requirements

Extend the Typer CLI.

## 19.1 Default comparison report

Example:

```powershell
uv run folder-diff-cli report
```

Default output:

* ranked by direct growth;
* threshold applied to direct delta;
* non-overlapping totals;
* confidence and warnings included.

Recommended columns:

```text
Path
Direct Δ
Current Direct
Inclusive Δ
State
Confidence
```

## 19.2 Tree option

Add:

```powershell
uv run folder-diff-cli report --tree
```

Optional arguments:

```text
--root PATH
--max-depth INTEGER
--changed-only
--include-reductions
--threshold-mb INTEGER
```

## 19.3 Direct-only option

Add or retain:

```powershell
uv run folder-diff-cli report --direct-only
```

## 19.4 Folder detail command

Add:

```powershell
uv run folder-diff-cli folder-show "C:\Users\brad\AppData\Roaming\Notion"
```

Display direct and inclusive history for the current comparison pair.

Do not require exact path casing.

---

# 20. Text Report Changes

Update text logs and reports to use explicit terminology.

Recommended section:

```text
DIRECT FOLDER GROWTH
------------------------------------------------------------
These values do not overlap and may be summed.

C:\Users\brad\AppData\Roaming\Notion
    Direct growth:       1.49 GB
    Inclusive growth:    1.74 GB
    Current direct size: 2.10 GB
    Current tree size:   4.50 GB
```

Add a separate hierarchy summary:

```text
LARGEST AFFECTED FOLDER TREES
------------------------------------------------------------
Inclusive values overlap across parent and child directories.
They are shown for navigation and must not be summed.
```

The report summary must include:

```text
Total positive direct growth
Total direct reduction
Net direct change
```

Do not label inclusive growth totals as explained disk growth.

---

# 21. Confidence Rules

Maintain separate confidence for direct and inclusive measurements.

## 21.1 Direct high confidence

* directory was scanned successfully;
* direct file enumeration completed;
* same measurement mode used in both scans;
* no direct-folder warnings affected size.

## 21.2 Inclusive high confidence

* direct confidence is high;
* all descendant observations are complete;
* hierarchy is valid;
* no missing child measurements exist;
* both comparison scans have complete inclusive totals.

## 21.3 Inclusive medium confidence

* minor descendant warnings exist;
* hierarchy is complete but some measurements are estimated;
* one scan completed with non-critical warnings.

## 21.4 Inclusive low or unavailable

* inaccessible descendants;
* orphaned nodes;
* missing observations;
* hierarchy cycle;
* incompatible hierarchy metadata;
* one scan lacks inclusive measurements.

Do not allow a high direct-confidence result to imply high inclusive confidence automatically.

---

# 22. Migration and Backfill

The Phase 3 migration introduces new hierarchy fields.

Existing Phase 2 scans may not contain enough hierarchy metadata to calculate inclusive values.

Choose one of these strategies.

## Recommended strategy: no automatic historical backfill

* Add the new columns.
* Mark prior scan hierarchy status as `unavailable`.
* Begin storing hierarchy-complete scans after the Phase 3 upgrade.
* Require two Phase 3-compatible scans before inclusive deltas are available.

Display:

```text
Inclusive comparison unavailable because the baseline predates hierarchical measurements.
```

This is the safest approach.

## Optional strategy: backfill when possible

Only attempt a backfill if Phase 2 already stored:

* every directory;
* normalized paths;
* direct measurements;
* complete scans.

A backfill command may calculate parent relationships from paths.

Do not make automatic backfill a requirement for application startup.

---

# 23. Hierarchy Algorithm Version

Add a hierarchy algorithm version to scan configuration metadata.

Example:

```text
hierarchy_algorithm_version = 1
```

Include it in the scan configuration hash or comparability metadata.

Do not compare inclusive measurements produced by materially different hierarchy algorithms without an explicit compatibility rule.

Direct measurements may remain comparable when their measurement algorithm has not changed.

---

# 24. Performance Requirements

The hierarchy aggregation must be suitable for hundreds of thousands of directories.

Requirements:

* avoid recursive Python function calls through the entire tree;
* use iterative depth-based aggregation;
* query only required columns;
* avoid loading file-level data;
* batch database updates;
* avoid one ORM object graph containing every parent and child relationship;
* report aggregation progress;
* honor cancellation before report generation where practical.

Suggested aggregation phases:

```text
Loading hierarchy
Validating parent relationships
Aggregating inclusive sizes
Persisting hierarchy results
Generating comparison
```

Progress events should be throttled.

---

# 25. Failure Handling

If direct scanning completes but hierarchy aggregation fails:

* retain the completed direct measurements;
* mark hierarchy aggregation failed or partial;
* allow direct comparisons;
* disable or downgrade inclusive results;
* record the aggregation failure;
* do not mark the entire scan failed unless direct measurement persistence is unusable.

Recommended scan metadata additions:

```text
direct_measurement_status
hierarchy_aggregation_status
```

Possible hierarchy statuses:

```text
not_started
running
completed
completed_with_warnings
failed
unavailable
```

A scan may therefore be:

```text
scan status: completed
hierarchy status: failed
```

The application should remain capable of producing a direct-growth report.

---

# 26. Service Boundaries

Add an analysis service dedicated to hierarchy.

Recommended structure:

```text
scanner/
- gathers direct measurements

db/
- stores directory identity and measurements

analysis/hierarchy.py
- validates relationships
- calculates inclusive measurements
- propagates partial status

analysis/differ.py
- compares direct and inclusive values

reporting/
- formats results

gui/
- presents direct and tree views
```

The scanner must not:

* calculate scan-to-scan deltas;
* format tree reports;
* query historical baselines;
* know GUI hierarchy behavior.

---

# 27. Suggested Models

## Hierarchy node

```python
class DirectoryHierarchyNode(BaseModel):
    directory_id: int
    parent_directory_id: int | None
    depth: int

    direct_logical_bytes: int
    direct_file_count: int
    direct_child_count: int

    direct_status: str
    warning_count: int
```

## Aggregated result

```python
class DirectoryAggregate(BaseModel):
    directory_id: int

    inclusive_logical_bytes: int | None
    inclusive_file_count: int | None
    descendant_directory_count: int | None

    hierarchy_status: str
    hierarchy_warning_count: int = 0
```

## Aggregation summary

```python
class HierarchyAggregationSummary(BaseModel):
    scan_id: int
    directories_processed: int
    complete_directories: int
    partial_directories: int
    orphaned_directories: int
    cycle_count: int
    started_at: datetime
    completed_at: datetime
```

---

# 28. Testing Requirements

Use temporary directory trees and temporary SQLite databases.

## 28.1 Direct and inclusive size tests

Create:

```text
Root
├── root.bin       100 bytes
├── ChildA
│   └── a.bin      250 bytes
└── ChildB
    └── b.bin      150 bytes
```

Expected:

| Directory | Direct | Inclusive |
| --------- | -----: | --------: |
| Root      |    100 |       500 |
| ChildA    |    250 |       250 |
| ChildB    |    150 |       150 |

## 28.2 Nested hierarchy test

Create at least five directory levels.

Verify:

* correct parent identity;
* correct depth;
* correct root inclusive size;
* no recursion-limit dependence.

## 28.3 Parent/child double-count test

Add 200 bytes only in a deep child.

Expected comparison:

```text
Deep child direct delta:       +200
All ancestors direct delta:       0
All ancestors inclusive delta: +200
Net direct change:             +200
```

The final total must be 200, not 200 multiplied by the number of ancestors.

## 28.4 Root direct file test

Add a file directly to the scan root.

Expected:

```text
Root direct delta: +file size
Root inclusive delta: +file size
```

## 28.5 Multiple branches test

Add files in two separate child branches.

Verify:

* each direct folder receives its own delta;
* common ancestors receive the sum as inclusive delta;
* total direct delta equals total bytes added.

## 28.6 File deletion test

Delete a file in a nested directory.

Expected:

* negative direct delta in that directory;
* matching negative inclusive delta in ancestors;
* net direct reduction equals the deleted size.

## 28.7 Directory removal test

Remove a directory tree.

Verify:

* removed directory retains previous direct and inclusive values;
* direct delta is negative;
* ancestor inclusive delta reflects removal;
* no historical rows are deleted.

## 28.8 New directory tree test

Create a new tree with files at multiple levels.

Verify:

* every new directory is classified correctly;
* direct deltas remain non-overlapping;
* inclusive values represent each subtree.

## 28.9 Inaccessible descendant test

Mock an inaccessible child.

Verify:

* direct measurements for accessible ancestors remain valid;
* inclusive status propagates as partial;
* inclusive delta is downgraded or unavailable;
* warning is persisted.

## 28.10 Orphan test

Insert or simulate an observation whose parent is missing.

Verify:

* direct data remains reportable;
* hierarchy status is orphaned;
* node is excluded from incorrect parent aggregation;
* warning is generated.

## 28.11 Cycle test

Create corrupt test data with a parent cycle.

Verify:

* aggregation terminates;
* cycle is detected;
* inclusive values are not trusted;
* error is recorded.

## 28.12 Migration test

Verify:

* Phase 2 database upgrades to Phase 3;
* new columns and indexes exist;
* old scans remain readable;
* old scans report inclusive data as unavailable;
* new scans store full hierarchy data.

## 28.13 Report total test

Verify:

```text
sum of direct deltas = actual net bytes added
```

and:

```text
inclusive rows are never used for the grand total
```

---

# 29. Compatibility Requirements

Phase 3 must preserve:

* Phase 2 direct snapshot comparisons;
* existing scan history;
* scan IDs;
* configuration compatibility checks;
* cancellation behavior;
* persisted warnings;
* GUI responsiveness;
* CLI scan history;
* text logs;
* baseline selection rules.

If inclusive aggregation is unavailable or fails, direct comparison must still work.

No existing valid Phase 2 scan should become unreadable after migration.

---

# 30. Documentation Requirements

Update `README.md` with:

* definition of direct size;
* definition of inclusive size;
* explanation of why inclusive values overlap;
* explanation of primary direct-growth ranking;
* hierarchy status meanings;
* behavior for partial or inaccessible branches;
* migration limitations for older scans;
* CLI examples for direct and tree views.

Include a concise example:

```text
A 500 MB file added to a nested folder produces:

Nested folder direct growth: 500 MB
Each ancestor direct growth: 0 MB
Each ancestor inclusive growth: 500 MB
Total disk growth reported: 500 MB
```

---

# 31. Acceptance Criteria

Phase 3 is complete when all of the following are true:

1. Every newly scanned directory has a parent relationship within the scan hierarchy.
2. The scan target is stored as the hierarchy root.
3. Every directory has a valid depth.
4. Direct logical size is stored separately from inclusive logical size.
5. Inclusive sizes are calculated bottom-up.
6. Direct and inclusive file counts are stored separately.
7. Direct and inclusive deltas are calculated independently.
8. The default growth report ranks by direct delta.
9. Primary totals use direct deltas only.
10. Inclusive parent and child values are never summed into a grand total.
11. A change in one nested child produces one direct contribution.
12. Ancestors reflect the change only through inclusive values.
13. Inaccessible descendants propagate partial hierarchy status upward.
14. Orphans and cycles are detected and reported.
15. Direct reports remain available when hierarchy aggregation fails.
16. Old Phase 2 scans remain readable.
17. Inclusive comparison is clearly unavailable for incompatible old scans.
18. GUI supports direct and hierarchy-oriented views.
19. CLI supports direct and tree reports.
20. Text reports explain that inclusive values overlap.
21. Aggregation uses batch persistence.
22. Aggregation does not rely on recursive Python calls for the full tree.
23. All prior tests continue to pass.
24. All Phase 3 tests pass with:

```powershell
uv run pytest
```

25. The application is prepared for Phase 4 reparse-point and canonical physical identity protection.

---

# 32. Coding-Agent Assignment

Implement Phase 3 only.

Add persistent parent-child directory relationships and directory depth. Store direct folder measurements separately from inclusive subtree measurements.

Treat the current per-folder size measurement from Phase 2 as direct size when it represents files immediately inside that directory.

After a successful scan, run a separate bottom-up hierarchy aggregation process. Initialize each directory’s inclusive measurement from its direct measurement, then aggregate child inclusive values into parents from greatest depth to the root.

Do not use recursive Python traversal for aggregation. Use an iterative depth-ordered algorithm and persist results in batches.

Extend scan comparisons to calculate:

* previous and current direct size;
* direct delta;
* previous and current inclusive size;
* inclusive delta.

The default ranked report and all grand totals must use direct deltas because direct values do not overlap. Inclusive values are for hierarchy navigation and must never be summed across parent and child folders.

Add hierarchy validation for missing parents, invalid depth, orphaned directories, self-parent references, and cycles. Preserve direct results even when inclusive aggregation is partial or fails.

Propagate incomplete descendant status upward so ancestors cannot be presented as having complete inclusive measurements when a child branch was inaccessible.

Update GUI, CLI, and text reports to distinguish direct and inclusive size and growth clearly. Add a direct-growth default view and an optional hierarchical tree view.

Do not implement reparse-point resolution, allocated-size measurement, hard-link handling, file-level tracking, volume reconciliation, retention, or scheduling.

The completed Phase 3 application must eliminate parent-and-child double counting while showing both the folder where bytes directly appeared and the larger folder trees affected by that change.
