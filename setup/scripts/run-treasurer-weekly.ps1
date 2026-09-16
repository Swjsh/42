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
. "$PSScriptRoot\_brain.ps1"   # GAMMA-STATION item 8: per-fire local brain (automation/state/brain-mode.json)

$task = "treasurer"

# Ensure treasury state dirs exist
$treasuryDir = Join-Path $projectRoot "analysis\treasury"
if (-not (Test-Path $treasuryDir)) { New-Item -ItemType Directory -Path $treasuryDir -Force | Out-Null }

Write-TaskLog -TaskName $task -Message "treasurer-weekly: START"

# Resolve the brain BEFORE building the prompt (not at the Invoke-Claude call site) so the
# human-readable brain stamp can be embedded in the prompt text itself -- analysis/treasury/
# {today}.md is written by the spawned agent per instruction 5 below, so the stamp has to
# travel IN the prompt.
$brainModel = Resolve-BrainModel "sonnet" -TaskName $task
$brainStamp = $env:GAMMA_BRAIN_STAMP
if (-not $brainStamp) { $brainStamp = "$brainModel (anthropic, stamp unavailable)" }

# Write prompt to temp file
$today = (Get-Date).ToString("yyyy-MM-dd")
$promptFile = Join-Path $env:TEMP "treasurer-prompt-$today.txt"
@"
Execute your weekly audit routine for $today. Fire is automatic (Gamma_TreasurerWeekly Sunday 16:00 ET).
Brain: $brainStamp

Your job (per .claude/agents/treasurer.md):
1. Pull both account balances via Alpaca MCP: safe-2 through the `alpaca` server, bold-2 through `alpaca_aggressive`. Account numbers, aliases and equity tiers come from automation/state/fleet/accounts.json (the source of truth) -- never from memory or this prompt.
2. Audit sizing math: per-trade risk %, daily kill-switch thresholds, account tier vs current equity
3. Check PDT awareness: trades remaining in rolling 5-day window
4. Review any account-tier transitions needed ($1K->$2K->$10K->$25K)
5. Write analysis/treasury/{today}.md with full audit -- include the line "Brain: $brainStamp" near the top, verbatim.
6. Write DRAFT params changes if needed (analysis/treasury/draft-params-changes.md) -- NEVER modify params*.json directly
7. Return the audit summary with any recommended changes.
"@ | Out-File -FilePath $promptFile -Encoding UTF8

# TREASURER-DEAD-ON-A-30-CENT-CAP (company audit, 2026-09-14 00:4x ET): every fire since at
# least 2026-08-30 died on the first request with "Error: Exceeded USD budget (0.3)" (see
# automation/state/logs/treasurer-2026-08-30/09-06/09-13.log: END exit=1 within ~20 s), so
# analysis/treasury/ never received a dated report -- and the wscript->pythonw chain returns
# 0 to Task Scheduler regardless, which hid it. The cap is now Invoke-Claude's own default
# (2.00: $0 on the local brain, at most ~$2/week of Max quota on the Claude fallback path),
# and the model resolves through _brain.ps1 exactly like run-analyst-eod.ps1 / run-conductor.ps1.
# First local-brain fire (2026-09-14 00:50 ET) hit Invoke-Claude's 240 s default wall clock
# mid tool-loop (exit=124, no report): the 27B at ~48 tok/s needs the room a Sonnet call does
# not. 540 s stays under run_ps1_hidden.py's own 600 s ceiling on the whole .ps1.
$exitCode = Invoke-Claude `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 2.00 `
    -Model $brainModel `
    -Effort "medium" `
    -TimeoutSec 540 `
    -AgentName "treasurer"

Remove-Item $promptFile -ErrorAction SilentlyContinue
Write-TaskLog -TaskName $task -Message "treasurer-weekly: END exit=$exitCode"
exit $exitCode
