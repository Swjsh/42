#!/usr/bin/env pwsh
# heartbeat-mcp-self-test.ps1 — verify TradingView + Alpaca MCP servers reachable from heartbeat's perspective.
#
# AUDIT: probe (a) TV CDP port 9222 listening, (b) TV process count > 0, (c) alpaca-mcp-server process alive.
# DIAGNOSE: GREEN if both probes pass; YELLOW if one transient (1 retry recovers); RED if either fails after retry.
# HEAL: TV-side = restart via launch_tv_debug.ps1 (idempotent — kills existing TV processes first);
#       Alpaca-side = NO auto-heal (key validation requires J).
# REPORT: stdout + JSON at automation/state/heartbeat-mcp-self-test-{ts}.json.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-mcp-self-test.ps1"
#   & "C:\Users\jackw\Desktop\42\setup\scripts\heartbeat-mcp-self-test.ps1" -Heal
#

param(
    [switch]$Heal,
    [switch]$Quiet
)

$ErrorActionPreference = "Continue"
$ROOT = "C:\Users\jackw\Desktop\42"
$TS   = Get-Date -Format "yyyy-MM-ddTHH-mm-ss"
$OUT_JSON = Join-Path $ROOT "automation\state\heartbeat-mcp-self-test-latest.json"

function Write-Result {
    param([string]$Verdict, [hashtable]$Data)
    $payload = @{
        skill   = "heartbeat-mcp-self-test"
        run_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss")
        verdict = $Verdict
    } + $Data
    $payload | ConvertTo-Json -Depth 6 | Out-File -FilePath $OUT_JSON -Encoding utf8 -Force
    if (-not $Quiet) {
        Write-Output "=== heartbeat-mcp-self-test $TS ==="
        Write-Output "VERDICT: $Verdict"
        foreach ($k in $Data.Keys) {
            Write-Output ("  {0}: {1}" -f $k, $Data[$k])
        }
        Write-Output ("  output: $OUT_JSON")
    }
}

# ---- TV PROBE ----
function Test-TvCdp {
    $cdpListening = $false
    try {
        $conn = Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue
        if ($null -ne $conn -and $conn.State -contains "Listen") {
            $cdpListening = $true
        }
    } catch {}

    $tvProcCount = 0
    try {
        $tvProcs = Get-Process | Where-Object { $_.ProcessName -like "*TradingView*" }
        $tvProcCount = if ($null -eq $tvProcs) { 0 } else { @($tvProcs).Count }
    } catch {}

    return [PSCustomObject]@{
        cdp_listening = $cdpListening
        tv_proc_count = $tvProcCount
        ok            = ($cdpListening -and $tvProcCount -gt 0)
    }
}

# ---- ALPACA PROBE ----
# alpaca-mcp-server runs as a uvx-launched python process. Probe by command-line substring.
function Test-AlpacaMcp {
    $alpacaProcCount = 0
    try {
        $procs = Get-WmiObject Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" -ErrorAction SilentlyContinue
        $alpacaProcs = @($procs | Where-Object { $_.CommandLine -and $_.CommandLine -like "*alpaca-mcp*" })
        $alpacaProcCount = $alpacaProcs.Count
    } catch {}

    return [PSCustomObject]@{
        alpaca_proc_count = $alpacaProcCount
        ok                = ($alpacaProcCount -gt 0)
    }
}

# ---- 1. AUDIT ----
$tv1 = Test-TvCdp
$alp1 = Test-AlpacaMcp

# Retry once with 5s pause if either failed (transient suppression)
$retried = $false
if (-not $tv1.ok -or -not $alp1.ok) {
    Start-Sleep -Seconds 5
    $tv2  = Test-TvCdp
    $alp2 = Test-AlpacaMcp
    $retried = $true
} else {
    $tv2 = $tv1
    $alp2 = $alp1
}

# ---- 2. DIAGNOSE ----
$tvOk    = $tv2.ok
$alpacaOk = $alp2.ok
$verdict = "GREEN"
$reason  = "tv-and-alpaca-mcp-reachable"

if (-not $tvOk -and -not $alpacaOk) {
    $verdict = "RED"
    $reason  = "BOTH-tv-cdp-and-alpaca-mcp-down"
} elseif (-not $tvOk) {
    $verdict = "RED"
    $reason  = "tv-cdp-port-9222-not-listening (cdp=$($tv2.cdp_listening) procs=$($tv2.tv_proc_count))"
} elseif (-not $alpacaOk) {
    $verdict = "RED"
    $reason  = "alpaca-mcp-process-not-found"
} elseif ($retried) {
    $verdict = "YELLOW"
    $reason  = "transient-recovered-on-retry"
}

# ---- 3. HEAL ----
$tvHealAction      = "no-op"
$alpacaHealAction  = "no-op"

if ($Heal -and -not $tvOk) {
    $launcher = Join-Path $ROOT "setup\launch_tv_debug.ps1"
    if (Test-Path $launcher) {
        try {
            # Kill existing TV first (idempotent restart)
            Get-Process | Where-Object { $_.ProcessName -like "*TradingView*" } | ForEach-Object {
                try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
            }
            Start-Sleep -Seconds 3
            & $launcher 2>&1 | Out-Null
            Start-Sleep -Seconds 8
            $tv3 = Test-TvCdp
            if ($tv3.ok) {
                $tvHealAction = "restarted-via-launch_tv_debug-CDP-now-up"
                $verdict = "YELLOW"  # downgraded since heal succeeded
                $reason  = "tv-cdp-was-down-but-heal-succeeded"
            } else {
                $tvHealAction = "restart-attempted-CDP-still-down (cdp=$($tv3.cdp_listening) procs=$($tv3.tv_proc_count))"
            }
        } catch {
            $tvHealAction = "restart-failed: $($_.Exception.Message)"
        }
    } else {
        $tvHealAction = "launcher-script-missing-at-$launcher"
    }
}

if ($Heal -and -not $alpacaOk) {
    $alpacaHealAction = "CANNOT-AUTO-HEAL-alpaca-mcp-needs-J-to-restart-with-key-validation"
}

# Discord alert
if ($Heal -and $verdict -eq "RED") {
    $alertMsg = "[heartbeat-mcp-self-test] RED :: $reason :: tv_heal=$tvHealAction :: alpaca_heal=$alpacaHealAction"
    try {
        Add-Content -Path (Join-Path $ROOT "automation\state\discord-outbox.jsonl") -Value (
            @{ ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"); kind = "ALERT"; severity = "RED"; text = $alertMsg } | ConvertTo-Json -Compress
        )
    } catch {}
}

# ---- 5. REPORT ----
Write-Result -Verdict $verdict -Data @{
    reason             = $reason
    tv_cdp_listening   = $tv2.cdp_listening
    tv_proc_count      = $tv2.tv_proc_count
    alpaca_proc_count  = $alp2.alpaca_proc_count
    retried            = $retried
    tv_heal_action     = $tvHealAction
    alpaca_heal_action = $alpacaHealAction
}

if ($verdict -eq "RED") { exit 1 } else { exit 0 }
