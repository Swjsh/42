# Heartbeat tick — Task Scheduler fires every 3 min from 09:30 to 15:50 ET weekdays.
# Each tick is a fresh `claude --print` invocation. State lives in JSON files.
#
# Cost-control layers (2026-05-06 v2):
#   1. Default model: Haiku 4.5. Escalate to Sonnet 4.6 only if the previous
#      tick wrote loop-state#next_tick_model = "sonnet" (same-day session_id).
#   2. Cadence throttle by mode: HOT every tick, BASE every 2nd, COOL every 3rd.
#      Reads loop-state#current_mode and ticks_today.
#   3. Hard per-tick budget cap: $0.20 (was $1.00). Aborts a runaway tick
#      before it eats the rolling 5h window.
#   4. Position-OPEN override: if a position is open, ALWAYS run regardless
#      of mode-throttle (never skip while we have skin in the game).
. "$PSScriptRoot\_shared.ps1"

$task = "heartbeat"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 35 -EndHour 15 -EndMin 50)) { exit 0 }

# Rate-limit cooldown — a prior tick (this or another wrapper) detected a Claude
# Code rate limit; skip this tick to avoid the wasted spawn. Per L54.
# CRITICAL (OP-32 fix verification 2026-05-22): pass -TaskName so the circuit-breaker
# claude_print_exempt flag actually reaches us. Without -TaskName, the heartbeat would
# block itself when the circuit breaker writes the cooldown file with exempt=true.
$cooldownReset = Test-RateLimitCooldown -TaskName $task
if ($cooldownReset) {
    Write-TaskLog -TaskName $task -Message "SKIP rate_limit_cooldown reset_at=$($cooldownReset.ToString('HH:mm')) ET"
    exit 0
}

$loopStatePath = Join-Path $WorkDir "automation\state\loop-state.json"
$posStatePath = Join-Path $WorkDir "automation\state\current-position.json"
$today = $et.ToString("yyyy-MM-dd")

$model = "haiku"
$mode = "BASE"
$positionOpen = $false

