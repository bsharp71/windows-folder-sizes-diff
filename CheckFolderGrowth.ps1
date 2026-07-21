# Identify folders where contents have grown more than the threshhold since yesterday.

# Run this if script needs permission
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# --- CONFIGURATION ---
$TargetDirectory = "C:\" # Change to the directory you want to scan
$GrowthThresholdMB = 100                        # Minimum size increase to report
# ---------------------

# Calculate the timestamp for exactly 24 hours ago
$24HoursAgo = (Get-Date).AddDays(-1)

Write-Host "Scanning '$TargetDirectory' for changes since $24HoursAgo..." -ForegroundColor Cyan
Write-Host "Looking for folders that grew by more than $GrowthThresholdMB MB..." -ForegroundColor Cyan
Write-Host "--------------------------------------------------------"

# Get all subdirectories
$SubFolders = Get-ChildItem -Path $TargetDirectory -Directory -Recurse -ErrorAction SilentlyContinue

$FlaggedFoldersCount = 0

foreach ($Folder in $SubFolders) {
    # Find files inside this specific folder modified or created in the last 24 hours
    $NewFiles = Get-ChildItem -Path $Folder.FullName -File -ErrorAction SilentlyContinue | Where-Object {
        $_.LastWriteTime -gt $24HoursAgo -or $_.CreationTime -gt $24HoursAgo
    }

    if ($NewFiles) {
        # Sum up the sizes of the new/modified files
        $TotalNewBytes = ($NewFiles | Measure-Object -Property Length -Sum).Sum
        $TotalNewMB = [Math]::Round($TotalNewBytes / 1MB, 2)

        # Check if the growth exceeds your threshold
        if ($TotalNewMB -ge $GrowthThresholdMB) {
            Write-Host "⚠️ $($Folder.FullName)" -ForegroundColor Yellow
            Write-Host "   -> Grew by $TotalNewMB MB in the last 24 hours." -ForegroundColor White
            $FlaggedFoldersCount++
        }
    }
}

if ($FlaggedFoldersCount -eq 0) {
    Write-Host "Scan complete. No folders grew by more than $GrowthThresholdMB MB since yesterday." -ForegroundColor Green
} else {
    Write-Host "Scan complete. Found $FlaggedFoldersCount folder(s) matching criteria." -ForegroundColor Green
}
