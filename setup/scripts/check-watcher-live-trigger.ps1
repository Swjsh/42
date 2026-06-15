#!/usr/bin/env pwsh
$tr = (Get-ScheduledTask -TaskName 'Gamma_WatcherLive').Triggers[0]
Write-Output ("Repetition.Interval: " + $tr.Repetition.Interval)
Write-Output ("Repetition.Duration: " + $tr.Repetition.Duration)
Write-Output ("Enabled: " + $tr.Enabled)
Write-Output ("StartBoundary: " + $tr.StartBoundary)
Write-Output ("EndBoundary: " + $tr.EndBoundary)

# Watcher state file
$stateFile = 'C:\Users\jackw\Desktop\42\automation\state\watcher_live_state.json'
if (Test-Path $stateFile) {
    Write-Output ""
    Write-Output "--- watcher_live_state.json ---"
    Get-Content $stateFile -Raw
} else {
    Write-Output "watcher_live_state.json NOT FOUND"
}
