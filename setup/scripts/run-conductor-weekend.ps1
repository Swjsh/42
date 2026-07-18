#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor WEEKEND wake fire -- the full "Gamma drives" loop, weekend cadence.

.DESCRIPTION
  Fires from Gamma_ConductorWeekend (every 2h, Saturday+Sunday, all day). Runs the SAME
  full STAGE 0->5 loop as the after-hours Gamma_Conductor -- read health + STATUS + queue,
  pick the single highest-value ready item, fan out a specialist, validate, ship-or-propose,
  learn, update state -- with the WEEKEND nudge in conductor.md's STAGE 1 (crypto-twin +
  Kitchen checked first, since nobody else reads them on a weekday-biased cadence).

  J directive 2026-07-18: "crypto weekends, futures n options during the week" -- weekends
  had ZERO daytime conductor coverage before this (the old Gamma_Conductor's 18:00-07:00 ET
  window only ever covered the overnight hours, even on a Saturday/Sunday). This wrapper
  closes that gap.

  SAME rails as run-conductor.ps1: after-hours-equivalent (market is never open on a
  weekend, but the gate is re-checked anyway as defense-in-depth against a misfire),
  fail-open, one-task-per-fire, PAPER-only trading-path edits.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor-weekend.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor-weekend"
$today = (Get-Date).ToString("yyyy-MM-dd")

# --- GATE: weekend ONLY (defense in depth -- the trigger is Weekly/Sat+Sun, this catches
# a misfire/manual Start-ScheduledTask on a weekday and refuses to spend on it). -----------
# NOTE (bug found + fixed live during the 2026-07-18 build/verification fire): an earlier
# version of this gate ALSO called Test-MarketHours on its own, unconjoined with
# Test-WeekDay -- that matches on CLOCK TIME alone and false-SKIPped a genuine Saturday
# fire simply because the ET hour (11:04) happened to fall inside the 09:30-15:55 numeric
# range. Test-WeekDay alone is the correct and sufficient gate here: a market is only ever
# "open" on a weekday in the first place, so ANY weekday (RTH or after-hours) correctly
# defers to Gamma_Conductor/Gamma_ConductorRTH, and no weekend clock-hour is ever RTH.
$et = Get-EtNow
if (Test-WeekDay -Et $et) {
    Write-TaskLog -TaskName $task -Message ("conductor-weekend: SKIP -- weekday (" + $et.ToString("ddd HH:mm") + " ET), this mode is weekend-only")
    exit 0
}

Write-TaskLog -TaskName $task -Message ("conductor-weekend: START (" + $et.ToString("yyyy-MM-dd HH:mm dddd") + " ET)")

# Same L181 retention + B2b twin-gauntlet autowires as run-conductor.ps1 -- STATUS.md
# silently regrows past the Read cap between fires regardless of which conductor mode
# is writing to it, and a weekend fire is exactly the kind of trading-path-adjacent
# session the gauntlet-gap check exists to catch.
try {
    $null = Invoke-PythonHidden -ScriptPath "setup\scripts\status_retention.py" `
        -ArgList @() -TaskName "status-retention" -TimeoutSec 30
} catch { }
try {
    $null = Invoke-PythonHidden -ScriptPath "setup\scripts\twin_gauntlet_conductor_hook.py" `
        -ArgList @() -TaskName "twin-gauntlet-conductor-hook" -TimeoutSec 30
} catch { }

$promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
if (-not (Test-Path $promptFile)) {
    Write-TaskLog -TaskName $task -Message "conductor-weekend: ERROR conductor.md missing at $promptFile"
    exit 1
}

# Sonnet, high effort, full $10 budget -- same as the after-hours full loop. The prompt's
# `Task: conductor-weekend` header selects WEEKEND mode (STAGE 1 twin/kitchen nudge);
# everything else is the identical STAGE 0->5 machinery.
$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 10.00 `
    -Model "sonnet" `
    -Effort "high" `
    -AgentName "gamma" `
    -TimeoutSec 600 `
    -MaxRateLimitWaitSec 3600

Write-TaskLog -TaskName $task -Message "conductor-weekend: END exit=$exitCode"
exit $exitCode
