#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor RTH_LIGHT wake fire -- the bounded, verify-and-flag-only market-hours tick.

.DESCRIPTION
  Fires from Gamma_ConductorRTH (every 30 min, 09:30-15:55 ET weekdays). This is the ONE
  J-authorized exception (2026-07-18) to "the conductor never runs during market hours" --
  and it is an exception for a small read-only verify pass, NOT the heavy STAGE 1-5 loop.
  Same prompt file as the after-hours conductor (automation/prompts/conductor.md); the
  MODE it runs is selected by the injected `Task:` header field ("conductor-rth" here),
  which the prompt's own STAGE 0-RTH section branches on -- see conductor.md "MODES".

  SAFETY: low effort, tiny budget cap, short timeout -- sized so it CANNOT balloon into
  the kind of RTH fan-out that starved the heartbeat once before (L54 scar). Still gated
  in the wrapper as defense-in-depth (only proceeds weekday 09:30-15:55 ET); the prompt
  re-checks the same gate at STAGE 0-RTH step 1.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor-rth.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor-rth"
$today = (Get-Date).ToString("yyyy-MM-dd")

# --- GATE: weekday RTH ONLY (this task exists BECAUSE it is the market-hours exception --
# but only within 09:30-15:55 ET; a misfire outside that window still must not spend). -----
$et = Get-EtNow
$isRth = (Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)
if (-not $isRth) {
    Write-TaskLog -TaskName $task -Message ("conductor-rth: SKIP -- outside RTH window (" + $et.ToString("ddd HH:mm") + " ET), nothing to verify")
    exit 0
}

Write-TaskLog -TaskName $task -Message ("conductor-rth: START (" + $et.ToString("yyyy-MM-dd HH:mm") + " ET)")

$promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
if (-not (Test-Path $promptFile)) {
    Write-TaskLog -TaskName $task -Message "conductor-rth: ERROR conductor.md missing at $promptFile"
    exit 1
}

# Sonnet, LOW effort, small budget, short timeout -- STAGE 0-RTH is a ~10-tool-call
# read-and-flag pass by design (conductor.md MODES table). This cap is the real
# anti-runaway guard, same philosophy as run-conductor.ps1's TimeoutSec for the heavy loop.
$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 0.50 `
    -Model "sonnet" `
    -Effort "low" `
    -AgentName "gamma" `
    -TimeoutSec 90 `
    -MaxRateLimitWaitSec 300

Write-TaskLog -TaskName $task -Message "conductor-rth: END exit=$exitCode"
exit $exitCode
