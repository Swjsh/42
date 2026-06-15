# Throttle benchmark v2 - simulates run-heartbeat.ps1 with HTF override + tightened Sonnet rules.
# Verifies: cost, bar-close coverage (5m and 15m), 5h rolling-window quota, edge cases.
$ErrorActionPreference = "Stop"

# ============================================================
# Throttle decision (mirrors run-heartbeat.ps1 v2)
# ============================================================
function Get-ThrottleFire {
    param([int]$TickIndex, [string]$Mode, [bool]$PositionOpen, [bool]$ModelEscalated)
    # HTF override - every 15-min post-close tick (idx % 5 == 1) fires regardless of mode
    $is15MinPostClose = ($TickIndex % 5) -eq 1
    if ($PositionOpen -or $ModelEscalated -or $is15MinPostClose) { return $true }
    switch ($Mode.ToUpper()) {
        "HOT"  { return $true }
        "BASE" { return ($TickIndex % 2) -eq 0 }
        "COOL" { return ($TickIndex % 3) -eq 0 }
        default { return $true }
    }
}

# ============================================================
# Sonnet escalation decision (mirrors heartbeat.md v2)
# ============================================================
function Should-EscalateToSonnet {
    param(
        [string]$Mode,
        [int]$BullScore,
        [int]$BearScore,
        [bool]$NewBarClosed,
        [bool]$Is15MinPostClose,
        [bool]$RibbonFlipped,
        [bool]$TriggerFired,
        [bool]$VixTierCrossed,
        [bool]$PositionOpen
    )
    # Always-Sonnet
    if ($PositionOpen -or $RibbonFlipped -or $TriggerFired -or $Is15MinPostClose -or $VixTierCrossed) {
        return $true
    }
    # HOT mode
    if ($Mode.ToUpper() -eq "HOT") {
        if ($NewBarClosed) { return $true }
        if ($BullScore -ge 7 -or $BearScore -ge 6) { return $true }
        return $false
    }
    # BASE/COOL mode
    if ($NewBarClosed -and ($BullScore -ge 9 -or $BearScore -ge 8)) { return $true }
    return $false
}

# ============================================================
# Build full-day schedule (Task Scheduler firings every 3 min from 09:30 to 15:50 ET)
# ============================================================
$ticks = New-Object System.Collections.ArrayList
$totalMinutes = (15 * 60 + 50) - (9 * 60 + 30)
for ($offset = 0; $offset -le $totalMinutes; $offset += 3) {
    $abs = (9 * 60 + 30) + $offset
    $h = [int][Math]::Floor($abs / 60)
    $m = $abs % 60
    $idx = [int][Math]::Floor($offset / 3)
    $wall = "{0:D2}h{1:D2}" -f $h, $m
    [void]$ticks.Add([PSCustomObject]@{
        Index = $idx
        Wall = $wall
        AbsMin = $abs
        PromptSkip = ($abs -lt (9 * 60 + 35))
        # A 5-min bar closes at minute % 5 == 0 (in absolute clock minutes).
        # The tick AT that minute fires WITH the close (bar may not yet be ohlcv'd in TV).
        # The tick 1-3 min after sees the closed bar reliably.
        # Heuristic: post-5-min-close tick = the first firing where (abs_min - 1) % 5 == 0..2 and prior tick was NOT post-close.
        # Simpler: a tick at abs_min sees the bar that closed at the largest multiple of 5 <= abs_min - 1.
        # Define "fresh 5m close" = the 5m bar at floor((abs_min-1)/5)*5 just closed (within last 4 min) AND wasn't seen by previous firing.
        Is15MinPostClose = ($idx % 5) -eq 1
    })
}

# 5-min bar closes (each at HH:00, HH:05, ..., HH:55)
$bars5m = New-Object System.Collections.ArrayList
for ($abs = (9 * 60 + 35); $abs -le (15 * 60 + 50); $abs += 5) { [void]$bars5m.Add($abs) }

# 15-min bar closes (each at HH:00, HH:15, HH:30, HH:45).
# Skip 09:30 - that's the open, not a meaningful close in our session window.
# First tradable 15m close is 09:45 (covers 09:30-09:45).
$bars15m = New-Object System.Collections.ArrayList
for ($abs = (9 * 60 + 45); $abs -le (15 * 60 + 50); $abs += 15) { [void]$bars15m.Add($abs) }

