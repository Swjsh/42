#requires -Version 5.1
<#
.SYNOPSIS
  Daily MCP connection audit -- fires every day 18:30 ET via Gamma_McpDailyAudit.
  Round-trips Alpaca (Safe + Bold) /v2/account + /v2/clock, checks TradingView CDP
  port 9222 and the alpaca-mcp-server processes (both report-only). Read-only, $0.

.DESCRIPTION
  RETIRED 2026-09-03 (was an `Invoke-Claude` LLM fire against
  `automation/prompts/mcp-weekly-audit.md`, ~$0.10-0.30/fire): the free-model prompt
  wrote TWO false BLOCKERs into STATUS.md `## Known broken` in one night -- a RED at
  00:03 ET ("Alpaca Safe and Bold both 401 Unauthorized ... BLOCKER") and a YELLOW at
  07:48 ET ("404 (credential/account mismatch)") -- while a direct REST `/v2/account`
  call using the SAME `.mcp.json` keys returned 200/ACTIVE for both accounts the whole
  time, and the live engine (which trades via direct REST, never through MCP) never
  lost a tick. Per CLAUDE.md "deterministic > LLM on hot paths": a pure network
  round-trip probe cannot hallucinate a status code, so this now calls
  `setup/scripts/mcp_daily_audit.py` directly via the standard `Invoke-PythonHidden`
  (system python.exe, CREATE_NO_WINDOW -- OP-27 L41) instead of spawning an LLM.
  Guard: `backtest/tests/test_mcp_daily_audit_2026_09_03.py`.
#>
$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

# Source _shared.ps1 for Invoke-PythonHidden + Write-TaskLog
. "$PSScriptRoot\_shared.ps1"

$task = "mcp-daily-audit"
Write-TaskLog -TaskName $task -Message "mcp-daily-audit: START"

$scriptPath = Join-Path $projectRoot "setup\scripts\mcp_daily_audit.py"
$result = Invoke-PythonHidden -ScriptPath $scriptPath -TaskName $task -TimeoutSec 60
$exitCode = $result.ExitCode

Write-TaskLog -TaskName $task -Message "mcp-daily-audit: END exit=$exitCode -- $($result.Stdout)"
exit $exitCode
