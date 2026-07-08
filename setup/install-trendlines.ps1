# install-trendlines.ps1 -- register Gamma_Trendlines (V3, engine-vision build 2026-07-08).
# Runs trendline_engine.py every 5 min RTH: detects the respected asc-support/resistance lines
# and writes automation/state/trendlines-live.json (SHADOW state the engine/dashboard can read).
# Windowless wscript -> run_exe_hidden.vbs -> backtest-venv-pythonw. SHADOW-only, $0.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_Trendlines"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker = Join-Path $Root "backtest\autoresearch\trendline_engine.py"
foreach ($p in @($pythonw, $runExeHidden, $worker)) { if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 } }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$worker`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "V3 engine-vision: detect respected SPY trendlines (asc-support/resistance) every 5 min 09:30-16:00 ET; write trendlines-live.json (SHADOW state, engine/dashboard-readable). The engine does NOT trade off these yet (entry-wire A/B-gated NEEDS-REVIEW). Windowless, `$0. Guard: test_trendline_live_state.py."
Write-Output "OK: Registered $TaskName (every 5 min RTH)"
