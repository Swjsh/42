#requires -Version 5.1
<#
.SYNOPSIS
  Weekly MCP connection audit -- fires Sunday 18:30 ET via Gamma_McpWeeklyAudit.
  Round-trips Alpaca (Safe + Bold) + TradingView MCP TOOLS (not just the CDP port)
  to catch a hung-but-alive MCP bridge that Gamma_TvWatchdog cannot see. Read-only.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 for Invoke-Claude + Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "mcp-weekly-audit"
Write-TaskLog -TaskName $task -Message "mcp-weekly-audit: START"

$exitCode = Invoke-Claude `
    -PromptFile (Join-Path $projectRoot "automation\prompts\mcp-weekly-audit.md") `
    -TaskName $task `
    -MaxBudgetUsd 0.30 `
    -Model "haiku" `
    -Effort "low" `
    -TimeoutSec 240

Write-TaskLog -TaskName $task -Message "mcp-weekly-audit: END exit=$exitCode"
exit $exitCode
