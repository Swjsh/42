#!/usr/bin/env pwsh
$diagFile = 'C:\Users\jackw\Desktop\42\automation\state\watcher-live-diag.jsonl'
$obsFile = 'C:\Users\jackw\Desktop\42\automation\state\watcher-observations.jsonl'

Write-Output "=== watcher-live-diag.jsonl ==="
if (Test-Path $diagFile) {
    $f = Get-Item $diagFile
    Write-Output ("size_bytes: " + $f.Length)
    Write-Output ("last_write: " + $f.LastWriteTime)
    $lines = Get-Content $diagFile
    Write-Output ("total_lines: " + $lines.Count)
    if ($lines.Count -gt 0) {
        Write-Output ""
        Write-Output "--- FIRST ENTRY ---"
        Write-Output $lines[0]
        Write-Output ""
        Write-Output "--- LAST ENTRY ---"
        Write-Output $lines[-1]

        # Count signals_emitted across all lines
        $totalSignals = 0
        $linesWithSignals = 0
        $maxMdr = 0
        $sniper5dHighSet = $false
        foreach ($line in $lines) {
            try {
                $obj = $line | ConvertFrom-Json
                if ($obj.signals_emitted -ne $null) {
                    $totalSignals += [int]$obj.signals_emitted
                    if ($obj.signals_emitted -gt 0) { $linesWithSignals++ }
                }
                if ($obj.multi_day_rth_rows -gt $maxMdr) { $maxMdr = $obj.multi_day_rth_rows }
                if ($obj.sniper_5d_high -ne $null -and $obj.sniper_5d_high -ne 0) { $sniper5dHighSet = $true }
            } catch { }
        }
        Write-Output ""
        Write-Output "--- TODAY SUMMARY ---"
        Write-Output ("total_signals_emitted: " + $totalSignals)
        Write-Output ("fires_with_signals: " + $linesWithSignals + " / " + $lines.Count)
        Write-Output ("max_multi_day_rth_rows: " + $maxMdr)
        Write-Output ("sniper_5d_high_populated: " + $sniper5dHighSet)
    }
} else {
    Write-Output "NOT FOUND - watcher_live did not write diag-trail today!"
}

Write-Output ""
Write-Output "=== watcher-observations.jsonl 5/14 entries ==="
if (Test-Path $obsFile) {
    $obsLines = Get-Content $obsFile
    $today = $obsLines | Where-Object { $_ -like "*bar_timestamp_et*2026-05-14*" }
    Write-Output ("today_obs_count: " + $today.Count)
    if ($today.Count -gt 0) {
        $byWatcher = @{}
        foreach ($line in $today) {
            try {
                $obj = $line | ConvertFrom-Json
                $w = $obj.watcher_name
                if (-not $byWatcher.ContainsKey($w)) { $byWatcher[$w] = 0 }
                $byWatcher[$w]++
            } catch { }
        }
        Write-Output "by watcher:"
        foreach ($k in ($byWatcher.Keys | Sort-Object)) {
            Write-Output ("  " + $k + ": " + $byWatcher[$k])
        }
    }
} else {
    Write-Output "watcher-observations.jsonl NOT FOUND"
}
