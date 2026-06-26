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
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $launchScript -Kill *>&1 | Out-File -Append -Encoding utf8 -FilePath $logFile
        }
    } else {
        $tvAction = "relaunch_fresh"
        $tvDetail = "no TV process and CDP dead - launching"
        Write-TaskLog -TaskName $task -Message "RELAUNCH_FRESH $tvDetail"
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $launchScript *>&1 | Out-File -Append -Encoding utf8 -FilePath $logFile
    }
}

# --- 2. Heartbeat task freshness ("watching heartbeat") ---------------------
# Only meaningful 09:35-15:55 ET when the engine should tick every 3 min.
$hbFlag = "na"
$mins = $et.Hour * 60 + $et.Minute
if ($mins -ge 575 -and $mins -le 955) {
    try {
        $hb = Get-ScheduledTaskInfo -TaskName "Gamma_Heartbeat" -ErrorAction Stop
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
            & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $lsScript -Kill *>&1 | Out-File -Append -Encoding utf8 -FilePath $lLogFile
        }
    } catch { $hbFlag = "unknown" }
}

# --- 3. Persist status + alert on real problems -----------------------------
$rec = [ordered]@{
    ts        = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    et        = $et.ToString("yyyy-MM-dd HH:mm")
    cdp_up    = $cdpReady
    tv_action = $tvAction
    tv_detail = $tvDetail
    heartbeat = $hbFlag
}
$rec | ConvertTo-Json | Set-Content -Path $statusFile -Encoding utf8

$problem = ($tvAction -like "relaunch*") -or ($hbFlag -like "STALE*") -or ($hbFlag -like "ERR_*")
if ($problem) {
    ($rec | ConvertTo-Json -Compress) | Add-Content -Path $eventLog -Encoding utf8
    $alert = "- [$($et.ToString('MM-dd HH:mm')) ET] TvWatchdog: tv=$tvAction heartbeat=$hbFlag $tvDetail"
    try { Add-Content -Path $statusMd -Value $alert -Encoding utf8 } catch { }
}
exit 0
