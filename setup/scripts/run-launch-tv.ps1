# Launch TradingView with CDP debug port - fires at 08:00 ET weekdays.
# Smart: if CDP already responding, no-op. Otherwise launches (with -Kill if needed).
. "$PSScriptRoot\_shared.ps1"

$task = "launch-tv"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}
if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

# Check if CDP is already responding on the expected port
$cdpReady = $false
try {
    $r = Invoke-WebRequest "http://localhost:9222/json/version" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $cdpReady = $true }
} catch {
    # Not responding
}

if ($cdpReady) {
    Write-TaskLog -TaskName $task -Message "CDP_ALREADY_LIVE - skipping launch"
    exit 0
}

# CDP not responding. Check if TV is running without the debug port (need -Kill)
$tvRunning = Get-Process -Name "TradingView" -ErrorAction SilentlyContinue
$killFlag = if ($tvRunning) { "-Kill" } else { "" }

Write-TaskLog -TaskName $task -Message "LAUNCHING tradingview with cdp (kill=$($null -ne $tvRunning))"

$logFile = Join-Path $LogDir "launch-tv-$($et.ToString('yyyy-MM-dd')).log"
$launchScript = Join-Path $WorkDir "setup\launch_tv_debug.ps1"

# FIX 2026-06-15: the child PowerShell + the TradingView exe write progress to stderr.
# Under the inherited Stop preference, *>&1 surfaced that as a NativeCommandError and
# aborted the launch BEFORE confirming CDP (this morning TV came up but CDP was never
# verified -> heartbeat ran all morning on ERROR_TV). Run with Continue so native
# stderr is captured, not fatal; then VERIFY CDP actually came up.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$killArg = if ($tvRunning) { @('-Kill') } else { @() }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $launchScript @killArg 2>&1 |
    Out-File -Append -Encoding utf8 -FilePath $logFile
$ErrorActionPreference = $prevEAP

# Verify CDP confirmed (old script never did -> silent "no TV = no trades").
$cdpUp = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest "http://localhost:9222/json/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $cdpUp = $true; break }
    } catch { }
}
Write-TaskLog -TaskName $task -Message "LAUNCH_COMPLETE exit=$LASTEXITCODE cdp_up=$cdpUp"
if (-not $cdpUp) {
    Write-TaskLog -TaskName $task -Message "WARN CDP did not confirm after launch - heartbeat will ERROR_TV; TvWatchdog should relaunch"
}
exit 0
