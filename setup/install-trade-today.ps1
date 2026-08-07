# install-trade-today.ps1 -- register Gamma_TradeToday (OP-33e 'did it trade' instrument).
# Runs trade_today_watcher.py every 2 min during RTH: queries Alpaca orders (source of truth),
# pings J LOUD on a new SPY-option fill (FIRST FILL EVER flagged), writes trade-today.json.
# Windowless wscript -> run_exe_hidden.vbs -> backtest-venv-pythonw chain. Notify-only, $0.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_TradeToday"
$pythonw = Join-Path $Root "backtest\.venv\Scripts\pythonw.exe"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker = Join-Path $ScriptsDir "trade_today_watcher.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
foreach ($p in @($pythonw, $runExeHidden, $worker, $sysPythonw, $runCmdHidden)) { if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 } }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" -- `"$pythonw`" `"$worker`""
# 07:30 LOCAL (MT) = 09:30 ET open; repeat every 2 min for 6.5h -> covers 09:30-16:00 ET.
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:30"
$rep = (New-ScheduledTaskTrigger -Once -At "07:30" -RepetitionInterval (New-TimeSpan -Minutes 2) -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "OP-33e: LOUD-ping J the moment the engine records a real SPY-option fill (source of truth = Alpaca get_orders, not decisions.jsonl). Every 2 min 09:30-16:00 ET. Writes trade-today.json (glanceable). Notify-only, fail-open, `$0. Guard: test_trade_today_watcher.py."
Write-Output "OK: Registered $TaskName (every 2 min, 09:30-16:00 ET weekdays)"
