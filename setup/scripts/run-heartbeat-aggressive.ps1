# Aggressive heartbeat tick — same 3-min schedule as safe heartbeat.
# Runs the second paper account (mcp__alpaca_aggressive__) with wider stops,
# relaxed time gates, and larger sizing. State in automation/state/aggressive/.
#
# Cost-control: same Haiku/Sonnet escalation and HOT/BASE/COOL cadence as safe.
# Budget cap: $0.50/tick (same as safe — aggressive prompts are similar token size).
. "$PSScriptRoot\_shared.ps1"

$task = "heartbeat_aggressive"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }
# Aggressive entry gate is 09:40, but we still start the script at 09:35 so it
# can run skip-gates and stale checks even before the first valid entry window.
if (-not (Test-MarketHours -Et $et -StartHour 9 -StartMin 35 -EndHour 15 -EndMin 50)) { exit 0 }

# Rate-limit cooldown — a prior tick (this or another wrapper) detected a Claude
# Code rate limit; skip this tick to avoid the wasted spawn. Per L54.
# CRITICAL (OP-32 fix verification 2026-05-22): pass -TaskName so the circuit-breaker
# claude_print_exempt flag actually reaches us. Without -TaskName, heartbeat blocks itself.
$cooldownReset = Test-RateLimitCooldown -TaskName $task
if ($cooldownReset) {
    Write-TaskLog -TaskName $task -Message "SKIP rate_limit_cooldown reset_at=$($cooldownReset.ToString('HH:mm')) ET"
    exit 0
}

# Aggressive-specific state paths
# NOTE (2026-05-18 dual-account redesign): Bold position state moved from
# automation\state\aggressive\current-position.json → automation\state\current-position-bold.json.
# Loop state stays in aggressive\ for now (written by aggressive/heartbeat.md).
$loopStatePath  = Join-Path $WorkDir "automation\state\aggressive\loop-state.json"
$posStatePath   = Join-Path $WorkDir "automation\state\current-position-bold.json"
$today = $et.ToString("yyyy-MM-dd")

$model        = "haiku"
$mode         = "BASE"
$positionOpen = $false

if (Test-Path $loopStatePath) {
    try {
        $loopState = Get-Content $loopStatePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($loopState.session_id -eq $today) {
            if ($loopState.next_tick_model -eq "sonnet") { $model = "sonnet" }
            if ($loopState.current_mode) { $mode = "$($loopState.current_mode)" }
        }
    } catch {
        Write-TaskLog -TaskName $task -Message "WARN loop-state.json (aggressive) unreadable ($($_.Exception.Message))"
    }
}

# Position-open override — never skip while we have a live aggressive position.
if (Test-Path $posStatePath) {
    try {
        $pos = Get-Content $posStatePath -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        if ($pos.status -and $pos.status -ne "null" -and $pos.status -ne "none") {
            $positionOpen = $true
        }
    } catch { }
}

# Wall-clock tick index — same 3-min cadence as safe heartbeat.
$marketOpen = [DateTime]::new($et.Year, $et.Month, $et.Day, 9, 30, 0)
$tickIndex  = [int][Math]::Floor(($et - $marketOpen).TotalMinutes / 3)

# HTF override — every 15-min bar close (idx % 5 == 1) always fires.
$is15MinPostClose = ($tickIndex % 5) -eq 1

# Cadence throttle — HOT every tick, BASE every 3rd, COOL every 4th.
# Bypassed by: position open, Sonnet-flagged tick, 15-min post-close tick.
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

# Self-heal: kill any stale claude/MCP processes from a prior crashed aggressive tick.
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

Write-TaskLog -TaskName $task -Message "FIRE mode=$mode idx=$tickIndex model=$model pos_open=$positionOpen htf=$is15MinPostClose"

# R2 bar-age guard: if within 30s of the next 5m bar close, sleep 30s (same as safe heartbeat).
$secondsIntoCurrent5mBar = (($et.Minute % 5) * 60) + $et.Second
$secondsUntilBarClose = 300 - $secondsIntoCurrent5mBar
if ($secondsUntilBarClose -lt 30) {
    Write-TaskLog -TaskName $task -Message "BAR_AGE_GUARD: bar closes in ${secondsUntilBarClose}s, sleeping 30s"
    Start-Sleep -Seconds 30
}

$tickTimeout = if ($model -eq "sonnet") { 180 } else { 220 }
$tickEffort  = if ($model -eq "sonnet") { "medium" } else { "low" }

# FIX 1 (2026-06-15): Isolated heartbeat API key — same as safe heartbeat.
# Bold uses a separate key file at automation/state/.heartbeat-api-key-bold
# (can be same key as safe, just kept separate for future independent rotation).
# Falls back to Max plan key if file absent.
$heartbeatKeyPath = Join-Path $WorkDir "automation\state\.heartbeat-api-key-bold"
$heartbeatKeyPathShared = Join-Path $WorkDir "automation\state\.heartbeat-api-key"
$originalApiKey = $env:ANTHROPIC_API_KEY
$heartbeatKeyLoaded = $false
if (Test-Path $heartbeatKeyPath) {
    $hbKey = (Get-Content $heartbeatKeyPath -Raw -ErrorAction SilentlyContinue).Trim()
} elseif (Test-Path $heartbeatKeyPathShared) {
    $hbKey = (Get-Content $heartbeatKeyPathShared -Raw -ErrorAction SilentlyContinue).Trim()
} else {
    $hbKey = ""
}
if ($hbKey -and $hbKey -ne "") {
    $env:ANTHROPIC_API_KEY = $hbKey
    $heartbeatKeyLoaded = $true
    $model = "haiku"  # Hard-lock: isolated key runs Haiku only, no Sonnet escalation
    Write-TaskLog -TaskName $task -Message "HEARTBEAT_KEY_LOADED: using isolated API key (FIX-1), model hard-locked to haiku"
}

$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\aggressive\heartbeat.md") `
    -TaskName $task `
    -MaxBudgetUsd 1.00 `
    -Model $model `
    -TimeoutSec $tickTimeout `
    -Effort $tickEffort

# Restore original API key so post-tick scripts use the Max plan key.
if ($heartbeatKeyLoaded) { $env:ANTHROPIC_API_KEY = $originalApiKey }

# Post-tick safety: atomic-bracket-guard catches mid-MCP-timeout failures
# (5/18 10:48 Bold naked-SPY-740C incident class). Cancels orphan parent
# orders, RED-flags STATUS.md if a filled naked position is detected.
# Per CLAUDE.md OP-25 ENGINE-BENEFIT AUTONOMY.
try {
    Invoke-PythonHidden -ScriptPath "setup\scripts\atomic_bracket_guard.py" `
        -ArgList @("--account", "bold", "--silent") `
        -TaskName "atomic-bracket-guard-bold" `
        -TimeoutSec 15 | Out-Null
} catch {
    Write-TaskLog -TaskName $task -Message "atomic-bracket-guard failed: $_"
}

exit $exit
