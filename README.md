# Folder Size Difference Scanner

A Windows desktop app that scans a directory tree and reports direct logical folder-size changes between comparable completed scans.

Useful for tracking down where logical file sizes changed between scans. Phase 2 compares persisted directory observations; it does not yet measure recursive inclusive size or physical allocated disk usage.

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

Fill in the three settings at the top of the window and click **Start**:

| Setting | Default | Description |
|---|---|---|
| Directory | `C:\` | Root directory to recursively scan |
| Threshold (MB) | `100` | Minimum absolute net logical change to show in reports |
| Days | `1` | Legacy setting retained for compatibility; it no longer drives the primary Phase 2 report |

Use the **Browse** button to navigate the filesystem and pick a folder.

Click **Stop** at any time to cancel a running scan.

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

Phase 2 measures direct logical folder size:

```
direct_logical_size(folder) = sum(st_size of direct child files)
```

Files in child folders are measured on the child folder, not rolled into the parent. Recursive inclusive sizing is deferred to Phase 3.

Example:

```
Scan 1:
C:\Data = 1.0 GB

Scan 2:
C:\Data = 1.4 GB

Reported direct logical change:
+0.4 GB
```

Changing a file without changing its size produces zero folder growth.

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
uv run folder-diff-cli report --reductions
uv run folder-diff-cli compare <current-scan-id> <previous-scan-id>
```

## Log Files

Each run writes a timestamped report to the `logs/` directory:

```
logs/scan_2025-07-23_14-30-00.log
```

The **Show Log** button becomes active at the end of a run when a log file was written, and opens it in Notepad.

## Settings Persistence

Settings are saved to `config.yaml` in the project root after each run and restored on next launch.

## Legacy PowerShell Version

The original PowerShell script is preserved in `ps/` with its own [README](ps/README.md).
