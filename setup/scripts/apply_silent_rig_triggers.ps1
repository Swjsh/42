#Requires -Version 5.1
<#
.SYNOPSIS
    GOAL-SILENT-RIG-2026-09-05 L1 -- edits scheduled-task TRIGGERS and SETTINGS only.

.DESCRIPTION
    Applies the load plan in markdown/infra/SILENT-RIG-2026-09-05.md:
      - NARROW_MONFRI tasks: currently fire every day (DailyTrigger/TimeTrigger with no
        DaysOfWeek filter) despite SPY-engine/tickers-lane doctrine saying weekdays only.
        Rebuilt as a Weekly trigger, Monday-Friday, same clock time + repetition as today.
      - NARROW_CME tasks: same idea, futures-lane tasks scoped to their CME/RTH weekday
        window per futures_health.py / backtest/futures/futures_session.py.
      - OFF_HOURS_CADENCE tasks: keepalives that must stay 24/7 but don't need 5-min
        fidelity outside 08:00-16:30 ET. Split into a "hot" trigger (5 min, 08:00-16:30 ET)
        and two "cold" triggers (15 min, 16:30-24:00 ET and 00:00-08:00 ET) covering the
        rest of the day -- Windows triggers can't wrap midnight in one RepetitionDuration
        window, hence the split.
      - PRIORITY: every Gamma_* task gets Settings.Priority = 7 (below normal), preserving
        every other Settings property (Enabled included -- this script NEVER flips a task's
        enabled state).

    NEVER enables a task. NEVER calls Start-ScheduledTask. Only Set-ScheduledTask against
    triggers/settings on tasks that are already registered. Every mutating call honours
    -WhatIf (this script declares [CmdletBinding(SupportsShouldProcess)]).

    Box runs Mountain time; Task Scheduler StartBoundary/At times are LOCAL. ET = local + 2h.
    So "09:20 ET" == local 07:20, "16:10 ET" == local 14:10, "08:00 ET" == local 06:00,
    "16:30 ET" == local 14:30. All -At / boundary times below are LOCAL, with the ET
    equivalent noted in a comment.

.PARAMETER WhatIf
    Standard PowerShell common parameter -- preview every change without applying it.
    This is the ONLY mode a worker is allowed to invoke; Fable applies for real after review.

.EXAMPLE
    pwsh -File setup/scripts/apply_silent_rig_triggers.ps1 -WhatIf
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$SkipPriority
)

$ErrorActionPreference = 'Stop'

# ── ET-local conversion (box is Mountain time, ET = local + 2h) ────────────────────────────
# SPY-engine window: 09:20-16:10 ET == 07:20-14:10 local. This is the FALLBACK -At time used
# only when a task has no parseable existing StartBoundary -- Set-NarrowMonFriTrigger always
# prefers the task's OWN existing clock time (many of these tasks fire at their own specific
# time, e.g. MondayVerify/WinnerAutopsy/TrendCacheProducer are afternoon one-shots, not
# 07:20 local starts -- overwriting their time-of-day would be a correctness bug, not a fix).
$MonFri_AtFallback = '07:20:00'
$MonFri_DurationH  = 6.833333  # 6h50m -> matches the 09:20-16:10 ET session span, used only
                                # as a clamp ceiling for tasks whose duration is unbounded/empty.
# Keepalive hot window: 08:00-16:30 ET == 06:00-14:30 local
$Hot_At           = '06:00:00'
$Hot_DurationH    = 8.5       # 06:00-14:30 local
$Cold1_At         = '14:30:00'  # 14:30-24:00 local (16:30 ET onward)
$Cold1_DurationH  = 9.5
$Cold2_At         = '00:00:00'  # 00:00-06:00 local (next day, up to 08:00 ET)
$Cold2_DurationH  = 6.0

# ── Task categories (see markdown/infra/SILENT-RIG-2026-09-05.md for the doctrine reason
#    behind each bucket -- this script is the MECHANISM, the doc is the JUSTIFICATION) ────

