# install-broker-fills.ps1 -- register Gamma_BrokerFills (HANDOFF-2026-07-09-TRUTH-AND-EXITS, T1).
# Clone of install-level-memory.ps1's wscript->pythonw hidden pattern. Two triggers on ONE task:
#   (a) 10-min repeating, 09:00-16:00 ET (07:00-14:00 local Mountain) -- intraday visibility.
#   (b) one dedicated EOD fire at 16:05 ET (14:05 local) -- AFTER EodFlatten (15:55) and the last
#       RTH repeat (16:00), so the day's ledger is settled before firm_brief / EOD digest read it.
$ErrorActionPreference = "Stop"
$Root       = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName   = "Gamma_BrokerFills"
$pythonw    = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker     = Join-Path $ScriptsDir "broker_fills.py"

foreach ($p in @($pythonw, $runExeHidden, $worker)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""

# (a) 07:00 LOCAL (Mountain) = 09:00 ET; repeat every 10 min for 7h -> covers 09:00-16:00 ET.
$rthTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00"
$rep = (New-ScheduledTaskTrigger -Once -At "07:00" `
        -RepetitionInterval (New-TimeSpan -Minutes 10) `
        -RepetitionDuration (New-TimeSpan -Hours 7)).Repetition
$rthTrigger.Repetition = $rep

# (b) 14:05 LOCAL (Mountain) = 16:05 ET; single daily fire, after EodFlatten + last RTH repeat.
$eodTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "14:05"

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($rthTrigger, $eodTrigger) `
    -Settings $settings `
    -Description "T1: broker-truth fills ledger + pnl-statement (Alpaca activities/FILL, all 6 fleet accounts). 10-min RTH + 16:05 ET EOD fire."

Write-Output "Registered $TaskName."
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object NextRunTime, LastRunTime, LastTaskResult
