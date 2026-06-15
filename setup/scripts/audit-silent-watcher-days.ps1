#!/usr/bin/env pwsh
# Audit watcher-observations.jsonl for any trading-day silent zero-observation pattern.
# Reads JSONL, groups by bar_timestamp_et date, counts entries per date + per watcher.
$ErrorActionPreference = "Continue"
$file = 'C:\Users\jackw\Desktop\42\automation\state\watcher-observations.jsonl'

if (-not (Test-Path $file)) {
    Write-Output "watcher-observations.jsonl NOT FOUND"
    exit 1
}

$lines = Get-Content $file
Write-Output ("Total observations: " + $lines.Count)
Write-Output ""

# Parse + group by bar date
$byDate = @{}
$byWatcher = @{}
foreach ($line in $lines) {
    try {
        $obj = $line | ConvertFrom-Json
        $barTs = $obj.bar_timestamp_et
        if ($barTs) {
            $datePart = $barTs.Substring(0, 10)
            if (-not $byDate.ContainsKey($datePart)) { $byDate[$datePart] = 0 }
            $byDate[$datePart]++
        }
        $w = $obj.watcher_name
        if ($w) {
            if (-not $byWatcher.ContainsKey($w)) { $byWatcher[$w] = 0 }
            $byWatcher[$w]++
        }
    } catch {
        Write-Output ("JSON parse error: " + $_.Exception.Message)
    }
}

Write-Output "--- OBSERVATIONS BY BAR-DATE ---"
$sorted = $byDate.GetEnumerator() | Sort-Object Name
foreach ($entry in $sorted) {
    Write-Output ($entry.Name + ": " + $entry.Value + " observations")
}
Write-Output ""

Write-Output "--- OBSERVATIONS BY WATCHER ---"
$wsorted = $byWatcher.GetEnumerator() | Sort-Object -Property Value -Descending
foreach ($entry in $wsorted) {
    Write-Output ($entry.Name + ": " + $entry.Value)
}
Write-Output ""

# Identify recent silent days (5/10-5/13 = 4 trading days)
Write-Output "--- RECENT TRADING DAY COVERAGE ---"
$recent = @("2026-05-08", "2026-05-11", "2026-05-12", "2026-05-13")
foreach ($d in $recent) {
    $count = if ($byDate.ContainsKey($d)) { $byDate[$d] } else { 0 }
    $verdict = if ($count -eq 0) { "SILENT-DAY" } else { "OK" }
    Write-Output ($d + ": " + $count + " observations  [" + $verdict + "]")
}
