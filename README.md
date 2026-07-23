# Folder Growth Scanner

A Windows desktop app that scans a directory tree and reports folders whose direct child files have recent timestamp activity above a configured size threshold.

Useful for tracking down likely sources of recent disk usage, such as active caches or log directories. Phase 1 stores durable scan history, but it does not yet calculate true snapshot-based growth.

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
| Threshold (MB) | `100` | Minimum size increase to flag a folder |
| Days | `1` | How far back to look for new or modified files |

Use the **Browse** button to navigate the filesystem and pick a folder.

Click **Stop** at any time to cancel a running scan.

## Output

The results pane lists each flagged folder and the current logical size of direct child files whose modification or creation timestamp is inside the selected history window:

```
⚠  C:\Users\brad\AppData\Local\Temp\SomeApp
    → 342.5 MB in last 1 day(s)
```

A status bar at the bottom shows live progress during the scan.

## Database

Phase 1 stores scan history in SQLite at:

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

## CLI

Inspect the database with:

```
uv run folder-diff-cli db-info
uv run folder-diff-cli scans
uv run folder-diff-cli scan-show <scan-id>
uv run folder-diff-cli warnings --scan-id <scan-id>
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