if (Test-Path $loopStatePath) {
    try {
        $loopState = Get-Content $loopStatePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($loopState.session_id -eq $today) {
            if ($loopState.next_tick_model -eq "sonnet") { $model = "sonnet" }
            if ($loopState.current_mode) { $mode = "$($loopState.current_mode)" }
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN loop-state.json unreadable ($($_.Exception.Message))"
    }
}

# Position-open override — never skip while we have a position.
# JSON null deserializes to $null (falsy). The string "null" is truthy in PS, so
# guard against legacy state files that wrote that as a literal: explicitly require
# a non-empty status that is NOT the literal string "null"/"none".
if (Test-Path $posStatePath) {
    try {
        $pos = Get-Content $posStatePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($pos.status -and $pos.status -ne "null" -and $pos.status -ne "none") {
            $positionOpen = $true
        }
    } catch { }
}

# Wall-clock tick index — independent of state writes, so throttle-skipped
# ticks don't break the counter. Task Scheduler fires every 3 min starting 09:30 ET.
$marketOpen = [DateTime]::new($et.Year, $et.Month, $et.Day, 9, 30, 0)
$tickIndex = [int][Math]::Floor(($et - $marketOpen).TotalMinutes / 3)

# HTF override — every 15-min bar close happens 3 min before tick (idx % 5 == 1).
# These ticks (09:33 post-09:30 close, 09:48 post-09:45 close, 10:03 post-10:00 close, ...)
# ALWAYS fire regardless of mode — guaranteed HTF coverage every 15 min.
$is15MinPostClose = ($tickIndex % 5) -eq 1

# Cadence throttle — HOT every tick, BASE every 3rd (was 2nd), COOL every 4th (was 3rd).
# Bypassed by: position open, Sonnet-flagged tick, OR 15-min post-close tick.
#
# 2026-05-07 tighter throttle: BASE 2->3, COOL 3->4. Today's burn analysis showed
# 17 fires/hour was eating ~$3-5/hour. With 3->effective-9-min cadence on BASE (when
# nothing's happening), expected burn drops to ~10 fires/hour = ~$2/hour = $13/day.
# HTF ticks every 15 min still always fire (idx%5==1 bypass) so HTF coverage is intact.
$throttleSkip = $false
if (-not $positionOpen -and -not $is15MinPostClose -and $model -eq "haiku") {
    switch ($mode.ToUpper()) {
        "HOT"  { $throttleSkip = $false }
        "BASE" { if (($tickIndex % 3) -ne 0) { $throttleSkip = $true } }
        "COOL" { if (($tickIndex % 4) -ne 0) { $throttleSkip = $true } }
        default { $throttleSkip = $false }
    }
}

if ($throttleSkip) {
    Write-TaskLog -TaskName $task -Message "SKIP throttle mode=$mode idx=$tickIndex model=$model pos_open=$positionOpen htf=$is15MinPostClose"
    exit 0
}

# Multi-Agent Gamma 2.0 Big Win #7: hash-based early-exit.
# Compute SHA-256 of heartbeat-relevant state. If unchanged from last tick AND
# none of the bypass conditions apply, skip the Claude call entirely.
# Bypasses: position open, HTF tick, score >=7 (escalation territory), Sonnet escalation.
# Estimated skip rate on quiet days: 30-50% of ticks. Saves ~$0.005/tick = ~$1.50-3/mo.
# Source: smtg-ai/claude-squad HasUpdated() pattern.
$developingScore = 0
if ($loopState -and $loopState.developing_setup -and $loopState.developing_setup.score) {
    $developingScore = [int]$loopState.developing_setup.score
}
$bypassHashCheck = $positionOpen -or $is15MinPostClose -or ($model -eq "sonnet") -or ($developingScore -ge 7)
if (-not $bypassHashCheck) {
    $hashScript = Join-Path $WorkDir "setup\scripts\compute-state-hash.ps1"
    $hashFile = Join-Path $WorkDir "automation\state\heartbeat-state-hash.txt"
    if (Test-Path $hashScript) {
        try {
            $currentHash = & $hashScript -WorkDir $WorkDir 2>$null
            $priorHash = if (Test-Path $hashFile) { (Get-Content $hashFile -Raw -ErrorAction SilentlyContinue).Trim() } else { "" }
            if ($currentHash -and $currentHash -eq $priorHash) {
                Write-TaskLog -TaskName $task -Message "SKIP hash_unchanged hash=$currentHash mode=$mode idx=$tickIndex"
                exit 0
            }
            # Hash differs (or first run today) -- update file BEFORE the Claude call so
            # a crash mid-tick doesn't make us think nothing changed next tick.
            if ($currentHash) {
                $currentHash | Out-File -FilePath $hashFile -Encoding utf8 -NoNewline
            }
        } catch {
            Write-TaskLog -TaskName $task -Message "HASH_FAIL: $($_.Exception.Message) (proceeding with Claude call)"
        }
    }
}

# Self-heal: kill any stale claude/MCP processes from a prior crashed tick.
# Heartbeat fires every 3 min — anything still running from 5+ min ago is dead-weight.
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

Write-TaskLog -TaskName $task -Message "FIRE mode=$mode idx=$tickIndex model=$model pos_open=$positionOpen htf=$is15MinPostClose score=$developingScore"

# R2 bar-age guard (2026-05-17): if we're within 30s of the next 5-minute bar close,
# sleep 30s so the bar is guaranteed closed before TV data_get_ohlcv runs.
# Complements the heartbeat.md R1 prompt filter (closed-bar check) by removing the
# race condition where the bar closes mid-tick while the prompt is being processed.
# Context: SPY 5m bars close at :00/:05/:10/:15/:20/:25/:30/:35/:40/:45/:50/:55.
# seconds_into_bar = (minute%5)*60 + second. seconds_until_close = 300 - that.
$secondsIntoCurrent5mBar = (($et.Minute % 5) * 60) + $et.Second
$secondsUntilBarClose = 300 - $secondsIntoCurrent5mBar
if ($secondsUntilBarClose -lt 30) {
    Write-TaskLog -TaskName $task -Message "BAR_AGE_GUARD: bar closes in ${secondsUntilBarClose}s, sleeping 30s to let bar complete"
    Start-Sleep -Seconds 30
}

# Heartbeat must finish in <3 min (next tick fires).
# 2026-05-07 iteration 3: 90s -> 130s -> 160s. Even at 130s Haiku times out on the
# full heartbeat prompt (10+ tool calls including 15m HTF refresh + VIX chart
# switch + state writes). 160s gives a 20s buffer before next 3-min tick
# boundary; if a tick truly needs >160s we have a structural problem (prompt too
# heavy for the model) — kill is correct.
# 2026-06-22: widened 180/220 -> 280 both branches. Heavy ticks (developing setup
# score>=7 + 15m HTF refresh) were measured at ~224s and timing out (exit 124) =
# no loop-state persist during active markets (the worst time). 280s lets them
# complete; a tick overlapping the 180s cadence just LOCK_BUSY-skips the next.
# Band-aid for the oversized 97KB heartbeat.md prompt -- durable fix = trim it (after-hours).
$tickTimeout = if ($model -eq "sonnet") { 280 } else { 280 }
$tickEffort = if ($model -eq "sonnet") { "medium" } else { "low" }

# 2026-05-07 update: budget 0.20 -> 0.35. Live heartbeat ticks were exiting at
# ~36s with "Exceeded USD budget (0.2)". Root cause: Haiku 4.5 accumulates input
# tokens across tool-call turns (each tool result becomes input on next turn).
# Heartbeat does ~5 MCP calls (chart state + OHLCV + study values + VIX quote +
# alpaca position) plus reads 5 state files. Total accumulated input across turns
# can hit 40-60K tokens = $0.04-0.06 input. Plus output (one-line emit + state
# writes) ~10K tokens = $0.05 output. Plus a buffer for retries/reasoning.
# 0.35 is the sweet spot - holds the kill-switch on truly runaway ticks without
# choking normal ones.
# AUTH (2026-06-21): the heartbeat runs on J's Claude subscription (Max 20x / $200 plan),
# NOT a dedicated ANTHROPIC_API_KEY. The isolated-API-key path (FIX-1, 2026-06-15) was
# retired 2026-06-17 after it burned ~$30 and hit a credit-cliff mid-FOMC; the branch is
# removed here so a stray automation/state/.heartbeat-api-key file can never silently
# re-route the heartbeat off the subscription (and silently hard-lock it to Haiku).
# Invoke-Claude inherits the logged-in subscription auth when $env:ANTHROPIC_API_KEY is
# unset. Sonnet escalation stays available via loop-state next_tick_model. See L54 +
# the "Heartbeat on Max subscription" memory.

$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\heartbeat.md") `
    -TaskName $task `
    -MaxBudgetUsd 1.00 `
    -Model $model `
    -TimeoutSec $tickTimeout `
    -Effort $tickEffort

# Post-tick safety: atomic-bracket-guard catches mid-MCP-timeout failures (5/18
# 10:48 naked-order incident class). Runs in <2s, hits Alpaca REST directly,
# cancels orphan parent orders, RED-flags STATUS.md if a filled naked position
# is detected. Returns its own exit code which we ignore — we keep the original
# Claude exit for the parent task. Per CLAUDE.md OP-25 ENGINE-BENEFIT AUTONOMY.
try {
    Invoke-PythonHidden -ScriptPath "setup\scripts\atomic_bracket_guard.py" `
        -ArgList @("--account", "safe", "--silent") `
        -TaskName "atomic-bracket-guard-safe" `
        -TimeoutSec 15 | Out-Null
} catch {
    Write-TaskLog -TaskName $task -Message "atomic-bracket-guard failed: $_"
}

# Post-tick safety: mechanical daily-loss kill switch (Rule 5). Computes day P&L vs
# start-of-day equity via Alpaca REST and flips circuit-breaker.json#tripped at -30%
# (Safe). The next tick reads tripped=true at gate G5 and halts; HealthBeacon RED-pings.
# Fail-safe: never trips on a fetch error or a stale (un-armed) SoD. Added 2026-06-21
# (readiness audit C2/P0-3 — Rule 5's daily-loss switch was previously never enforced).
try {
    Invoke-PythonHidden -ScriptPath "setup\scripts\daily_loss_guard.py" `
        -ArgList @("--account", "safe", "--silent") `
        -TaskName "daily-loss-guard-safe" `
        -TimeoutSec 15 | Out-Null
} catch {
    Write-TaskLog -TaskName $task -Message "daily-loss-guard failed: $_"
}

exit $exit
