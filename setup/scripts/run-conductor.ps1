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

# --- L181 RETENTION AUTOWIRE (self-executing, after-hours only) -----------------
# STATUS.md silently regrows past the ~25K-token Read cap between fires -- the
# 06-22 + 06-24 manual trims each regrew within hours (commit a795fc3 BUILT the
# durable guard; this call makes it run without a fire having to NOTICE + run it).
# status_retention.py is idempotent (no-op when under budget), fail-open (never
# throws), and atomic-write -- safe to call on every after-hours conductor wake.
# Runs AFTER the rail-1 gate (after-hours only) and BEFORE the claude launch so
# THIS fire reads a freshly-trimmed STATUS. CREATE_NO_WINDOW (no flash, OP-27 L42).
try {
    $null = Invoke-PythonHidden -ScriptPath "setup\scripts\status_retention.py" `
        -ArgList @() -TaskName "status-retention" -TimeoutSec 30
} catch { }

$promptFile = Join-Path $projectRoot "automation\prompts\conductor.md"
if (-not (Test-Path $promptFile)) {
    Write-TaskLog -TaskName $task -Message "conductor: ERROR conductor.md missing at $promptFile"
    exit 1
}

# Opus -- the conductor's job is hard reasoning (single highest-leverage item +
# is it safe to ship). AgentName=gamma loads Manager-mode persona context. Retry
# wrapper handles rate-limit skip-ahead.
# BUDGET (2026-06-20): raised 1.50 -> 10.00. The FIRST live fire aborted at t+1s
# with "Exceeded USD budget (1.5)" having done ZERO work -- same failure class as
# run-heartbeat.ps1:163. --max-budget-usd counts CUMULATIVE input tokens (cache
# reads + every tool result becomes next-turn input), and an opus + high-effort
# fire that loads CLAUDE.md + conductor.md + the gamma agent's full MCP tool
# surface (alpaca + alpaca_aggressive + tradingview + discord) AND fans out
# specialist sub-agents (whose tokens roll up into this session) blows past 1.50
# immediately. 10.00 lets one bounded fan-out fire + validation actually COMPLETE;
# the real runaway guard is -TimeoutSec 600 below, not the dollar cap.
$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 10.00 `
    -Model "opus" `
    -Effort "high" `
    -AgentName "gamma" `
    -TimeoutSec 600 `
    -MaxRateLimitWaitSec 3600

Write-TaskLog -TaskName $task -Message "conductor: END exit=$exitCode"
exit $exitCode
