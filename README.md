# Folder Size Difference Scanner

A Windows desktop app that scans a directory tree and reports direct and inclusive logical folder-size changes between comparable completed scans.

Useful for tracking down where logical file sizes changed between scans. The primary report ranks non-overlapping direct folder growth so parent and child folders are not double counted. Inclusive subtree values are available for hierarchy navigation, not grand totals.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Setup

```
uv sync
uv run alembic upgrade head
```

The Alembic command creates or upgrades the SQLite database schema.

## Running

```
uv run folder-diff
```

The legacy command still works:

```
uv run python src/main.py
```

## Usage

Fill in the three settings at the top of the window and click **Run Scan**:

| Setting | Default | Description |
|---|---|---|
| Directory | `C:\` | Root directory to recursively scan |
| Threshold (MB) | `100` | Minimum absolute net logical change to show in reports |
| Days | `1` | Legacy setting retained for compatibility; it no longer drives the primary Phase 2 report |

Use the **Browse** button to navigate the filesystem and pick a folder.

Click **Cancel Scan** at any time to request cooperative cancellation of a running scan.

## Output

The first compatible scan creates a baseline. It does not claim growth:

```
Baseline scan completed.
Run another scan to calculate folder-size changes.
```

After a second compatible scan, the results pane lists folders whose direct logical size changed beyond the configured threshold:

```
C:\Users\brad\AppData\Local\Temp\SomeApp
    Net logical change: +342.5 MB
    Previous direct size: 120.0 MB | Current direct size: 462.5 MB
    State: grown | Confidence: high
```

A status bar at the bottom shows live progress and scan/comparison status.

## Measurement Semantics

The scanner stores two logical measurements:

```
direct_logical_size(folder) = sum(st_size of direct child files)
inclusive_logical_size(folder) = direct_logical_size(folder) + all descendant direct sizes
```

Direct size is the size of files immediately inside a folder. Inclusive size is the size of the folder's whole subtree.

The default report is ranked by direct growth because direct values do not overlap. Inclusive values overlap across ancestors and descendants, so they are shown for navigation and must not be summed into a total.

Example:

```
A 500 MB file added to a nested folder produces:

Nested folder direct growth: 500 MB
Each ancestor direct growth: 0 MB
Each ancestor inclusive growth: 500 MB
Total disk growth reported: 500 MB
```

Hierarchy status meanings:

```
complete       Inclusive totals were calculated successfully.
partial        One or more descendants were incomplete or inaccessible.
orphaned       A parent relationship could not be resolved.
invalid_parent Stored hierarchy metadata is inconsistent.
cycle_detected Corrupt hierarchy metadata created a cycle.
unavailable   The scan predates Phase 3 hierarchy aggregation.
```

If a descendant is inaccessible, direct measurements for accessible folders remain reportable, but ancestor inclusive status becomes partial. Upgraded Phase 2 scans remain readable; their inclusive comparison is unavailable until two Phase 3 hierarchy-compatible scans exist.

Changing a file without changing its size produces zero direct growth.

These values are logical file-size differences between snapshots. They are not physical allocated disk-space differences; sparse files, compression, hard links, inaccessible paths, system metadata, and files changing during a scan can all make disk usage differ from the report.

## Database

Scan history and direct logical observations are stored in SQLite at:

```
data/folder_sizes.db
```

Change the location by adding or editing `DatabasePath` in `config.yaml`:

```
DatabasePath: 'data/folder_sizes.db'
```

The app checks that the database schema is current at startup. If it is missing or outdated, run:

```
uv run alembic upgrade head
```

Cancelled scans keep any observations that were already committed and are marked `cancelled`. Scans left `pending` or `running` from an interrupted app session are marked `interrupted` on the next startup and are not treated as completed history.

Automatic comparisons use the most recent earlier `completed` scan with:

- the same normalized target path;
- the same measurement algorithm version;
- the same measurement configuration hash.

Cancelled, failed, interrupted, and Phase 1 timestamp-only scans are not selected as baselines.

## CLI

Inspect the database with:

```
uv run folder-diff-cli db-info
uv run folder-diff-cli scans
uv run folder-diff-cli scan-show <scan-id>
uv run folder-diff-cli warnings --scan-id <scan-id>
uv run folder-diff-cli report
uv run folder-diff-cli report --tree
uv run folder-diff-cli report --direct-only
uv run folder-diff-cli report --reductions
uv run folder-diff-cli compare <current-scan-id> <previous-scan-id>
uv run folder-diff-cli compare <current-scan-id> <previous-scan-id> --tree
uv run folder-diff-cli folder-show "C:\Users\brad\AppData\Roaming\Notion"
```

## Log Files

Each run writes a timestamped report to the `logs/` directory:

```
logs/scan_2025-07-23_14-30-00.log
```

Use **File → Open Logs Folder** to open the report directory, or **Help → Open Application Log** to open the active application log.

## Settings Persistence

Settings are saved to `config.yaml` in the project root after each run and restored on next launch.

## Legacy PowerShell Version

The original PowerShell script is preserved in `ps/` with its own [README](ps/README.md).
