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

    # TRIGGER SHAPE (2026-07-30, LEVELS-BLINDNESS incident): the audit was structurally
    # unable to see WHETHER a task still repeats. A task registered with a one-shot
    # trigger (or whose repetition was dropped) fires once and goes dark forever, and
    # every field emitted above still looks healthy -- NextRunTime even keeps advancing.
    # Emit the trigger definition so audit_scheduled_tasks.py can compare live cadence
    # against the cadence SCHEDULED-TASKS.md documents. Purely additive field.
    $trigs = @()
    if ($t.Triggers) {
        foreach ($tr in $t.Triggers) {
            $cls = ""
            if ($tr.CimClass -and $tr.CimClass.CimClassName) {
                $cls = $tr.CimClass.CimClassName -replace '^MSFT_Task', ''
            }
            $repInt = $null; $repDur = $null
            if ($tr.Repetition) {
                if ($tr.Repetition.Interval) { $repInt = [string]$tr.Repetition.Interval }
                if ($tr.Repetition.Duration) { $repDur = [string]$tr.Repetition.Duration }
            }
            $dow = $null
            if (($tr.PSObject.Properties.Name -contains 'DaysOfWeek') -and ($null -ne $tr.DaysOfWeek)) {
                $dow = [int]$tr.DaysOfWeek
            }
            # DAYS-INTERVAL (2026-08-28, GITHUB-AUDIT-FALSE-RED incident): a DailyTrigger's
            # DaysInterval (e.g. "every 2 days") was never emitted here, so
            # unattended_health.py's expected_gap_minutes() had no way to see it and
            # silently treated EVERY DailyTrigger as a 1-day cadence -- an every-N-day task
            # got a budget of exactly 2*1440min regardless of N, i.e. ZERO slack for a
            # single missed run once N>=2 (contradicting this file's own stated design:
            # "daily/weekly ones get 2, which tolerates EXACTLY ONE missed run"). Purely
            # additive field; only DailyTrigger carries DaysInterval.
            $daysInterval = $null
            if (($tr.PSObject.Properties.Name -contains 'DaysInterval') -and ($null -ne $tr.DaysInterval)) {
                $daysInterval = [int]$tr.DaysInterval
            }
            $trigs += [PSCustomObject]@{
                type = $cls
                start_boundary = if ($tr.StartBoundary) { [string]$tr.StartBoundary } else { $null }
                repetition_interval = $repInt
                repetition_duration = $repDur
                days_of_week = $dow
                days_interval = $daysInterval
                enabled = [bool]$tr.Enabled
            }
        }
    }

    $out += [PSCustomObject]@{
        name = $t.TaskName
        state = $t.State.ToString()
        execute = if ($a) { $a.Execute } else { "" }
        arguments = if ($a) { $a.Arguments } else { "" }
        last_run = $lastRun
        last_result = $lastResult
        next_run = $nextRun
        triggers = @($trigs)
    }
}
$out | ConvertTo-Json -Depth 7 -Compress
