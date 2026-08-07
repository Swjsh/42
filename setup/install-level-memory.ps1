# install-level-memory.ps1 -- register Gamma_LevelMemory (V1b, engine-vision build 2026-07-08).
#
# Runs setup/scripts/level_memory_producer.py every 10 min during RTH to keep the multi-day
# MEMORY-level shadow map (automation/state/key-levels-memory.json) fresh. Windowless via the
# canonical wscript -> run_exe_hidden.vbs -> backtest-venv-pythonw chain (L41/L42/C8 no-flash).
# Shadow-only: does NOT touch the live entry feed. Idempotent (re-run to update).
$ErrorActionPreference = "Stop"
$Root      = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName  = "Gamma_LevelMemory"
$pythonw      = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker       = Join-Path $ScriptsDir "level_memory_producer.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"

foreach ($p in @($pythonw, $runExeHidden, $worker, $sysPythonw, $runCmdHidden)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" -- `"$pythonw`" `"$worker`""

# 07:00 LOCAL (Mountain) = 09:00 ET; repeat every 10 min for 7h -> covers 09:00-16:00 ET.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:00"
$rep = (New-ScheduledTaskTrigger -Once -At "07:00" `
        -RepetitionInterval (New-TimeSpan -Minutes 10) `
        -RepetitionDuration (New-TimeSpan -Hours 7)).Repetition
$trigger.Repetition = $rep

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "V1b: refresh the multi-day level-MEMORY shadow map (key-levels-memory.json) every 10 min, 09:00-16:00 ET weekdays. Runs level_memory_producer.py on the backtest venv (pandas/yfinance). Windowless. SHADOW-only -- does NOT touch the live entry feed (that wire is A/B-gated). Idempotent, fail-open, $0."

Write-Output "OK: Registered $TaskName (every 10 min, 09:00-16:00 ET weekdays)"
Write-Output "    Worker: $worker  (backtest venv pythonw)"
Write-Output "    Shadow: automation\state\key-levels-memory.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $TaskName"
