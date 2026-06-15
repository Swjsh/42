#!/usr/bin/env pwsh
# Pre-flight readiness audit for tomorrow's market open (5/14 09:30 ET).
# Verifies each operational scheduled task's command line + trigger times.
$ErrorActionPreference = "Continue"

$tasks = @(
    "Gamma_LaunchTV",
    "Gamma_Premarket",
    "Gamma_Heartbeat",
    "Gamma_EodFlatten",
    "Gamma_EodSummary",
    "Gamma_DailyReview",
    "Gamma_WatcherLive",
    "Gamma_WatcherMorningReport",
    "Gamma_WatcherReplay",
    "Gamma_DiscordWatchdog",
    "Gamma_SelfAudit"
)

Write-Output "=== PRE-FLIGHT READINESS AUDIT 5/14 ==="
Write-Output ("audit_at: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"))
Write-Output ""

foreach ($name in $tasks) {
    try {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        $info = Get-ScheduledTaskInfo -TaskName $name -ErrorAction SilentlyContinue
        $actions = $task.Actions
        $triggers = $task.Triggers

        Write-Output ("--- " + $name + " ---")
        Write-Output ("  State:        " + $task.State)
        Write-Output ("  LastRun:      " + $info.LastRunTime)
        Write-Output ("  LastResult:   " + $info.LastTaskResult)
        Write-Output ("  NextRun:      " + $info.NextRunTime)

        foreach ($a in $actions) {
            if ($a -is [Microsoft.Management.Infrastructure.CimInstance]) {
                $execPath = $a.CimInstanceProperties["Execute"].Value
                $args = $a.CimInstanceProperties["Arguments"].Value
                Write-Output ("  Execute:      " + $execPath)
                Write-Output ("  Arguments:    " + $args)
            } else {
                Write-Output ("  Action:       " + ($a | Out-String).Trim())
            }
        }

        foreach ($t in $triggers) {
            $tStart = $t.StartBoundary
            $rep = $t.Repetition
            Write-Output ("  StartBoundary: " + $tStart)
            if ($rep -and $rep.Interval) {
                Write-Output ("  Interval:     " + $rep.Interval)
                Write-Output ("  Duration:     " + $rep.Duration)
            }
        }
        Write-Output ""
    } catch {
        Write-Output ("--- " + $name + " ---")
        Write-Output ("  ERROR: " + $_.Exception.Message)
        Write-Output ""
    }
}
