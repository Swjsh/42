#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor wake fire -- the "Gamma drives" engine.

.DESCRIPTION
  Fires from Gamma_Conductor (after-hours cadence). Runs ONE bounded conductor
  tick: read engine-health + STATUS + the prioritized queue, pick the single
  highest-value ready item, fan out the right specialist persona, validate
  (gym/tests), SHIP if it clears the auto-ratify gate ELSE flag J via Discord,
  update STATUS + queue, exit. Prompt: automation/prompts/conductor.md.
  Persona: .claude/agents/gamma.md (Manager mode). Model: opus.

  SAFETY RAIL 1 (after-hours only, L54): this wrapper hard-gates on market hours
  as defense-in-depth. If it is a weekday and 09:30 <= ET < 15:55, the conductor
  does NOT spawn Claude -- a market-hours fan-out would starve the heartbeat on
  the shared Max rate-limit pool. The prompt re-checks this gate (STAGE 0), but
  the wrapper refusing first means zero model spend during RTH.

  SAFETY RAIL 2 (fail-open): this wrapper NEVER kills/blocks any process. It only
  spawns its own claude --print (tree-scoped self-heal in Invoke-Claude) and exits.

  Invoked via the OP-27 L42 canonical zero-leak chain:
    Task Scheduler -> wscript.exe -> run_exe_hidden.vbs -> sys-pythonw
                   -> run_ps1_hidden.py -> run-conductor.ps1 -> claude --print
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor"
$today = (Get-Date).ToString("yyyy-MM-dd")

# --- SAFETY RAIL 1: after-hours gate (defense in depth; prompt re-checks) ------
$et = Get-EtNow
if ((Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et -StartHour 9 -StartMin 30 -EndHour 15 -EndMin 55)) {
    Write-TaskLog -TaskName $task -Message ("conductor: SKIP -- market open (" + $et.ToString("HH:mm") + " ET), deferring to heartbeat (rail 1 / L54)")
    exit 0
}

Write-TaskLog -TaskName $task -Message ("conductor: START (" + $et.ToString("yyyy-MM-dd HH:mm") + " ET)")

$promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
if (-not (Test-Path $promptFile)) {
    Write-TaskLog -TaskName $task -Message "conductor: ERROR conductor.md missing at $promptFile"
    exit 1
}

# Opus -- the conductor's job is hard reasoning (single highest-leverage item +
# is it safe to ship). One bounded fire; ~$1.50 budget cap. AgentName=gamma loads
# Manager-mode persona context. Retry wrapper handles rate-limit skip-ahead.
$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 1.50 `
    -Model "opus" `
    -Effort "high" `
    -AgentName "gamma" `
    -TimeoutSec 600 `
    -MaxRateLimitWaitSec 3600

Write-TaskLog -TaskName $task -Message "conductor: END exit=$exitCode"
exit $exitCode
