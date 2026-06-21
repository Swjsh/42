#!/usr/bin/env pwsh
# connectivity-gate.ps1 - LAYER 1 (PROCESS) substrate for the connectivity-gate skill.
#
# This is the cheap, MCP-free first check. It does NOT make any TradingView or
# Alpaca MCP calls (those are LAYER 2, executed by the heartbeat/pilot via its MCP
# access - see .claude/skills/connectivity-gate/SKILL.md). This script only probes
# the process/port SUBSTRATE that must be alive before any functional round-trip can
# possibly succeed:
#
#   TV_CDP_PORT   - CDP port 9222 listening (TV reachable over DevTools protocol)
#   TV_PROCESS    - >=1 TradingView Desktop process alive
#   ALPACA_MCP    - >=1 alpaca-mcp-server process alive (Safe account server)
#
# It reuses the existing audited probes by invoking preflight-gate.ps1 (which chains
# heartbeat-mcp-self-test + chart-data-verify + heartbeat-pulse-check) and then
# re-expresses the result as a FLAT NODE LIST with stable node names + heal hints,
# so the skill's functional layer can append its nodes to the same list.
#
# Per CLAUDE.md OP-25 ("silent failure is the only true failure"): a failed substrate
# is a LOUD, named node - never a dead tick.
# Per OP-32 / L54: this gate fails CLOSED for trading (RED = no entry) but NEVER
# locks out J - it only reports; healing TV is gated on -Heal AND J-not-on-chart.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1"
#   & "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1" -Heal    # only if J NOT on the chart
#   & "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1" -Quiet
#   & "C:\Users\jackw\Desktop\42\setup\scripts\connectivity-gate.ps1" -ProcessOnly   # skip preflight sub-audits, raw port/proc only
#
# Exit code: 0 if all process nodes PASS (GREEN), 1 if any process node FAILS (RED).
# The skill's LAYER 2 functional nodes can still turn a process-GREEN into a
# functional-RED (e.g. stale TV data) - this script only owns the substrate verdict.

param(
    [switch]$Heal,
    [switch]$Quiet,
    [switch]$ProcessOnly,
    [string]$Date = (Get-Date -Format "yyyy-MM-dd")
)

$ErrorActionPreference = "Continue"
$ROOT     = "C:\Users\jackw\Desktop\42"
$SCRIPTS  = Join-Path $ROOT "setup\scripts"
$STATE    = Join-Path $ROOT "automation\state"
$OUT_JSON = Join-Path $STATE "connectivity-gate-latest.json"

# ---- raw process/port probes (same logic as heartbeat-mcp-self-test, inlined so
#      -ProcessOnly works without spawning a child PowerShell) ----
function Test-TvCdpPort {
    $cdpListening = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue
        if ($null -ne $conn -and $conn.State -contains "Listen") { $cdpListening = $true }
    } catch {}
    return $cdpListening
}

function Get-TvProcCount {
    $tvProcCount = 0
    try {
        $tvProcs = Get-Process | Where-Object { $_.ProcessName -like "*TradingView*" }
        $tvProcCount = if ($null -eq $tvProcs) { 0 } else { @($tvProcs).Count }
    } catch {}
    return $tvProcCount
}

function Get-AlpacaMcpProcCount {
    # alpaca-mcp-server runs as a uvx-launched (python|pythonw) process. Probe by
    # command-line substring via WMI - Get-Process misses console-less pythonw (L27).
    $count = 0
    try {
        $procs = Get-WmiObject Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
        $count = @($procs | Where-Object { $_.CommandLine -and $_.CommandLine -like "*alpaca-mcp*" }).Count
    } catch {}
    return $count
}

# ---- build the flat node list ----
$nodes = @()

function Add-Node {
    param(
        [string]$Name,
        [bool]$Pass,
        [string]$Layer,
        [string]$Detail,
        [string]$HealHint
    )
    $script:nodes += [ordered]@{
        node      = $Name
        layer     = $Layer
        status    = if ($Pass) { "PASS" } else { "FAIL" }
        detail    = $Detail
        heal_hint = $HealHint
    }
}

# Probe substrate once
$cdp   = Test-TvCdpPort
$tvN   = Get-TvProcCount
$alpN  = Get-AlpacaMcpProcCount

# Retry once after 5s if anything looks down (transient suppression, mirrors self-test)
$retried = $false
if (-not $cdp -or $tvN -eq 0 -or $alpN -eq 0) {
    Start-Sleep -Seconds 5
    $cdp  = Test-TvCdpPort
    $tvN  = Get-TvProcCount
    $alpN = Get-AlpacaMcpProcCount
    $retried = $true
}

