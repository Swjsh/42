# Gamma_TvWatchdog - keeps TradingView + CDP (port 9222) alive during trading hours,
# and flags a stale heartbeat. This is the "no TV = no trades" fix.
#
# WHY: Gamma_LaunchTV fires ONCE at 08:00 ET. Nothing recovered a mid-session TV death,
# so when TV/CDP went down the heartbeat read a dead chart and logged blind HOLDs until
# the next 08:00 launch. 2026-06-01: TV died after the 08:00 launch and was not back until
# a manual relaunch at 10:37 ET - roughly one hour of "no TV = no trades". This closes it.
#
# Cadence: every 5 min, 08:05-16:00 ET weekdays. Idempotent: if CDP is live it no-ops.
# Cost: $0 (pure PowerShell). Reuses the proven CDP-check + relaunch block from
# run-launch-tv.ps1 so there is no new launch logic to get wrong.

. "$PSScriptRoot\_shared.ps1"

$task       = "tv-watchdog"
$et         = Get-EtNow
$port       = 9222
$statusFile = Join-Path $WorkDir "automation\state\tv-watchdog-status.json"
$eventLog   = Join-Path $WorkDir "automation\state\tv-watchdog.jsonl"
$statusMd   = Join-Path $WorkDir "automation\overnight\STATUS.md"

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca)  { exit 0 }

# --- 1. TradingView / CDP health + self-heal --------------------------------
$cdpReady = $false
try {
    $r = Invoke-WebRequest "http://localhost:$port/json/version" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $cdpReady = $true }
} catch { }

$tvAction = "none"
$tvDetail = ""

if ($cdpReady) {
    $tvAction = "healthy"
} else {
    $tvRunning    = Get-Process -Name "TradingView" -ErrorAction SilentlyContinue
    $launchScript = Join-Path $WorkDir "setup\launch_tv_debug.ps1"
    $logFile      = Join-Path $LogDir "tv-watchdog-$($et.ToString('yyyy-MM-dd')).log"
    if ($tvRunning) {
        # Process exists but CDP dead. Young process = still booting, give it grace.
        $youngest = $tvRunning | Sort-Object StartTime -Descending | Select-Object -First 1
        $ageSec   = ((Get-Date) - $youngest.StartTime).TotalSeconds
        if ($ageSec -lt 75) {
            $tvAction = "booting"
            $tvDetail = "TV pid=$($youngest.Id) age=$([int]$ageSec)s, CDP warming up"
        } else {
            $tvAction = "relaunch_kill"
            $tvDetail = "TV up but CDP dead for $([int]$ageSec)s - kill+relaunch"
            Write-TaskLog -TaskName $task -Message "RELAUNCH_KILL $tvDetail"
            # FIX 2026-07-06: was missing the 2026-06-15 ErrorActionPreference='Continue'
            # fix (this exact call site is one of 3 -- see Invoke-TvLaunchSafe in _shared.ps1).
            $r = Invoke-TvLaunchSafe -LaunchScript $launchScript -LogFile $logFile -Kill
            if ($r.skipped) { Write-TaskLog -TaskName $task -Message "SKIP_LOCK_HELD $($r.reason)"; $tvAction = "lock_held" }
        }
    } else {
        $tvAction = "relaunch_fresh"
        $tvDetail = "no TV process and CDP dead - launching"
        Write-TaskLog -TaskName $task -Message "RELAUNCH_FRESH $tvDetail"
        $r = Invoke-TvLaunchSafe -LaunchScript $launchScript -LogFile $logFile
        if ($r.skipped) { Write-TaskLog -TaskName $task -Message "SKIP_LOCK_HELD $($r.reason)"; $tvAction = "lock_held" }
    }
}

