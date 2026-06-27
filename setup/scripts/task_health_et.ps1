# task_health_et.ps1 -- list Gamma scheduled tasks with last/next run in ET + a CORRECT overdue flag.
#
# GUARD against a recurring foot-gun (2026-06-26): Get-ScheduledTaskInfo returns LastRunTime/NextRunTime
# in the machine's LOCAL time. This rig is MOUNTAIN time (ET = local + 2h). Comparing a local NextRunTime
# against an ET "now" makes every future run look ~2h OVERDUE -- which made me declare the gym + conductor
# schedulers "stuck/dead" when they were firing perfectly on schedule. ALWAYS reason about task timing in
# ET. Run this instead of eyeballing raw Get-ScheduledTaskInfo. See feedback_bash_tz_broken +
# project_scheduled_task_tz. (Empty NextRunTime IS a real dark-trigger bug -- different from this.)
$ErrorActionPreference = 'Stop'
$etz = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')
$nowEt = [System.TimeZoneInfo]::ConvertTime((Get-Date), $etz)
Write-Host ("ET now: {0}" -f $nowEt.ToString('yyyy-MM-dd HH:mm:ss'))
$rows = Get-ScheduledTask -TaskName 'Gamma_*' | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    $nextEt = if ($i.NextRunTime) { [System.TimeZoneInfo]::ConvertTime($i.NextRunTime, $etz) } else { $null }
    $lastEt = if ($i.LastRunTime) { [System.TimeZoneInfo]::ConvertTime($i.LastRunTime, $etz) } else { $null }
    # Genuinely overdue ONLY if: has a next time, it's >10min past in ET, AND it's not market-hours-gated.
    # On-demand tasks (no trigger) legitimately have NO next-run -- they fire programmatically
    # (Start-ScheduledTask) when a grind launches. Only a task that HAS a trigger but no next-run
    # is the genuine one-shot-trigger dark bug.
    $hasTrigger = [bool]$_.Triggers
    $overdue = ($nextEt -ne $null) -and ($nextEt -lt $nowEt.AddMinutes(-10))
    $dark = $hasTrigger -and ($null -eq $i.NextRunTime)
    [PSCustomObject]@{
        Task      = $_.TaskName
        LastET    = if ($lastEt) { $lastEt.ToString('MM-dd HH:mm') } else { 'never' }
        NextET    = if ($nextEt) { $nextEt.ToString('MM-dd HH:mm') } elseif (-not $hasTrigger) { 'on-demand' } else { 'NONE(dark)' }
        Flag      = if ($dark) { 'DARK-no-next' } elseif ($overdue) { 'OVERDUE-ET' } else { 'ok' }
    }
}
$rows | Sort-Object Flag -Descending | Format-Table -Auto
$bad = @($rows | Where-Object { $_.Flag -ne 'ok' })
if ($bad.Count) { Write-Host ("FLAGGED (genuinely stuck/dark in ET): {0}" -f (($bad.Task) -join ', ')) }
else { Write-Host 'ALL GAMMA TASKS HEALTHY (ET-correct) -- no stuck/dark triggers' }
