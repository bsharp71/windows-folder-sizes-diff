# Identify folders where contents have grown more than the threshold in the given time range.

# Run this if script needs permission
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# --- SIDECAR SETTINGS ---
$SidecarPath = Join-Path $PSScriptRoot "config.yaml"
$defaults = @{ TargetDirectory = 'C:\'; GrowthThresholdMB = 100; HistoryDays = 1 }

if (-not (Test-Path $SidecarPath)) {
    Set-Content $SidecarPath "TargetDirectory: '$($defaults.TargetDirectory)'`nGrowthThresholdMB: $($defaults.GrowthThresholdMB)`nHistoryDays: $($defaults.HistoryDays)"
}

# Parse the 3 known keys from YAML (no module required)
$yaml = @{}
Get-Content $SidecarPath | ForEach-Object {
    if ($_ -match "^(\w+):\s*'?([^']*)'?\s*$") { $yaml[$Matches[1]] = $Matches[2] }
}
$prev = @{
    TargetDirectory   = if ($yaml.TargetDirectory)   { $yaml.TargetDirectory }   else { $defaults.TargetDirectory }
    GrowthThresholdMB = if ($yaml.GrowthThresholdMB) { [int]$yaml.GrowthThresholdMB } else { $defaults.GrowthThresholdMB }
    HistoryDays       = if ($yaml.HistoryDays)       { [int]$yaml.HistoryDays }       else { $defaults.HistoryDays }
}

# --- PROMPTS ---
$inputDir   = Read-Host "Parent directory to scan [$($prev.TargetDirectory)]"
$TargetDirectory   = if ($inputDir.Trim())   { $inputDir.Trim() }   else { $prev.TargetDirectory }

$inputMB    = Read-Host "Growth threshold in MB [$($prev.GrowthThresholdMB)]"
$GrowthThresholdMB = if ($inputMB.Trim())    { [int]$inputMB.Trim() }    else { $prev.GrowthThresholdMB }

$inputDays  = Read-Host "History range in days [$($prev.HistoryDays)]"
$HistoryDays       = if ($inputDays.Trim())  { [int]$inputDays.Trim() }  else { $prev.HistoryDays }

# Save settings back to sidecar
Set-Content $SidecarPath "TargetDirectory: '$TargetDirectory'`nGrowthThresholdMB: $GrowthThresholdMB`nHistoryDays: $HistoryDays"
# -------------------------

$SinceDate = (Get-Date).AddDays(-$HistoryDays)

Write-Host "Scanning '$TargetDirectory' for changes since $SinceDate..." -ForegroundColor Cyan
Write-Host "Looking for folders that grew by more than $GrowthThresholdMB MB..." -ForegroundColor Cyan
Write-Host "--------------------------------------------------------"

# Reserve the status line and record its position
Write-Host ""
$StatusRow = [Console]::CursorTop - 1

# Move cursor below the status line so results print beneath it
[Console]::SetCursorPosition(0, $StatusRow + 1)

function Write-Status ($text, $color = 'DarkCyan') {
    $saved = [Console]::CursorTop
    [Console]::SetCursorPosition(0, $script:StatusRow)
    $trimmed = if ($text.Length -gt [Console]::WindowWidth - 1) { $text.Substring(0, [Console]::WindowWidth - 1) } else { $text }
    Write-Host $trimmed.PadRight([Console]::WindowWidth - 1) -ForegroundColor $color -NoNewline
    [Console]::SetCursorPosition(0, $saved)
}

$spinner = @('|','/','-','\')
$ScanStart = Get-Date

try {
    # Phase 1: Build folder list (streaming, interruptible)
    Write-Status "$($spinner[0])  Running 0 sec.  Building folder list..."
    $SubFolders = [System.Collections.Generic.List[string]]::new()
    $i = 0
    $lastUpdate = [datetime]::Now
    $queue = [System.Collections.Generic.Queue[string]]::new()
    $queue.Enqueue($TargetDirectory)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        $children = try { [System.IO.Directory]::EnumerateDirectories($current) } catch { continue }
        foreach ($dir in $children) {
            $queue.Enqueue($dir)
            $SubFolders.Add($dir)
            if (([datetime]::Now - $lastUpdate).TotalMilliseconds -ge 250) {
                $elapsed = [int](New-TimeSpan -Start $ScanStart).TotalSeconds
                Write-Status "$($spinner[$i % 4])  Running $elapsed sec.  Building folder list... ($($SubFolders.Count) found)"
                $i++
                $lastUpdate = [datetime]::Now
            }
        }
    }
    $FolderCount = $SubFolders.Count

    # Phase 2: Analyze each folder
    $FlaggedFoldersCount = 0
    $FolderIndex = 0

    foreach ($Folder in $SubFolders) {
        $FolderIndex++
        $elapsed = [int](New-TimeSpan -Start $ScanStart).TotalSeconds
        Write-Status "Running $elapsed sec.  Analyzing $FolderIndex of $FolderCount  $Folder"

        $NewFiles = Get-ChildItem -Path $Folder -File -ErrorAction SilentlyContinue | Where-Object {
            $_.LastWriteTime -gt $SinceDate -or $_.CreationTime -gt $SinceDate
        }

        if ($NewFiles) {
            $TotalNewMB = [Math]::Round(($NewFiles | Measure-Object -Property Length -Sum).Sum / 1MB, 2)

            if ($TotalNewMB -ge $GrowthThresholdMB) {
                [Console]::SetCursorPosition(0, $script:StatusRow)
                Write-Host "⚠️  $Folder" -ForegroundColor Yellow
                Write-Host "    -> Grew by $TotalNewMB MB in the last $HistoryDays day(s)." -ForegroundColor White
                $script:StatusRow = [Console]::CursorTop
                Write-Host ""
                $FlaggedFoldersCount++
            }
        }
    }

    # Clear status line and print summary
    [Console]::SetCursorPosition(0, $script:StatusRow)
    Write-Host "".PadRight([Console]::WindowWidth - 1)
    [Console]::SetCursorPosition(0, $script:StatusRow)

    if ($FlaggedFoldersCount -eq 0) {
        Write-Host "Scan complete. No folders grew by more than $GrowthThresholdMB MB." -ForegroundColor Green
    } else {
        Write-Host "Scan complete. Found $FlaggedFoldersCount folder(s) matching criteria." -ForegroundColor Green
    }
    $completed = $true
} finally {
    if (-not $completed) {
        [Console]::SetCursorPosition(0, $script:StatusRow)
        Write-Host "".PadRight([Console]::WindowWidth - 1)
        [Console]::SetCursorPosition(0, $script:StatusRow)
    }
}
