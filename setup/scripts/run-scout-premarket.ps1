#requires -Version 5.1
<#
.SYNOPSIS
  Daily Scout invocation -- fires 05:30 ET via Gamma_ScoutPremarket.
  Runs Scout persona (macro/news/calendar scan) and writes scout_output.json
  for Premarket (08:30 ET) to consume.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 to get $Global:ClaudeExe (full path) + Invoke-Claude + Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "scout"

# Ensure scout state dir exists
$scoutStateDir = Join-Path $projectRoot "automation\scout\state"
if (-not (Test-Path $scoutStateDir)) { New-Item -ItemType Directory -Path $scoutStateDir -Force | Out-Null }

Write-TaskLog -TaskName $task -Message "scout-premarket: START"

# Write prompt to temp file (Invoke-Claude reads from file)
$today = (Get-Date).ToString("yyyy-MM-dd")
$promptFile = Join-Path $env:TEMP "scout-prompt-$today.txt"
@"
Execute your daily routine for $today. Fire is automatic (Gamma_ScoutPremarket task at 05:30 ET).

Your job (per .claude/agents/scout.md):
1. Scan macro calendar, news headlines, geopolitical events
2. Write scout_output.json with catalyst summary + bias hypothesis
3. Append scout-log.jsonl entry
4. If HIGH catalyst within 3h of open: append STATUS.md WARN line
5. Return the standard report confirming what you wrote and where.
"@ | Out-File -FilePath $promptFile -Encoding UTF8

$exitCode = Invoke-Claude `
    -PromptFile $promptFile `
    -TaskName $task `
    -MaxBudgetUsd 0.50 `
    -Model "sonnet" `
    -Effort "medium" `
    -AgentName "scout"

Remove-Item $promptFile -ErrorAction SilentlyContinue
Write-TaskLog -TaskName $task -Message "scout-premarket: END exit=$exitCode"
exit $exitCode
