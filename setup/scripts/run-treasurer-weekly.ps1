#requires -Version 5.1
<#
.SYNOPSIS
  Weekly Treasurer invocation -- fires Sunday 16:00 ET via Gamma_TreasurerWeekly.
  AFTER Friday EOD pipeline, BEFORE Gamma_WeeklyReview (18:00).
  Audits sizing math vs current equity for both accounts.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 to get $Global:ClaudeExe (full path) + Invoke-Claude + Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "treasurer"

# Ensure treasury state dirs exist
$treasuryDir = Join-Path $projectRoot "analysis\treasury"
if (-not (Test-Path $treasuryDir)) { New-Item -ItemType Directory -Path $treasuryDir -Force | Out-Null }

Write-TaskLog -TaskName $task -Message "treasurer-weekly: START"

# Write prompt to temp file
$today = (Get-Date).ToString("yyyy-MM-dd")
$promptFile = Join-Path $env:TEMP "treasurer-prompt-$today.txt"
@"
Execute your weekly audit routine for $today. Fire is automatic (Gamma_TreasurerWeekly Sunday 16:00 ET).

Your job (per .claude/agents/treasurer.md):
1. Pull both account balances (Gamma-Safe PA3PHRM47D1J + Gamma-Risky PA35NRWPGKD5) via Alpaca MCP
2. Audit sizing math: per-trade risk %, daily kill-switch thresholds, account tier vs current equity
3. Check PDT awareness: trades remaining in rolling 5-day window
4. Review any account-tier transitions needed ($1K->$2K->$10K->$25K)
5. Write analysis/treasury/{today}.md with full audit
6. Write DRAFT params changes if needed (analysis/treasury/draft-params-changes.md) -- NEVER modify params*.json directly
7. Return the audit summary with any recommended changes.
"@ | Out-File -FilePath $promptFile -Encoding UTF8

$exitCode = Invoke-Claude `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 0.30 `
    -Model "sonnet" `
    -Effort "medium" `
    -AgentName "treasurer"

Remove-Item $promptFile -ErrorAction SilentlyContinue
Write-TaskLog -TaskName $task -Message "treasurer-weekly: END exit=$exitCode"
exit $exitCode
