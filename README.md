# Folder Growth Scanner

A Windows desktop app that scans a directory tree and reports folders whose contents have grown beyond a specified size threshold within a given time range.

Useful for tracking down unexpected disk usage — finding which folders ballooned overnight, or identifying a runaway cache or log directory over the past week.

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) for dependency management

## Setup

```
uv sync
```

## Running

```
uv run src/main.py
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

The results pane lists each flagged folder and how much it grew:

```
⚠  C:\Users\brad\AppData\Local\Temp\SomeApp
    → 342.5 MB in last 1 day(s)
```

A status bar at the bottom shows live progress during the scan.

## Log Files

Each run that finds at least one matching folder writes a timestamped log to the `logs/` directory:

```
logs/scan_2025-07-23_14-30-00.log
```

The **Show Log** button becomes active at the end of a run when a log file was written, and opens it in Notepad.

## Settings Persistence

Settings are saved to `CheckFolderGrowth.yaml` in the project root after each run and restored on next launch.

## Legacy PowerShell Version

The original PowerShell script is preserved in `ps/` with its own [README](ps/README.md).
