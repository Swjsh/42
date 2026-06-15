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

if ($tvRunning) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $launchScript -Kill *>&1 | Out-File -Append -Encoding utf8 -FilePath $logFile
} else {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -NonInteractive -File $launchScript *>&1 | Out-File -Append -Encoding utf8 -FilePath $logFile
}

Write-TaskLog -TaskName $task -Message "LAUNCH_COMPLETE exit=$LASTEXITCODE"
exit 0