# ============================================================
# Cost model (USD per tick)
# ============================================================
# Rough per-tick token use: input ~3K (prompt + state files + tool results), output ~400 tok (one-line + state JSON).
# HTF refresh ticks add ~500 input tokens (extra OHLCV + ribbon read on 15m).
$haikuIn = 0.80; $haikuOut = 4.00       # USD per M tokens
$sonnetIn = 3.00; $sonnetOut = 15.00
function Get-TickCost {
    param([string]$Model, [bool]$IsHtfRefresh)
    $extra = 0
    if ($IsHtfRefresh) { $extra = 500 }
    $inTok = 3000 + $extra
    $outTok = 400
    if ($Model -eq "sonnet") { return ($inTok / 1e6) * $sonnetIn + ($outTok / 1e6) * $sonnetOut }
    return ($inTok / 1e6) * $haikuIn + ($outTok / 1e6) * $haikuOut
}

# ============================================================
# Simulator
# ============================================================
function Simulate {
    param(
        [string]$Name,
        [hashtable]$ModeByPhase,
        [hashtable]$ScoreByPhase = @{},      # absMin -> @{Bull=N; Bear=N}
        [int[]]$RibbonFlipsAt = @(),         # absMins of ribbon flips
        [int[]]$TriggersAt = @(),            # absMins of triggers fired
        [int[]]$VixCrossingsAt = @(),
        [int]$PositionOpenStart = -1,        # absMin position opens
        [int]$PositionOpenEnd = -1
    )
    $fired = 0; $skippedPrompt = 0; $skippedThrottle = 0
    $sonnetTicks = 0; $haikuTicks = 0; $cost = 0.0
    $coverage5m = @{}; foreach ($b in $bars5m) { $coverage5m[$b] = -1 }
    $coverage15m = @{}; foreach ($b in $bars15m) { $coverage15m[$b] = -1 }
    $tickLog = New-Object System.Collections.ArrayList

    # Sort mode changes
    $modeChanges = @()
    foreach ($key in $ModeByPhase.Keys) {
        $parts = $key.Split(":")
        $modeChanges += [PSCustomObject]@{
            AbsMin = [int]$parts[0] * 60 + [int]$parts[1]
            Mode = $ModeByPhase[$key]
        }
    }
    $modeChanges = $modeChanges | Sort-Object AbsMin

    # Track new-bar-closed events between consecutive fired ticks
    $lastFiredAbsMin = -1
    # Track when mode last had elevated score (for auto-drop modeling)
    $lastElevatedScoreAbsMin = -1
    $autoDroppedToBase = $false

    foreach ($tick in $ticks) {
        if ($tick.PromptSkip) { $skippedPrompt++; continue }

        # Determine mode (explicit phase setting)
        $mode = "BASE"
        foreach ($mc in $modeChanges) {
            if ($tick.AbsMin -ge $mc.AbsMin) { $mode = $mc.Mode }
        }

        # Mode auto-drop: if explicit mode is HOT but score has been <7/<6 for 30+ min, drop to BASE.
        # Reset auto-drop flag if explicit mode changes.
        if ($mode -eq "HOT" -and $autoDroppedToBase) {
            # Check if score has re-elevated since last auto-drop check
            # (handled below by lastElevatedScoreAbsMin)
        }

        # Score for this tick (carries forward from most recent threshold)
        $bull = 0; $bear = 0
        $sortedScoreKeys = $ScoreByPhase.Keys | Sort-Object
        foreach ($k in $sortedScoreKeys) {
            if ($tick.AbsMin -ge [int]$k) {
                $bull = $ScoreByPhase[$k].Bull
                $bear = $ScoreByPhase[$k].Bear
            }
        }

        # Track elevated-score timing for auto-drop
        if ($bull -ge 7 -or $bear -ge 6) {
            $lastElevatedScoreAbsMin = $tick.AbsMin
            $autoDroppedToBase = $false
        }
        # Apply auto-drop: HOT -> BASE after 30 min of low score
        if ($mode -eq "HOT" -and $lastElevatedScoreAbsMin -ge 0 -and ($tick.AbsMin - $lastElevatedScoreAbsMin) -gt 30) {
            $mode = "BASE"
            $autoDroppedToBase = $true
        }
        # If never elevated, treat HOT as BASE after 30 min from session start
        if ($mode -eq "HOT" -and $lastElevatedScoreAbsMin -lt 0 -and $tick.AbsMin -gt ((9 * 60 + 30) + 30)) {
            $mode = "BASE"
            $autoDroppedToBase = $true
        }

        # Position open?
        $posOpen = ($PositionOpenStart -ge 0 -and $tick.AbsMin -ge $PositionOpenStart -and $tick.AbsMin -le $PositionOpenEnd)

        # Event detection - did a new 5m bar close between last fired tick and this one?
        $newBarClosed = $false
        if ($lastFiredAbsMin -ge 0) {
            foreach ($b in $bars5m) {
                if ($b -gt $lastFiredAbsMin -and $b -le $tick.AbsMin) { $newBarClosed = $true }
            }
        } else {
            # First tick of day: any bar close <= now counts
            foreach ($b in $bars5m) { if ($b -le $tick.AbsMin) { $newBarClosed = $true; break } }
        }

        # Ribbon flips / triggers / VIX in this tick window
        $flipped = $false; $triggered = $false; $vixCrossed = $false
        $windowStart = if ($lastFiredAbsMin -ge 0) { $lastFiredAbsMin + 1 } else { 0 }
        foreach ($t in $RibbonFlipsAt) { if ($t -ge $windowStart -and $t -le $tick.AbsMin) { $flipped = $true } }
        foreach ($t in $TriggersAt) { if ($t -ge $windowStart -and $t -le $tick.AbsMin) { $triggered = $true } }
        foreach ($t in $VixCrossingsAt) { if ($t -ge $windowStart -and $t -le $tick.AbsMin) { $vixCrossed = $true } }

        # Sonnet decision
        $useSonnet = Should-EscalateToSonnet -Mode $mode -BullScore $bull -BearScore $bear `
            -NewBarClosed $newBarClosed -Is15MinPostClose $tick.Is15MinPostClose `
            -RibbonFlipped $flipped -TriggerFired $triggered -VixTierCrossed $vixCrossed `
            -PositionOpen $posOpen

        # Throttle decision (the script ignores future Sonnet decision; it only knows last tick's flag).
        # For benchmark: assume Sonnet flag follows useSonnet from prior fired tick.
        # Conservative: if useSonnet would fire now, model the bypass too.
        $shouldFire = Get-ThrottleFire -TickIndex $tick.Index -Mode $mode -PositionOpen $posOpen -ModelEscalated $useSonnet
        if (-not $shouldFire) { $skippedThrottle++; continue }

        # Cost
        $isHtf = $tick.Is15MinPostClose
        $modelLabel = if ($useSonnet) { "sonnet" } else { "haiku" }
        $cost += Get-TickCost -Model $modelLabel -IsHtfRefresh $isHtf
        if ($useSonnet) { $sonnetTicks++ } else { $haikuTicks++ }

        $fired++
        [void]$tickLog.Add([PSCustomObject]@{
            AbsMin = $tick.AbsMin
            Wall = $tick.Wall
            Model = $modelLabel
            Mode = $mode
            Bull = $bull
            Bear = $bear
            NewBar = $newBarClosed
            Htf = $isHtf
        })

        # Coverage
        foreach ($b in $bars5m) {
            if ($b -le $tick.AbsMin -and $coverage5m[$b] -eq -1) { $coverage5m[$b] = $tick.AbsMin - $b }
        }
        foreach ($b in $bars15m) {
            if ($b -le $tick.AbsMin -and $coverage15m[$b] -eq -1) { $coverage15m[$b] = $tick.AbsMin - $b }
        }

        $lastFiredAbsMin = $tick.AbsMin
    }

    # Coverage stats
    $latencies5m = @(); foreach ($v in $coverage5m.Values) { if ($v -ne -1) { $latencies5m += $v } }
    $latencies15m = @(); foreach ($v in $coverage15m.Values) { if ($v -ne -1) { $latencies15m += $v } }
    $avg5 = if ($latencies5m.Count -gt 0) { ($latencies5m | Measure-Object -Average).Average } else { 0 }
    $max5 = if ($latencies5m.Count -gt 0) { ($latencies5m | Measure-Object -Maximum).Maximum } else { 0 }
    $avg15 = if ($latencies15m.Count -gt 0) { ($latencies15m | Measure-Object -Average).Average } else { 0 }
    $max15 = if ($latencies15m.Count -gt 0) { ($latencies15m | Measure-Object -Maximum).Maximum } else { 0 }
    $missed5 = ($coverage5m.Values | Where-Object { $_ -eq -1 }).Count
    $missed15 = ($coverage15m.Values | Where-Object { $_ -eq -1 }).Count

    # 5h rolling window peak (worst 300-min stretch)
    $peak5h = 0
    foreach ($t in $tickLog) {
        $count = 0
        foreach ($u in $tickLog) {
            if ($u.AbsMin -ge $t.AbsMin -and $u.AbsMin -le ($t.AbsMin + 300) -and $u.Model -eq "sonnet") { $count++ }
        }
        if ($count -gt $peak5h) { $peak5h = $count }
    }

    return [PSCustomObject]@{
        Scenario = $Name
        Fired = $fired
        Sonnet = $sonnetTicks
        Haiku = $haikuTicks
        SkipThrottle = $skippedThrottle
        CostDay = [Math]::Round($cost, 4)
        CostMo = [Math]::Round($cost * 21, 2)
        Avg5mLag = [Math]::Round($avg5, 2)
        Max5mLag = $max5
        Miss5m = $missed5
        Avg15mLag = [Math]::Round($avg15, 2)
        Max15mLag = $max15
        Miss15m = $missed15
        Peak5hSonnet = $peak5h
    }
}

# ============================================================
# Run scenarios
# ============================================================
Write-Host ""
Write-Host "=== Throttle benchmark v2 - HTF coverage + tightened Sonnet rules ===" -ForegroundColor Cyan
Write-Host "Total firings: $($ticks.Count) | Eligible: $(($ticks | Where-Object { -not $_.PromptSkip }).Count)"
Write-Host "5-min bar closes in window: $($bars5m.Count) | 15-min closes: $($bars15m.Count)"
Write-Host ""

$results = @()

# Quiet day - HOT at open, auto-drops to BASE, stays there
$results += Simulate -Name "Quiet day (open HOT, no setup, auto-drops)" `
    -ModeByPhase @{ "09:30" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=4; Bear=2} }

# Realistic day - score peaks at 7 mid-session, HOT during open and close
$results += Simulate -Name "Realistic day (score peaks 7 at 13:00)" `
    -ModeByPhase @{ "09:30" = "HOT"; "11:00" = "BASE"; "14:30" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=4; Bear=2}; "660" = @{Bull=6; Bear=3}; "780" = @{Bull=7; Bear=2}; "840" = @{Bull=5; Bear=2}; "870" = @{Bull=8; Bear=2}; "930" = @{Bull=4; Bear=2} } `
    -RibbonFlipsAt @(605, 870)

# Today's actual pattern - sustained 9/11 for 5 bars (60 min) with multiple ribbon adjustments
$results += Simulate -Name "Today's pattern (9/11 sustained 60 min, no trade)" `
    -ModeByPhase @{ "09:30" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=4; Bear=2}; "330" = @{Bull=6; Bear=3}; "490" = @{Bull=8; Bear=2}; "555" = @{Bull=9; Bear=2}; "615" = @{Bull=5; Bear=2} } `
    -RibbonFlipsAt @(330, 555) -VixCrossingsAt @(450, 540)

# Trade day - bullish entry at 14:30, position runs 30 min
$results += Simulate -Name "Trade day (entry 14:30, 30 min position)" `
    -ModeByPhase @{ "09:30" = "HOT"; "11:00" = "BASE"; "14:30" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=4; Bear=2}; "870" = @{Bull=11; Bear=2}; "900" = @{Bull=8; Bear=2}; "960" = @{Bull=4; Bear=2} } `
    -RibbonFlipsAt @(605, 870) -TriggersAt @(870) -PositionOpenStart 873 -PositionOpenEnd 903

# Whipsaw day - 4 ribbon flips, score oscillates, mode toggles HOT/BASE multiple times
$results += Simulate -Name "Whipsaw (4 ribbon flips, score oscillates)" `
    -ModeByPhase @{ "09:30" = "HOT"; "10:30" = "BASE"; "11:30" = "HOT"; "13:00" = "BASE"; "14:00" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=5; Bear=3}; "60" = @{Bull=7; Bear=2}; "150" = @{Bull=3; Bear=6}; "240" = @{Bull=8; Bear=2}; "360" = @{Bull=2; Bear=7}; "480" = @{Bull=6; Bear=4} } `
    -RibbonFlipsAt @(75, 165, 255, 375) -VixCrossingsAt @(100, 200, 300, 400)

# Late-day rip - boring all day, sudden setup at 15:15, no entry, score drops by close
$results += Simulate -Name "Late-day rip (sudden setup 15:15)" `
    -ModeByPhase @{ "09:30" = "BASE" } `
    -ScoreByPhase @{ "0" = @{Bull=3; Bear=2}; "345" = @{Bull=8; Bear=2}; "360" = @{Bull=10; Bear=2}; "375" = @{Bull=6; Bear=2} } `
    -RibbonFlipsAt @(345)

# Worst-realistic: HOT-elevated 4 hours sustained (extended setup)
$results += Simulate -Name "Worst-realistic: HOT 4h with score 7-9" `
    -ModeByPhase @{ "09:30" = "HOT" } `
    -ScoreByPhase @{ "0" = @{Bull=5; Bear=2}; "30" = @{Bull=7; Bear=2}; "120" = @{Bull=9; Bear=2}; "240" = @{Bull=8; Bear=2} } `
    -RibbonFlipsAt @(60)

$results | Format-Table -AutoSize

# ============================================================
# Cost summary
# ============================================================
Write-Host ""
Write-Host "=== Cost projection (21 trading days/mo) ===" -ForegroundColor Cyan
foreach ($r in $results) {
    $pad = $r.Scenario.PadRight(50)
    Write-Host "  $pad  $($r.CostDay) USD/day  --  $($r.CostMo) USD/mo"
}
Write-Host ""
Write-Host "Plan cap: 100 USD/mo. Headroom check vs the cap." -ForegroundColor Yellow
Write-Host ""

# ============================================================
# Coverage proof
# ============================================================
Write-Host "=== Bar-close coverage (5m and 15m) ===" -ForegroundColor Cyan
Write-Host "All scenarios should show 0 missed 15m bars (HTF guarantee)."
foreach ($r in $results) {
    $pad = $r.Scenario.PadRight(50)
    Write-Host "  $pad  5m: avg $($r.Avg5mLag)m / max $($r.Max5mLag)m (miss $($r.Miss5m))  |  15m: avg $($r.Avg15mLag)m / max $($r.Max15mLag)m (miss $($r.Miss15m))"
}
Write-Host ""

# ============================================================
# 5h rolling-window stress (Sonnet ticks per 5h window)
# ============================================================
Write-Host "=== 5h rolling-window peak Sonnet usage ===" -ForegroundColor Cyan
Write-Host "Indicator of pressure on the Max 5x plan rolling quota."
foreach ($r in $results) {
    $pad = $r.Scenario.PadRight(50)
    Write-Host "  $pad  peak Sonnet ticks/5h: $($r.Peak5hSonnet)"
}
Write-Host ""

# ============================================================
# HTF coverage edge cases
# ============================================================
Write-Host "=== HTF coverage edge case verification ===" -ForegroundColor Cyan
$htfFireIdxs = @()
foreach ($tick in $ticks) {
    if (-not $tick.PromptSkip -and $tick.Is15MinPostClose) {
        $htfFireIdxs += $tick.Wall
    }
}
$htfCount = $htfFireIdxs.Count
Write-Host "  HTF post-close ticks (always fire): $htfCount across the session"
Write-Host "  These ticks: $($htfFireIdxs -join ', ')"
Write-Host ""

# ============================================================
# Sonnet usage breakdown for realistic scenario
# ============================================================
Write-Host "=== Realistic-day model mix ===" -ForegroundColor Cyan
$realistic = $results[1]
$total = $realistic.Fired
if ($total -gt 0) {
    $sonnetPct = [Math]::Round(($realistic.Sonnet / $total) * 100, 1)
    $haikuPct = [Math]::Round(($realistic.Haiku / $total) * 100, 1)
    Write-Host "  Fired: $total | Sonnet: $($realistic.Sonnet) ($sonnetPct%) | Haiku: $($realistic.Haiku) ($haikuPct%)"
}
Write-Host ""

# ============================================================
# Today's actual cost reconstruction (vs new path)
# ============================================================
Write-Host "=== Cost vs today's actual path ===" -ForegroundColor Cyan
# Today: 127 ticks, all Sonnet, ~5K input + ~1.5K output (verbose markdown)
$todayInTok = 5000; $todayOutTok = 1500
$todayCostPerTick = ($todayInTok / 1e6) * 3.00 + ($todayOutTok / 1e6) * 15.00
$todayDailyCost = $todayCostPerTick * 127
Write-Host "  Today's path (Sonnet, 5K in / 1.5K out, 127 ticks): $([Math]::Round($todayDailyCost, 2)) USD/day -> $([Math]::Round($todayDailyCost * 21, 2)) USD/mo"
$todayPattern = $results[2]
$reduction = [Math]::Round((1 - ($todayPattern.CostDay / $todayDailyCost)) * 100, 1)
Write-Host "  v2 on same pattern: $($todayPattern.CostDay) USD/day -> $($todayPattern.CostMo) USD/mo  ($reduction% reduction)"
Write-Host ""
