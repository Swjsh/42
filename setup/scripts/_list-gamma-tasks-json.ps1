#requires -Version 5.1
# Emit Gamma_* scheduled tasks as a JSON array. Used by setup/scripts/audit_scheduled_tasks.py.
$ErrorActionPreference = "Stop"
$out = @()
foreach ($t in (Get-ScheduledTask -TaskName "Gamma_*")) {
    $a = if ($t.Actions -and $t.Actions.Count -gt 0) { $t.Actions[0] } else { $null }
    $info = $null
    try { $info = $t | Get-ScheduledTaskInfo } catch { $info = $null }
    $lastRun = if ($info -and $info.LastRunTime) { $info.LastRunTime.ToString("o") } else { $null }
    $nextRun = if ($info -and $info.NextRunTime) { $info.NextRunTime.ToString("o") } else { $null }
    $lastResult = if ($info) { $info.LastTaskResult } else { $null }
    $out += [PSCustomObject]@{
        name = $t.TaskName
        state = $t.State.ToString()
        execute = if ($a) { $a.Execute } else { "" }
        arguments = if ($a) { $a.Arguments } else { "" }
        last_run = $lastRun
        last_result = $lastResult
        next_run = $nextRun
    }
}
$out | ConvertTo-Json -Depth 5 -Compress
