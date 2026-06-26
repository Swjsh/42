# freshness-watchdog.ps1 - make staleness LOUD (Deep-Review finding #1).
#
# The autonomous loop's worst failure mode is silent: premarket/EOD/heartbeat
# stop running and nothing says so. This asserts the freshness of the key state
# files and writes ONE status line + a machine-readable flag. Wire it into Task
# Scheduler (e.g. hourly) and/or call it at the top of each wake fire.
#
# FAIL-OPEN by design (OP-32 scar): on ANY error it reports the error and exits 0.
# It NEVER blocks, kills, or gates anything. PowerShell 5.1 compatible (ASCII only).

$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$state = Join-Path $repo "automation\state"
$outFlag = Join-Path $state "freshness.json"
$today = (Get-Date).Date

function Get-AgeHours($path) {
    if (-not (Test-Path $path)) { return $null }
    $lw = (Get-Item $path).LastWriteTime
    return [math]::Round(((Get-Date) - $lw).TotalHours, 1)
}

function Read-Json($path) {
    if (-not (Test-Path $path)) { return $null }
    try { return (Get-Content $path -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { return $null }
}

$problems = New-Object System.Collections.ArrayList

try {
    # Is it a trading day? (Mon-Fri). On weekends, staleness is expected - report INFO only.
    $dow = $today.DayOfWeek.value__   # 0=Sun .. 6=Sat
    $isTradingDay = ($dow -ge 1 -and $dow -le 5)

    # 1. Premarket ran today (circuit-breaker re-armed each premarket).
    $cb = Read-Json (Join-Path $state "circuit-breaker.json")
    if ($cb -and $cb.last_reset) {
        $resetDate = ([datetime]$cb.last_reset).Date
        if ($isTradingDay -and $resetDate -lt $today) {
            [void]$problems.Add("premarket stale: circuit-breaker.last_reset $($resetDate.ToString('yyyy-MM-dd')) < today")
        }
    } else {
        [void]$problems.Add("circuit-breaker.json missing or unreadable")
    }

    # 2. Decisions written within ~1 trading day (skip weekends).
    $decAge = Get-AgeHours (Join-Path $state "decisions.jsonl")
    if ($isTradingDay -and $decAge -ne $null -and $decAge -gt 30) {
        [void]$problems.Add("decisions.jsonl stale: ${decAge}h old")
    }

    # 3. EOD aggregates refreshing (setup-performance feeds the outer loop).
    foreach ($f in @("setup-performance.json", "equity-curve.json")) {
        $p = Join-Path $state $f
        if (-not (Test-Path $p)) { [void]$problems.Add("$f MISSING (EOD outer-loop input)") }
    }

    # 4. params.json internal consistency + cross-account rule_version (C3 guard).
    $params = Read-Json (Join-Path $state "params.json")
    if (-not $params) {
        [void]$problems.Add("params.json missing or invalid JSON")
    } else {
        if (-not $params.rule_version) { [void]$problems.Add("params.json has no rule_version") }
        # exits pinned to CURRENT ratified v15.3 doctrine (synced 2026-06-21 -- the prior
        # 2026-06-14 pins tp1=0.5/bear=-0.20 were stale: Rank-31 set tp1_qty_fraction=0.667
        # (2026-06-16) and chart-stop-primary set premium_stop_pct_bear=-0.50 (2026-06-18),
        # both ratified with scorecards. params.json is canonical -- bump these on next ratify.
        if ($params.tp1_qty_fraction -ne 0.667) { [void]$problems.Add("params.tp1_qty_fraction=$($params.tp1_qty_fraction) (expected 0.667)") }
        if ($params.runner_max_premium_pct -ne 2.5) { [void]$problems.Add("params.runner_max_premium_pct=$($params.runner_max_premium_pct) (expected 2.5)") }
        if ($params.premium_stop_pct_bear -ne -0.5) { [void]$problems.Add("params.premium_stop_pct_bear=$($params.premium_stop_pct_bear) (expected -0.5)") }
    }
    $safe = Read-Json (Join-Path $state "params_safe.json")
    $bold = Read-Json (Join-Path $state "aggressive\params.json")
    if ($safe -and $bold -and $safe.rule_version -and $bold.rule_version -and ($safe.rule_version -ne $bold.rule_version)) {
        [void]$problems.Add("account rule_version mismatch: safe=$($safe.rule_version) bold=$($bold.rule_version)")
    }

    $health = if ($problems.Count -eq 0) { "GREEN" } else { "RED" }
    $result = [ordered]@{
        checked_at = (Get-Date).ToString("o")
        trading_day = $isTradingDay
        health = $health
        problems = @($problems)
        watchdog = "ok"
    }
    $result | ConvertTo-Json -Depth 5 | Set-Content $outFlag -Encoding UTF8

    if ($health -eq "RED") {
        Write-Host "FRESHNESS: RED - $($problems.Count) problem(s):" -ForegroundColor Red
        $problems | ForEach-Object { Write-Host "  - $_" }
    } else {
        Write-Host "FRESHNESS: GREEN (all checks passed)" -ForegroundColor Green
    }
}
catch {
    # FAIL-OPEN: record the watchdog's own error, never block.
    $err = [ordered]@{ checked_at = (Get-Date).ToString("o"); health = "UNKNOWN"; watchdog = "error: $($_.Exception.Message)" }
    try { $err | ConvertTo-Json | Set-Content $outFlag -Encoding UTF8 } catch {}
    Write-Host "FRESHNESS watchdog error (fail-open, not blocking): $($_.Exception.Message)" -ForegroundColor Yellow
}
exit 0
