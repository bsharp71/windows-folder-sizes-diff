
# Run this if script needs permission
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# --- CONFIGURATION ---
$TargetDirectory = "C:\" # Set this to your user folder or "C:\" for a full drive check
$GrowthThresholdMB = 100
# ---------------------

$24HoursAgo = (Get-Date).AddDays(-1)
Write-Host "Scanning directory changes since $24HoursAgo..." -ForegroundColor Cyan

# Get a list of all subdirectories to process one by one
$SubFolders = Get-ChildItem -Path $TargetDirectory -Directory -Recurse -ErrorAction SilentlyContinue
$TotalFolders = $SubFolders.Count

$Report = @()
$CurrentIndex = 0

# 1. Check files directly in the root target directory first
$RootFiles = Get-ChildItem -Path $TargetDirectory -File -ErrorAction SilentlyContinue | 
    Where-Object { $_.LastWriteTime -gt $24HoursAgo -or $_.CreationTime -gt $24HoursAgo }
if ($RootFiles) {
    $Size = ($RootFiles | Measure-Object -Property Length -Sum).Sum
    if ($Size -ge ($GrowthThresholdMB * 1MB)) {
        $Report += [PSCustomObject]@{ FolderPath = $TargetDirectory; GrowthMB = [Math]::Round($Size / 1MB, 2) }
    }
}

# 2. Process all subfolders individually to provide live status updates
foreach ($Folder in $SubFolders) {
    $CurrentIndex++
    
    # Format the live status line (Trims long folder paths so they don't break the single-line layout)
    $DisplayPath = $Folder.FullName
    if ($DisplayPath.Length -gt 60) { $DisplayPath = "..." + $DisplayPath.Substring($DisplayPath.Length - 57) }
    
    # The `r character resets the cursor to the start of the line. The spaces at the end clear old trailing text.
    Write-Host -NoNewline "`r Checking ($CurrentIndex/$TotalFolders): $DisplayPath                     "

    # Find modified files inside this specific folder
    $RecentFiles = Get-ChildItem -Path $Folder.FullName -File -ErrorAction SilentlyContinue | 
        Where-Object { $_.LastWriteTime -gt $24HoursAgo -or $_.CreationTime -gt $24HoursAgo }

    if ($RecentFiles) {
        $FolderSize = ($RecentFiles | Measure-Object -Property Length -Sum).Sum
        if ($FolderSize -ge ($GrowthThresholdMB * 1MB)) {
            $Report += [PSCustomObject]@{
                FolderPath = $Folder.FullName
                GrowthMB   = [Math]::Round($FolderSize / 1MB, 2)
            }
        }
    }
}

# Overwrite and clear the final status line completely before showing results
Write-Host -NoNewline "`r                                                                                `r"

# 3. Final Output Report
if ($Report) {
    Write-Host "--- Found the space hogs! ---" -ForegroundColor Yellow
    $Report | Sort-Object GrowthMB -Descending | ForEach-Object {
        Write-Host "⚠️ $($_.FolderPath)" -ForegroundColor White
        Write-Host "   -> Grew by $($_.GrowthMB) MB" -ForegroundColor Red
    }
} else {
    Write-Host "Scan complete. No folders grew by more than $GrowthThresholdMB MB." -ForegroundColor Green
}