# --- 2. Heartbeat task freshness ("watching heartbeat") ---------------------
# Only meaningful 09:35-15:55 ET when the engine should tick every 1 min.
# 2026-06-29 FIX: this checked the RETIRED "Gamma_Heartbeat" (LLM, disabled 06-25) which is
# ALWAYS stale -> the hung-bridge branch force-killed TV every 5 min all day (the "TV keeps
# crashing" bug). Must check the LIVE Python engine, Gamma_HeartbeatCore.
$hbFlag = "na"
$mins = $et.Hour * 60 + $et.Minute
if ($mins -ge 575 -and $mins -le 955) {
    try {
        $hb = Get-ScheduledTaskInfo -TaskName "Gamma_HeartbeatCore" -ErrorAction Stop
        $ageMin = ((Get-Date) - $hb.LastRunTime).TotalMinutes
        if ($ageMin -gt 7) { $hbFlag = "STALE_$([int]$ageMin)min" }
        elseif ($hb.LastTaskResult -ne 0) { $hbFlag = ("ERR_0x{0:X}" -f $hb.LastTaskResult) }
        else { $hbFlag = "fresh" }

        # Hung-bridge detection (2026-06-24): CDP alive + heartbeat stale > 6 min during RTH
        # = MCP bridge is hung (port 9222 answers but tool calls freeze). Force-restart TV.
        # Grace is 6 min (< the 7 min stale-flag threshold) so we heal before alerting J.
        if ($cdpReady -and $ageMin -gt 6) {
            $tvAction = "relaunch_hung_bridge"
            $tvDetail = "CDP alive but heartbeat stale $([int]$ageMin)min — hung bridge, force-restarting TV"
            $lsScript = Join-Path $WorkDir "setup\launch_tv_debug.ps1"
            $lLogFile = Join-Path $LogDir "tv-watchdog-$($et.ToString('yyyy-MM-dd')).log"
            Write-TaskLog -TaskName $task -Message "RELAUNCH_HUNG_BRIDGE $tvDetail"
            $r = Invoke-TvLaunchSafe -LaunchScript $lsScript -LogFile $lLogFile -Kill
            if ($r.skipped) { Write-TaskLog -TaskName $task -Message "SKIP_LOCK_HELD $($r.reason)"; $tvAction = "lock_held" }
        }
    } catch { $hbFlag = "unknown" }
}

# --- 3. key-levels.json freshness self-heal (2026-07-30 incident) -----------
# Gamma_LevelRefresh's own PT5M scheduled cadence can go silently dark for hours with
# zero Task Scheduler error signal (root-caused 2026-07-30: ~20h stall, 770/770 RTH
# decision rows blind, engine fell through to its worst trendline-only cohort). Nothing
# previously force-killed+relaunched a stuck instance -- this closes that gap the same
# way section 1 closes the analogous TV/CDP one. RTH-scoped with a 12min post-open
# warmup (matches levels_blind_check.py's own LEVELS_FILE_WARMUP_MIN=12) so a normal
# cold pre-open file never false-triggers, and the 12min stale threshold heals BEFORE
# levels_blind_check.py's own 20min RED-alarm threshold ever needs to fire.
$levelsRefreshAction = "none"
# FIX (2026-07-30, conductor AFTERHOURS re-audit): $mins is Hour*60+Minute (minutes since
# midnight, same convention as the hbFlag window above) -- the window boundary for "09:42
# ET" is therefore 582 (9*60+42), NOT the literal clock digits "942". The original fix used
# 942, which numerically means 15:42 ET (942/60 = 15h42m) -- so the self-heal only ever ran
# in the last 13 minutes before the 15:55 close (942-955) instead of across the intended
# ~373-minute RTH window (582-955). The guard test made the identical mistake (asserted the
# literal substring "942" is present, which is true either way) so it never caught this.
# Caught by re-verifying the fix this fire, not by the test -- the incident's own self-heal
# would have covered ~3% of the session it was built to protect.
if ($mins -ge 582 -and $mins -le 955) {
    $keyLevelsPath = Join-Path $WorkDir "automation\state\key-levels.json"
    if (Test-Path $keyLevelsPath) {
        $klAgeMin = ((Get-Date) - (Get-Item $keyLevelsPath).LastWriteTime).TotalMinutes
        if ($klAgeMin -gt 12) {
            $levelsRefreshAction = "self_heal"
            $lrLogFile = Join-Path $LogDir "level-refresh-watchdog-$($et.ToString('yyyy-MM-dd')).log"
            $lrScript  = Join-Path $WorkDir "setup\scripts\run-level-refresh.ps1"
            Write-TaskLog -TaskName $task -Message "LEVEL_REFRESH_SELF_HEAL key-levels.json stale $([int]$klAgeMin)min - kill+relaunch"
            $lr = Invoke-LevelRefreshSafe -Script $lrScript -LogFile $lrLogFile
            if ($lr.skipped) { Write-TaskLog -TaskName $task -Message "SKIP_LOCK_HELD $($lr.reason)"; $levelsRefreshAction = "lock_held" }
        } else {
            $levelsRefreshAction = "fresh"
        }
    } else {
        $levelsRefreshAction = "missing_file"
    }
}

