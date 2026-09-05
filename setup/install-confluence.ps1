# install-confluence.ps1 -- register Gamma_Confluence (confluence layer, 2026-07-08).
# Runs confluence_producer.py every 10 min RTH: stacks the memory/trendline/wick-low/gap shadow
# sources into scored CONFLUENCE ZONES (automation/state/confluence-zones.json). SHADOW-only.
$ErrorActionPreference = "Stop"
$Root = "C:\Users\jackw\Desktop\42"; $ScriptsDir = Join-Path $Root "setup\scripts"
$TaskName = "Gamma_Confluence"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$worker = Join-Path $ScriptsDir "confluence_producer.py"
# 2026-08-07: relay through run_cmd_hidden.py for real exit-code visibility -- see
# VBS-WRAPPER-EXIT-CODE-BLIND-SPOT / Gamma_CryptoTwin drift finding, queue.md.
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $Root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
foreach ($p in @($runExeHidden, $worker, $sysPythonw, $runCmdHidden)) { if (-not (Test-Path $p)) { Write-Error "missing: $p"; exit 1 } }
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$Root`" --env `"PYTHONPATH=$pythonPath`" -- `"$sysPythonw`" `"$worker`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At "07:32"
$rep = (New-ScheduledTaskTrigger -Once -At "07:32" -RepetitionInterval (New-TimeSpan -Minutes 10) -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)).Repetition
$trigger.Repetition = $rep
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description "Confluence layer: stack the memory/trendline/wick-low/gap shadow sources into scored CONFLUENCE ZONES (>=2 distinct sources within +/-0.85, deduped, capped 8) -> confluence-zones.json. Captures how J reads structure (745.39 = 3 sources stacked). Every 10 min 09:32-16:00 ET. SHADOW-only (entry-use A/B-gated). Windowless, `$0. Guard: test_confluence_producer.py."
Write-Output "OK: Registered $TaskName (every 10 min RTH)"