# NOTE: this list is DELIBERATELY only the tasks whose CURRENT trigger has NO DaysOfWeek
# filter (MSFT_TaskDailyTrigger / MSFT_TaskTimeTrigger). A separate set of <=PT5M tasks
# (Gamma_DeadMansSwitch, EntryBlockWatch, TradeToday, ContextBundle, the 4 futures RTH
# tasks, GhostOrderReconciler, LiveWatch, ThetaClock, Trendlines, TvWatchdog, WatcherLive)
# are ALREADY registered as MSFT_TaskWeeklyTrigger with DaysOfWeek=62 (Mon-Fri) -- verified
# against the snapshot, see markdown/infra/SILENT-RIG-2026-09-05.md -- so they need NO
# trigger change and are intentionally excluded here to keep this script's diff honest.
$NarrowMonFri = @(
    'Gamma_EmaSnapshot', 'Gamma_EodFlatten', 'Gamma_EodFlatten_Aggressive', 'Gamma_EodFullAudit',
    'Gamma_FleetExecutor', 'Gamma_GateExpiryCheck', 'Gamma_HeartbeatCore', 'Gamma_JournalCalendar',
    'Gamma_LaunchTV', 'Gamma_MondayVerify', 'Gamma_MultiCore', 'Gamma_Premarket',
    'Gamma_RefusedSetupLedger', 'Gamma_RegimeStamp', 'Gamma_RuleBreakAudit', 'Gamma_SightBeacon',
    'Gamma_TickersDayCheck', 'Gamma_TickersEodFlatten', 'Gamma_TickersLane', 'Gamma_TrendCacheProducer',
    'Gamma_WinnerAutopsy', 'Gamma_WinnerSignature', 'Gamma_MarketKeepAwakeKeepalive', 'Gamma_XspSpreadRecorder'
)

# CME/futures-lane tasks: RTH-only weekday window per doctrine (same Mon-Fri window as
# above is the RIGHT scope for these three -- they are NOT full-CME-session tasks, doctrine
# text explicitly says "RTH only" / "09:30-16:00 ET weekdays"). Kept as a separate bucket
# only so the table in the doc can show the CME-session provenance distinctly.
$NarrowCme = @(
    'Gamma_FuturesBrokerProbe', 'Gamma_FuturesHealth', 'Gamma_FuturesHeartbeat'
)

# Keepalives: must stay 24/7 (doctrine), but don't need 5-min fidelity outside the trading
# day. Split hot/cold as described above.
$OffHoursCadence = @(
    'Gamma_CompanionKeepalive', 'Gamma_CryptoGrinderKeepalive', 'Gamma_DashboardKeepalive',
    'Gamma_DiscordBridge', 'Gamma_LevelRefresh', 'Gamma_QuoteRecorderKeepalive',
    # Gamma_HealthBeacon: doctrine (SCHEDULED-TASKS.md) says it is already "Market-hours
    # aware (quiet=GREEN overnight)" -- the SCRIPT already no-ops outside session hours, so
    # widening its off-hours launch cadence loses no information, only launch volume. It was
    # the #2 launch-count driver in today's evidence (621 launches, see the doc's before
    # table) precisely because it still spawns a process every minute to emit that no-op.
    'Gamma_HealthBeacon'
)

# Explicit KEEP -- never touched by this script, listed here only so a reviewer can see the
# full accounting (these are the ones GOAL-SILENT-RIG-2026-09-05 L1 explicitly says stay put).
$KeepUnchanged = @(
    'Gamma_CryptoTwin', 'Gamma_WindowLeakDetectorKeepalive', 'Gamma_WindowLeakHookKeepalive',
    'Gamma_QuietMode', 'Gamma_ConductorWake'
)

function Write-PlanLine {
    param([string]$TaskName, [string]$Change)
    Write-Host ("  [{0}] {1}" -f $TaskName, $Change)
}

function Get-ExistingRepetition {
    <# Pull (Interval, Duration) TimeSpan pair off a task's first trigger that has one, or
       $null if the task has no repetition (a plain one-shot trigger). #>
    param($Task)
    foreach ($trig in $Task.Triggers) {
        if ($trig.Repetition -and $trig.Repetition.Interval) {
            return $trig.Repetition
        }
    }
    return $null
}

function ConvertTo-TimeSpanSafe {
    <# ISO-8601 duration string ("PT5M", "PT6H25M", ...) -> TimeSpan, or $null on empty/bad input. #>
    param([string]$Iso)
    if ([string]::IsNullOrWhiteSpace($Iso)) { return $null }
    try { return [System.Xml.XmlConvert]::ToTimeSpan($Iso) } catch { return $null }
}

