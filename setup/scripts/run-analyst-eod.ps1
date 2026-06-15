#requires -Version 5.1
<#
.SYNOPSIS
  Daily Analyst EOD -- fires 16:45 ET via Gamma_AnalystEodReview.
  OP-30 FREE-TIER-FIRST: tries Nemotron/DeepSeek/MiniMax-free ladder first ($0).
  Only escalates to Claude (Sonnet) if the entire free-tier ladder fails.
  Fires AFTER Gamma_EodSummary (16:00) + Gamma_EodDeepDive (16:05) + Gamma_DailyReview (16:30).
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 for Invoke-PythonHidden, Invoke-ClaudeWithRetry, Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "analyst"
$today = (Get-Date).ToString("yyyy-MM-dd")

# Ensure analyst state dirs exist
foreach ($dir in @(
    (Join-Path $projectRoot "analysis\eod"),
    (Join-Path $projectRoot "analysis\patterns"),
    (Join-Path $projectRoot "strategy\candidates\_chef-inbox")
)) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
}

Write-TaskLog -TaskName $task -Message "analyst-eod: START"

# ── STEP 1: Free-tier primary (Nemotron → DeepSeek → MiniMax-free → MiniMax-paid) ──
# eod_fallback.py --primary tries the ladder at $0; tags output "FREE-TIER ROUTE"
Write-TaskLog -TaskName $task -Message "analyst-eod: trying free-tier primary (Nemotron ladder)"
$freeTierResult = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\eod_fallback.py" `
    -ArgList @("--task", "analyst", "--date", $today, "--primary") `
    -TaskName $task `
    -TimeoutSec 360

if ($freeTierResult.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "analyst-eod: free-tier PRIMARY OK"
    Write-TaskLog -TaskName $task -Message "analyst-eod: END exit=0"
    exit 0
}

Write-TaskLog -TaskName $task -Message "analyst-eod: free-tier failed exit=$($freeTierResult.ExitCode) -- escalating to Claude"

# ── STEP 2: Claude fallback (only if entire free-tier ladder failed) ──
$promptFile = Join-Path $env:TEMP "analyst-prompt-$today.txt"
@"
Execute your EOD routine for $today. Fire is automatic (Gamma_AnalystEodReview at 16:45 ET).

Your job (per .claude/agents/analyst.md):
1. Read today's journal, trades.csv, decisions.jsonl, EOD summary, gym scorecard, heartbeat tick audit
2. Review every trade taken and skipped against the 10 rules
3. Mine patterns from journal/trades.csv (archetypes, tape assistance, counterfactuals)
4. Write digest to analysis/eod/$today.md
5. Route findings to the correct skill-pipeline inboxes:
   - Engine foot-guns -> _validator-inbox/
   - New diagnostic skills -> _skill-inbox/
   - Doctrine lessons -> _lesson-inbox/
   - Strategy R&D candidates -> _chef-inbox/
6. Append one-line STATUS.md summary

Return a brief confirmation of what you wrote and where, plus any BROKEN flags.
"@ | Out-File -FilePath $promptFile -Encoding UTF8

$exitCode = Invoke-ClaudeWithRetry `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 0.60 `
    -Model "sonnet" `
    -Effort "medium" `
    -AgentName "analyst" `
    -MaxRateLimitWaitSec 7200

Remove-Item $promptFile -ErrorAction SilentlyContinue
Write-TaskLog -TaskName $task -Message "analyst-eod: END exit=$exitCode"
exit $exitCode
