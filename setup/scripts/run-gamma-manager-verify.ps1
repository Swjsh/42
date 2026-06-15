#requires -Version 5.1
<#
.SYNOPSIS
  Daily Gamma Manager verification -- fires 17:30 ET via Gamma_ManagerDailyVerify.
  OP-30 FREE-TIER-FIRST: tries Nemotron/DeepSeek/MiniMax-free ladder first ($0).
  Only escalates to Claude (Sonnet) if the entire free-tier ladder fails.
  AFTER Analyst (16:45) has written today's EOD digest.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 for Invoke-PythonHidden, Invoke-ClaudeWithRetry, Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "gamma-manager"
$today = (Get-Date).ToString("yyyy-MM-dd")

# Ensure dirs exist
$briefDir = Join-Path $projectRoot "analysis\daily-brief"
if (-not (Test-Path $briefDir)) { New-Item -ItemType Directory -Path $briefDir -Force | Out-Null }

Write-TaskLog -TaskName $task -Message "gamma-manager-verify: START"

# ── STEP 1: Free-tier primary (Nemotron → DeepSeek → MiniMax-free → MiniMax-paid) ──
Write-TaskLog -TaskName $task -Message "gamma-manager-verify: trying free-tier primary (Nemotron ladder)"
$freeTierResult = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\eod_fallback.py" `
    -ArgList @("--task", "manager", "--date", $today, "--primary") `
    -TaskName $task `
    -TimeoutSec 360

if ($freeTierResult.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "gamma-manager-verify: free-tier PRIMARY OK"
    Write-TaskLog -TaskName $task -Message "gamma-manager-verify: END exit=0"
    exit 0
}

Write-TaskLog -TaskName $task -Message "gamma-manager-verify: free-tier failed exit=$($freeTierResult.ExitCode) -- escalating to Claude"

# ── STEP 2: Claude fallback (only if entire free-tier ladder failed) ──
$promptFile = Join-Path $env:TEMP "gamma-manager-prompt-$today.txt"
@"
Execute your Manager-mode daily verification for $today. Fire is automatic (Gamma_ManagerDailyVerify at 17:30 ET, after Analyst 16:45 ET).

Your job (per .claude/agents/gamma.md Manager mode):
1. Verify all 11 daily loop phases ran (LaunchTV, Swarm, Premarket, Heartbeat x2, EodFlatten x2, EodSummary, EodDeepDive, DailyReview, Analyst)
2. Verify all 7 handoffs (swarm_output.json, today-bias.json, decisions.jsonl, journal/{today}.md, key-levels.json, analysis/eod/{today}.md)
3. Write analysis/daily-brief/{today}.md -- J's morning brief (what happened, what matters tomorrow)
4. Write automation/state/daily-loop-status-{today}.json
5. Append one-line summary to automation/overnight/STATUS.md

Return confirmation of what you wrote and any BROKEN flags found.
"@ | Out-File -FilePath $promptFile -Encoding UTF8

$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 0.70 `
    -Model "sonnet" `
    -Effort "medium" `
    -AgentName "gamma" `
    -MaxRateLimitWaitSec 7200

Remove-Item $promptFile -ErrorAction SilentlyContinue
Write-TaskLog -TaskName $task -Message "gamma-manager-verify: END exit=$exitCode"
exit $exitCode
