# CheckFolderGrowth

A PowerShell script that scans a Windows directory tree and reports any folders whose contents have grown beyond a specified size threshold within a given time range.

## Use Case

Useful for identifying what's consuming unexpected disk space — for example, finding which folders ballooned overnight, or tracking down a runaway log directory over the past week.

## Requirements

- Windows PowerShell 5.1 or PowerShell 7+
- Read access to the directory being scanned

## Running the Script

```powershell
.\CheckFolderGrowth.ps1
```

If you get an execution policy error, run this first in the same session:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

## Prompts

On each run the script prompts for three settings. Press Enter to accept the value shown in brackets (the last used value, or the default on first run).

| Prompt | Default | Description |
|---|---|---|
| Parent directory to scan | `C:\` | Root directory to recursively scan |
| Growth threshold in MB | `100` | Minimum size increase to flag a folder |
| History range in days | `1` | How far back to look for new or modified files |

## Settings File

Settings are saved to `CheckFolderGrowth.yaml` in the same folder as the script after each run. This file is created automatically on first run with the defaults above. You can edit it directly between runs if preferred.

```yaml
TargetDirectory: 'C:\'
GrowthThresholdMB: 100
HistoryDays: 1
```

## Output

The script runs in two phases, both indicated on a single updating status line:

- **Phase 1 — Building folder list:** Recursively enumerates all subdirectories under the target path. A spinner and live folder count are shown while this runs.
- **Phase 2 — Analyzing folders:** Checks each folder for files created or modified within the history range. Progress is shown as `Analyzing X of Y`.

Flagged folders print below the status line as they are found:

```
⚠️  C:\Users\brad\AppData\Local\Temp\SomeApp
    -> Grew by 342.5 MB in the last 1 day(s).
```

When complete, the status line is replaced with a summary.

## Stopping the Script

Press `Ctrl+C` at any time. The script will exit cleanly and clear the status line.