function Set-NarrowMonFriTrigger {
    param([string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-PlanLine $TaskName "SKIP (task not found in local registry)"
        return
    }
    $firstTrig = $task.Triggers[0]
    $alreadyWeekly = $firstTrig.CimClass.CimClassName -eq 'MSFT_TaskWeeklyTrigger' -and $firstTrig.DaysOfWeek -eq 62
    $wasDesc = if ($alreadyWeekly) {
        "already Weekly Mon-Fri (days=62) -- re-applying to normalize repetition/time only"
    } else {
        "$($firstTrig.CimClass.CimClassName), no DaysOfWeek filter"
    }

    # CORRECTNESS: preserve the task's OWN existing clock time. These tasks do NOT all fire
    # at the same time of day (MondayVerify/WinnerAutopsy/TrendCacheProducer are afternoon
    # one-shots, LaunchTV is a 06:00 local premarket fire, etc.) -- forcing every task onto a
    # single fixed -At would silently move dozens of tasks to the wrong time of day.
    $atTime = $MonFri_AtFallback
    if ($firstTrig.StartBoundary) {
        try {
            $parsed = [DateTimeOffset]::Parse($firstTrig.StartBoundary)
            $atTime = $parsed.ToString('HH:mm:ss')
        } catch {
            # fails open to $MonFri_AtFallback -- never block the run over one bad timestamp
        }
    }

    $rep = Get-ExistingRepetition -Task $task
    $repInterval = ConvertTo-TimeSpanSafe $rep.Interval
    $repDuration = ConvertTo-TimeSpanSafe $rep.Duration

    # CORRECTNESS GUARD: a Weekly trigger's DaysOfWeek filter only re-applies at the START
    # of each matching day -- if the Repetition.Duration spans PAST 24h (e.g. these tasks'
    # original P3650D "keepalive forever" duration, or an empty/unbounded duration), the
    # repetition just keeps firing through Sat/Sun regardless of DaysOfWeek, silently
    # defeating this entire narrowing pass. Clamp any duration that is missing or >= 24h to
    # the Mon-Fri session window itself, so the day-of-week restriction actually holds.
    $sessionSpan = [TimeSpan]::FromHours($MonFri_DurationH)
    $durationClamped = $false
    if (-not $repDuration -or $repDuration -ge [TimeSpan]::FromHours(24)) {
        if ($repInterval) {
            $durationClamped = $true
            $repDuration = $sessionSpan
        }
    }
    $repDesc = if ($repInterval -and $repDuration) {
        $clampNote = if ($durationClamped) { " (duration CLAMPED from $($rep.Duration) -- see script comment)" } else { "" }
        "repeat every $($rep.Interval) for $($repDuration)$clampNote"
    } else {
        "one-shot (no repetition)"
    }

    # New-ScheduledTaskTrigger's -Weekly parameter set does not accept -RepetitionInterval/
    # -RepetitionDuration directly (PS 5.1 ScheduledTasks module limitation) -- the repo's own
    # established idiom (setup/scripts/install-dead-mans-switch.ps1) is to build the repetition
    # pattern via a throwaway -Once trigger and copy its .Repetition CimInstance across.
    $newTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At $atTime
    if ($repInterval -and $repDuration) {
        $newTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At $atTime `
            -RepetitionInterval $repInterval -RepetitionDuration $repDuration).Repetition
    }

    Write-PlanLine $TaskName ("Weekly trigger -> Mon-Fri @ $atTime local (own existing clock time preserved), $repDesc [was: $wasDesc]")

    if ($PSCmdlet.ShouldProcess($TaskName, "Set-ScheduledTask -Trigger (Mon-Fri, unchanged repetition)")) {
        Set-ScheduledTask -TaskName $TaskName -Trigger $newTrigger | Out-Null
    }
}

function Set-OffHoursCadenceTrigger {
    param([string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-PlanLine $TaskName "SKIP (task not found in local registry)"
        return
    }
    $rep = Get-ExistingRepetition -Task $task
    $hotIntervalIso = if ($rep -and $rep.Interval) { $rep.Interval } else { 'PT5M' }  # keepalives all register PT5M today
    $hotInterval = ConvertTo-TimeSpanSafe $hotIntervalIso
    if (-not $hotInterval) { $hotInterval = [TimeSpan]::FromMinutes(5) }
    $coldInterval = [TimeSpan]::FromMinutes(15)

    # Same -Once/.Repetition copy idiom as Set-NarrowMonFriTrigger -- -Daily doesn't accept
    # -RepetitionInterval/-RepetitionDuration directly either.
    $hotTrigger = New-ScheduledTaskTrigger -Daily -At $Hot_At
    $hotTrigger.Repetition = (New-ScheduledTaskTrigger -Once -At $Hot_At `
        -RepetitionInterval $hotInterval -RepetitionDuration ([TimeSpan]::FromHours($Hot_DurationH))).Repetition

    $cold1Trigger = New-ScheduledTaskTrigger -Daily -At $Cold1_At
    $cold1Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $Cold1_At `
        -RepetitionInterval $coldInterval -RepetitionDuration ([TimeSpan]::FromHours($Cold1_DurationH))).Repetition

    $cold2Trigger = New-ScheduledTaskTrigger -Daily -At $Cold2_At
    $cold2Trigger.Repetition = (New-ScheduledTaskTrigger -Once -At $Cold2_At `
        -RepetitionInterval $coldInterval -RepetitionDuration ([TimeSpan]::FromHours($Cold2_DurationH))).Repetition

    Write-PlanLine $TaskName ("3 daily triggers -> hot $hotIntervalIso 06:00-14:30 local (08:00-16:30 ET), " +
        "cold PT15M 14:30-24:00 local + 00:00-06:00 local (rest of day) [was: $hotIntervalIso 24/7 flat]")

    if ($PSCmdlet.ShouldProcess($TaskName, "Set-ScheduledTask -Trigger (hot/cold split, 24/7 preserved)")) {
        Set-ScheduledTask -TaskName $TaskName -Trigger @($hotTrigger, $cold1Trigger, $cold2Trigger) | Out-Null
    }
}