# ---- optional TV heal (gated: only if -Heal AND caller has confirmed J not on chart) ----
# NOTE: this script CANNOT know whether J is on the chart. The skill instructs the
# caller (heartbeat/pilot) to pass -Heal ONLY when J-not-on-chart is established.
# A bare run (no -Heal) never touches TV - safe to call while J charts.
$tvHealAction = "no-op"
if ($Heal -and (-not $cdp -or $tvN -eq 0)) {
    $launcher = Join-Path $ROOT "setup\launch_tv_debug.ps1"
    if (Test-Path $launcher) {
        try {
            Get-Process | Where-Object { $_.ProcessName -like "*TradingView*" } | ForEach-Object {
                try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
            Start-Sleep -Seconds 3
            & $launcher 2>&1 | Out-Null
            Start-Sleep -Seconds 8
            $cdp = Test-TvCdpPort
            $tvN = Get-TvProcCount
            $tvHealAction = if ($cdp -and $tvN -gt 0) { "restarted-via-launch_tv_debug-CDP-now-up" } else { "restart-attempted-CDP-still-down" }
        } catch {
            $tvHealAction = "restart-failed: $($_.Exception.Message)"
        }
    } else {
        $tvHealAction = "launcher-script-missing-at-$launcher"
    }
}

Add-Node -Name "TV_CDP_PORT" -Pass $cdp -Layer "process" `
    -Detail "CDP port 9222 listening=$cdp (retried=$retried, heal=$tvHealAction)" `
    -HealHint "relaunch TV via setup/launch_tv_debug.ps1 - ONLY if J is NOT on the chart (OP-32: never lock J out)"

Add-Node -Name "TV_PROCESS" -Pass ($tvN -gt 0) -Layer "process" `
    -Detail "TradingView process count=$tvN" `
    -HealHint "relaunch TV via setup/launch_tv_debug.ps1 - ONLY if J is NOT on the chart"

Add-Node -Name "ALPACA_MCP" -Pass ($alpN -gt 0) -Layer "process" `
    -Detail "alpaca-mcp-server process count=$alpN" `
    -HealHint "CANNOT-AUTO-HEAL: needs J to restart alpaca-mcp with key validation (key fixes always require J)"

# ---- optional deeper substrate via preflight-gate (data-freshness + sched-task pulse) ----
# These are still PROCESS/INFRA layer (no MCP round-trip), but they spawn child
# PowerShell + a python data-verify. -ProcessOnly skips them for the fastest path.
if (-not $ProcessOnly) {
    $pgArgs = @("-File", (Join-Path $SCRIPTS "preflight-gate.ps1"), "-Quiet", "-Date", $Date)
    if ($Heal) { $pgArgs += "-Heal" }
    & powershell -NoProfile -ExecutionPolicy Bypass @pgArgs | Out-Null
    $pgJson = Join-Path $STATE "preflight-gate-latest.json"
    if (Test-Path $pgJson) {
        try {
            $pg = Get-Content $pgJson -Raw | ConvertFrom-Json
            $pgVerdict = "$($pg.verdict)".ToUpper()
            # preflight-gate RED -> a hard substrate node fails; YELLOW -> advisory (still PASS at substrate)
            Add-Node -Name "PREFLIGHT_SUBSTRATE" -Pass ($pgVerdict -ne "RED") -Layer "process" `
                -Detail "preflight-gate verdict=$pgVerdict :: $($pg.summary)" `
                -HealHint "inspect preflight-gate-latest.json (sub-checks: mcp-self-test / chart-data-verify / heartbeat-pulse); run preflight-gate.ps1 -Heal"
        } catch {
            Add-Node -Name "PREFLIGHT_SUBSTRATE" -Pass $false -Layer "process" `
                -Detail "preflight-gate JSON unparseable: $_" `
                -HealHint "re-run setup/scripts/preflight-gate.ps1 manually and read its stdout"
        }
    } else {
        Add-Node -Name "PREFLIGHT_SUBSTRATE" -Pass $false -Layer "process" `
            -Detail "preflight-gate wrote no JSON - sub-audit did not complete" `
            -HealHint "re-run setup/scripts/preflight-gate.ps1 manually and read its stdout"
    }
}

# ---- fold to a process-layer verdict ----
$failed = @($nodes | Where-Object { $_.status -eq "FAIL" })
$verdict = if ($failed.Count -eq 0) { "GREEN" } else { "RED" }
$failedNames = @($failed | ForEach-Object { $_.node })

$summary = if ($verdict -eq "GREEN") {
    "PROCESS LAYER GREEN. Substrate alive (TV CDP + TV proc + alpaca-mcp). Proceed to LAYER 2 functional MCP round-trips (see SKILL.md)."
} else {
    "PROCESS LAYER RED. Failed node(s): $($failedNames -join ', '). Do NOT trade. LAYER 2 functional checks would fail anyway - fix the substrate first."
}

$payload = [ordered]@{
    skill            = "connectivity-gate"
    layer            = "process"
    run_at           = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
    date             = $Date
    verdict          = $verdict
    failed_nodes     = $failedNames
    summary          = $summary
    nodes            = $nodes
    healed           = [bool]$Heal
    tv_heal_action   = $tvHealAction
    note             = "Process layer only. The FUNCTIONAL layer (TV read freshness, alpaca clock/account/positions, VIX) is executed by the heartbeat/pilot via MCP per the connectivity-gate SKILL.md - NOT by this script."
}
$payload | ConvertTo-Json -Depth 6 | Set-Content -Path $OUT_JSON -Encoding UTF8

if (-not $Quiet) {
    Write-Output "=== CONNECTIVITY-GATE (LAYER 1 / PROCESS): $verdict ==="
    foreach ($n in $nodes) {
        Write-Output ("  [{0,-4}] {1,-20} {2}" -f $n.status, $n.node, $n.detail)
        if ($n.status -eq "FAIL") {
            Write-Output ("         heal: {0}" -f $n.heal_hint)
        }
    }
    Write-Output ""
    Write-Output $summary
    Write-Output "JSON: $OUT_JSON"
    Write-Output "NEXT: run LAYER 2 functional MCP round-trips per .claude/skills/connectivity-gate/SKILL.md"
}

if ($verdict -eq "RED") { exit 1 } else { exit 0 }
