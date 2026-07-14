#requires -Version 5.1
# Emit Gamma_* scheduled tasks as a JSON array. Used by setup/scripts/audit_scheduled_tasks.py.
#
# 2026-07-14 (J: "stop the fkin popups on my screen"): this enumeration was scoped to
# "Gamma_*" ONLY -- structurally blind to any other repo-managed automation on this
# box, e.g. SwjshAK-BrainSync (a daily git-sync task for the SwjshAlgoKnife reservoir
# repo, registered directly with a bare `powershell.exe -WindowStyle Hidden` action --
# same leak class as Gamma tasks, invisible to this audit purely because its name
# doesn't start with "Gamma_"). $ExtraTaskNames lists additional non-Gamma task names
# this repo's audit should still window-leak-check even though they aren't Gamma's own
# and won't appear in SCHEDULED-TASKS.md's registry (see KNOWN_EXTERNAL_TASKS in
# audit_scheduled_tasks.py, which exempts these from ORPHAN_TASK/STALE_REGISTRY_ENTRY
# while still fully subjecting them to the hidden-window checks).
$ErrorActionPreference = "Stop"
$ExtraTaskNames = @("SwjshAK-BrainSync")
$out = @()
$allTasks = @(Get-ScheduledTask -TaskName "Gamma_*")
foreach ($extraName in $ExtraTaskNames) {
    $extraTask = Get-ScheduledTask -TaskName $extraName -ErrorAction SilentlyContinue
    if ($extraTask) { $allTasks += $extraTask }
}
foreach ($t in $allTasks) {
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