function Set-BelowNormalPriority {
    param([string]$TaskName)

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { return }

    $settings = $task.Settings
    if ($settings.Priority -eq 7) {
        return  # already below-normal, true no-op -- don't log noise for it
    }
    $before = $settings.Priority
    $settings.Priority = 7  # below normal, per Task Scheduler's Priority property (0-10 scale)

    Write-PlanLine $TaskName "Settings.Priority $before -> 7 (below normal) [Enabled unchanged: $($settings.Enabled)]"

    if ($PSCmdlet.ShouldProcess($TaskName, "Set-ScheduledTask -Settings (Priority=7 only)")) {
        Set-ScheduledTask -TaskName $TaskName -Settings $settings | Out-Null
    }
}

# ── Main ─────────────────────────────────────────────────────────────────────────────────

Write-Host "=== GOAL-SILENT-RIG-2026-09-05 L1: apply_silent_rig_triggers.ps1 ==="
Write-Host "Mode: $(if ($WhatIfPreference) { 'WHATIF (preview only, nothing applied)' } else { 'LIVE -- Fable-only, workers must never run this without -WhatIf' })"
Write-Host ""

Write-Host "--- NARROW_MONFRI ($($NarrowMonFri.Count) tasks) ---"
foreach ($name in $NarrowMonFri) { Set-NarrowMonFriTrigger -TaskName $name }

Write-Host ""
Write-Host "--- NARROW_CME ($($NarrowCme.Count) tasks, same Mon-Fri mechanism -- RTH-only per doctrine) ---"
foreach ($name in $NarrowCme) { Set-NarrowMonFriTrigger -TaskName $name }

Write-Host ""
Write-Host "--- OFF_HOURS_CADENCE ($($OffHoursCadence.Count) tasks) ---"
foreach ($name in $OffHoursCadence) { Set-OffHoursCadenceTrigger -TaskName $name }

Write-Host ""
Write-Host "--- KEEP UNCHANGED (no trigger edit; listed for audit completeness) ---"
foreach ($name in $KeepUnchanged) { Write-PlanLine $name "no change (doctrine: stays as-is)" }

if (-not $SkipPriority) {
    Write-Host ""
    Write-Host "--- PRIORITY = 7 on every Gamma_* task ---"
    $allGammaTasks = Get-ScheduledTask -TaskName 'Gamma_*' -ErrorAction SilentlyContinue
    Write-Host "  found $($allGammaTasks.Count) Gamma_* tasks in the local registry"
    foreach ($t in $allGammaTasks) { Set-BelowNormalPriority -TaskName $t.TaskName }
}

Write-Host ""
Write-Host "=== done ($(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') local) ==="