# --- 3b. Cross-fleet state-freshness self-heal (2026-07-31 generalization) --
# LIVE FINDING: Gamma_TradeToday / Gamma_BrokerFills / Gamma_EmaSnapshot all last fired
# 2026-07-29 despite Enabled=True, State=Ready, LastTaskResult=0 (no crash), no hung
# process on the box -- the scheduled trigger silently stopped firing for >24h with ZERO
# Task Scheduler error signal, and a manual Start-ScheduledTask succeeded immediately.
# state_freshness_audit.py (section above's sibling, 2026-07-30) already DETECTS this
# shape for every manifest-listed file but only reports -- nothing previously
# remediated it, same "nothing recovers it" gap section 3 closed for key-levels.json
# specifically. state_freshness_selfheal.py generalizes the fix: force-start the mapped
# Gamma_* task for any RED entry (cooldown-guarded on the Python side, so a genuinely
# broken producer is not hammered every 5 min). Pure Python, $0, fails open.
$freshHealScript = Join-Path $WorkDir "setup\scripts\state_freshness_selfheal.py"
$freshHealAction = "skipped_no_script"
$fhOut = ""
if (Test-Path $freshHealScript) {
    $venvPy = Join-Path $WorkDir "backtest\.venv\Scripts\pythonw.exe"
    try {
        $fhOut = & $venvPy $freshHealScript --json 2>&1 | Out-String
        $freshHealAction = "ran"
        if ($fhOut -match '"outcome":\s*"start_attempted"') {
            Write-TaskLog -TaskName $task -Message "STATE_FRESHNESS_HEAL $fhOut"
        }
    } catch {
        $freshHealAction = "error"
        Write-TaskLog -TaskName $task -Message "STATE_FRESHNESS_HEAL_ERROR $($_.Exception.Message)"
    }
}

# --- 4. Persist status + alert on real problems -----------------------------
$rec = [ordered]@{
    ts             = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    et             = $et.ToString("yyyy-MM-dd HH:mm")
    cdp_up         = $cdpReady
    tv_action      = $tvAction
    tv_detail      = $tvDetail
    heartbeat      = $hbFlag
    levels_refresh = $levelsRefreshAction
    fresh_heal     = $freshHealAction
}
$rec | ConvertTo-Json | Set-Content -Path $statusFile -Encoding utf8

$problem = ($tvAction -like "relaunch*") -or ($hbFlag -like "STALE*") -or ($hbFlag -like "ERR_*") -or ($levelsRefreshAction -eq "self_heal") -or ($fhOut -match '"outcome":\s*"start_attempted"')
if ($problem) {
    ($rec | ConvertTo-Json -Compress) | Add-Content -Path $eventLog -Encoding utf8
    $alert = "- [$($et.ToString('MM-dd HH:mm')) ET] TvWatchdog: tv=$tvAction heartbeat=$hbFlag levels_refresh=$levelsRefreshAction fresh_heal=$freshHealAction $tvDetail"
    try { Add-Content -Path $statusMd -Value $alert -Encoding utf8 } catch { }
}
exit 0
