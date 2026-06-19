#!/usr/bin/env pwsh
# preflight-gate.ps1 - ONE standing readiness check before any trading work.
#
# Chains the three pre-existing audits that the /insights report flagged as
# "exists but not unified", plus a key/timeframe sanity pass, and folds them
# into a SINGLE GREEN/YELLOW/RED verdict + JSON scorecard.
#
#   1. heartbeat-mcp-self-test  -> MCP servers reachable (TV CDP + alpaca proc + key loaded)
#   2. chart-data-verify        -> last closed SPY 5m bars agree across sources (no stale/wrong-TF data)
#   3. heartbeat-pulse-check    -> Gamma_Heartbeat scheduled task is actually firing
#
# Verdict = worst-of the three (RED dominates YELLOW dominates GREEN).
# Per CLAUDE.md OP-25 ("silent failure is the only true failure"): this gate
# turns the stale-401 + wrong-timeframe + dead-tick failure modes into a LOUD signal.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\preflight-gate.ps1"
#   & "C:\Users\jackw\Desktop\42\setup\scripts\preflight-gate.ps1" -Heal   # passes -Heal to sub-audits
#   & "C:\Users\jackw\Desktop\42\setup\scripts\preflight-gate.ps1" -Quiet
#
# Exit code: 0 for GREEN/YELLOW, 1 for RED (so callers can chain on $LASTEXITCODE).

param(
    [switch]$Heal,
    [switch]$Quiet,
    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Continue"
$ROOT     = "C:\Users\jackw\Desktop\42"
$SCRIPTS  = Join-Path $ROOT "setup\scripts"
$STATE    = Join-Path $ROOT "automation\state"
$OUT_JSON = Join-Path $STATE "preflight-gate-latest.json"
$RANK = @{ "GREEN" = 0; "YELLOW" = 1; "RED" = 2 }
$UNRANK = @{ 0 = "GREEN"; 1 = "YELLOW"; 2 = "RED" }

function Read-Verdict {
    param([string]$JsonPath, [string]$CheckName)
    if (-not (Test-Path $JsonPath)) {
        return @{ check = $CheckName; verdict = "RED"; reason = "no JSON written ($JsonPath missing) - audit did not complete" }
    }
    try {
        $j = Get-Content $JsonPath -Raw | ConvertFrom-Json
        $v = "$($j.verdict)".ToUpper()
        if (-not $RANK.ContainsKey($v)) { $v = "RED" }
        $reason = if ($j.reason) { "$($j.reason)" } else { "(no reason field)" }
        return @{ check = $CheckName; verdict = $v; reason = $reason }
    } catch {
        return @{ check = $CheckName; verdict = "RED"; reason = "unparseable JSON: $_" }
    }
}

$results = @()

# ---- 1. MCP self-test (live probe) ----
$mcpArgs = @("-File", (Join-Path $SCRIPTS "heartbeat-mcp-self-test.ps1"), "-Quiet")
if ($Heal) { $mcpArgs += "-Heal" }
& powershell -NoProfile -ExecutionPolicy Bypass @mcpArgs | Out-Null
$results += Read-Verdict (Join-Path $STATE "heartbeat-mcp-self-test-latest.json") "mcp-self-test"

# ---- 2. chart-data-verify (data freshness / correct timeframe) ----
# Verify yesterday's bars (today's may be mid-session / market closed).
$yday = (Get-Date $Date).AddDays(-1).ToString("yyyy-MM-dd")
Push-Location (Join-Path $ROOT "backtest")
& python -m autoresearch.chart_data_verify --date $yday --quiet 2>&1 | Out-Null
Pop-Location
$results += Read-Verdict (Join-Path $STATE "chart-data-verify-$yday.json") "chart-data-verify"

# ---- 3. heartbeat pulse (scheduled task firing) ----
$pulseArgs = @("-File", (Join-Path $SCRIPTS "heartbeat-pulse-check.ps1"), "-Date", $Date)
if ($Heal) { $pulseArgs += "-Heal" }
& powershell -NoProfile -ExecutionPolicy Bypass @pulseArgs | Out-Null
$results += Read-Verdict (Join-Path $STATE "heartbeat-pulse-check-$Date.json") "heartbeat-pulse"

# ---- Fold to worst-of ----
$worst = 0
foreach ($r in $results) { if ($RANK[$r.verdict] -gt $worst) { $worst = $RANK[$r.verdict] } }
$overall = $UNRANK[$worst]

$reds    = @($results | Where-Object { $_.verdict -eq "RED" }    | ForEach-Object { $_.check })
$yellows = @($results | Where-Object { $_.verdict -eq "YELLOW" } | ForEach-Object { $_.check })

$summary = switch ($overall) {
    "GREEN"  { "All 3 pre-flight checks GREEN. Cleared for trading work." }
    "YELLOW" { "Degraded but workable. YELLOW: $($yellows -join ', '). Proceed with caution." }
    "RED"    { "BLOCKED. RED: $($reds -join ', '). Do NOT start trading work until resolved." }
}

$payload = [ordered]@{
    skill    = "preflight-gate"
    run_at   = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    date     = $Date
    verdict  = $overall
    summary  = $summary
    checks   = $results
    healed   = [bool]$Heal
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $OUT_JSON -Encoding UTF8

if (-not $Quiet) {
    Write-Output "=== PRE-FLIGHT GATE: $overall ==="
    foreach ($r in $results) {
        Write-Output ("  [{0,-6}] {1,-18} {2}" -f $r.verdict, $r.check, $r.reason)
    }
    Write-Output ""
    Write-Output $summary
    Write-Output "JSON: $OUT_JSON"
}

if ($overall -eq "RED") { exit 1 } else { exit 0 }
