#requires -Version 5.1
<#
.SYNOPSIS
  Install the autonomous Kitchen: 3 scheduled tasks for 24/7 free-model R&D.

.DESCRIPTION
  Per CLAUDE.md OP-30 + J directive 2026-05-21 "24/7 free model cooking, Claude
  is the driver, pure autonomy". Registers three tasks via OP-27 L42 canonical
  zero-leak chain (wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> PS1).

  Tasks:
    Gamma_KitchenDaemonKeepalive  -- every 5 min, restarts kitchen_daemon.py if dead.
                                     The daemon is a long-running pythonw that processes
                                     cook-queue.jsonl through the OpenRouter free-tier ladder.
    Gamma_KitchenSeeder           -- hourly, generates 5 new cook tasks via Nemotron.
    Gamma_KitchenReviewer         -- every 2h, triages cook outputs, queues follow-ups.

  Cost target: $0/day primary (free tier), <$3/day worst case (paid fallback hard-capped).
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"

foreach ($p in @($runPs1Hidden, $runExeHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Register-KitchenTask {
    param(
        [string]$Name,
        [string]$Ps1,
        [string]$Description,
        [scriptblock]$TriggerBuilder,
        [int]$LimitMinutes = 15
    )
    $targetPs1 = Join-Path $ScriptsDir $Ps1
    if (-not (Test-Path $targetPs1)) {
        Write-Error "PS1 missing: $targetPs1"
        return
    }

    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue

    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

    $trigger = & $TriggerBuilder

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes $LimitMinutes)

    Register-ScheduledTask `
        -TaskName $Name `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description | Out-Null
    Write-Output "OK: $Name"
}

# 1. Keepalive every 5 min, 24/7
Register-KitchenTask `
    -Name "Gamma_KitchenDaemonKeepalive" `
    -Ps1 "run-kitchen-daemon-keepalive.ps1" `
    -Description "Every 5 min, restarts kitchen_daemon.py if dead. Daemon processes cook-queue.jsonl 24/7 via OpenRouter free tier (Nemotron primary)." `
    -LimitMinutes 5 `
    -TriggerBuilder {
        $start = (Get-Date).Date
        $t = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1
        $t.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
            -RepetitionInterval (New-TimeSpan -Minutes 5) `
            -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
        $t
    }

# 2. Seeder hourly, 24/7 (autonomous task generation)
Register-KitchenTask `
    -Name "Gamma_KitchenSeeder" `
    -Ps1 "run-kitchen-seeder.ps1" `
    -Description "Hourly. Reads leaderboard + lessons + journal, asks Nemotron to brainstorm 5 new cook tasks, enqueues to cook-queue.jsonl. Skipped if pending backlog >= 25." `
    -LimitMinutes 10 `
    -TriggerBuilder {
        $start = (Get-Date).Date.AddMinutes(20)  # offset from top-of-hour to spread load
        $t = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1
        $t.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
            -RepetitionInterval (New-TimeSpan -Hours 1) `
            -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
        $t
    }

# 3. Reviewer every 2 hours, 24/7
Register-KitchenTask `
    -Name "Gamma_KitchenReviewer" `
    -Ps1 "run-kitchen-reviewer.ps1" `
    -Description "Every 2 hours. Triages recent cook outputs (PROMOTE/VALIDATE/DUPLICATE/LOW_QUALITY) and queues follow-up tasks. Writes digest to analysis/kitchen-review/." `
    -LimitMinutes 15 `
    -TriggerBuilder {
        $start = (Get-Date).Date.AddMinutes(45)  # offset from seeder (20min) by 25min
        $t = New-ScheduledTaskTrigger -Daily -At $start -DaysInterval 1
        $t.Repetition = (New-ScheduledTaskTrigger -Once -At $start `
            -RepetitionInterval (New-TimeSpan -Hours 2) `
            -RepetitionDuration (New-TimeSpan -Days 1)).Repetition
        $t
    }

Write-Output ""
Write-Output "All 3 Kitchen tasks registered."
Write-Output ""
Write-Output "Verify: Get-ScheduledTask -TaskName 'Gamma_Kitchen*' | Format-Table"
Write-Output "Audit:  python setup\scripts\audit_scheduled_tasks.py"
Write-Output "Status: python setup\scripts\kitchen_daemon.py status"
Write-Output ""
Write-Output "The daemon starts on the NEXT keepalive fire (within 5 min)."
