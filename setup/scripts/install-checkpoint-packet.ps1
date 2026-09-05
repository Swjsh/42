#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_CheckpointPacket -- nightly generator for the September-freeze
  checkpoint packets (GOAL-CHECKPOINT-PACKET-2026-09-29, C4). Fires 23:30 ET daily
  (21:30 MT local -- this box is Mountain, ET=local+2h).

.DESCRIPTION
  Runs `setup/scripts/checkpoint_packet.py` (no args -- the script defaults its
  generation date to today via et_clock.et_now internally), which:
    1. Reads analysis/recommendations/checkpoint-2026-09-29-inventory.json (C1).
    2. Reuses each row's own named scorer (stop_mode_shadow_ledger.py,
       day_throttle_shadow.py, right_tail_capture.py's ledger, the
       ladder-rung/catastrophe-cap/vix-bull-hard-cap shadow ledgers, and each
       prereg's own status/decision_rule field) to compute today's verdict --
       RULE MET / RULE NOT MET / INSUFFICIENT N / PROVISIONAL / UNKNOWN, fail-open
       per row (a broken scorer degrades to one UNKNOWN row, never a crash).
    3. Writes analysis/recommendations/checkpoint-packet-<date>.json (raw numbers).
    4. GENERATES markdown/planning/CHECKPOINT-2026-09-29.md and
       -2026-10-30.md (never hand-edit these -- fix the generator or the source
       preregs/ledgers instead).

  Read-only against the trading engine. NEVER touches a FROZEN_TRADING_PATH file
  (params.json, aggressive/params.json, fleet/*, backtest/lib/filters.py,
  backtest/lib/risk_gate.py, setup/scripts/heartbeat_core.py) -- only reads from
  them and the analysis/ ledgers they feed. Runs daily (not just weekdays) so the
  09-29/10-30 checkpoint reads reflect the prior night's evidence even across a
  weekend gap.

  WIRING PATTERN (flash-free, cloned from install-zero-enter-autopsy.ps1):
    wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest venv pythonw -> checkpoint_packet.py
  Uses the backtest venv's python (same interpreter every other analysis/ scorer
  this packet calls into already depends on).

  Output:
    analysis/recommendations/checkpoint-packet-<date>.json
    markdown/planning/CHECKPOINT-2026-09-29.md
    markdown/planning/CHECKPOINT-2026-10-30.md
  Logs: automation/state/logs/run-cmd-hidden-<date>.log

  To verify: Get-ScheduledTask -TaskName Gamma_CheckpointPacket
  To test now: Start-ScheduledTask -TaskName Gamma_CheckpointPacket
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_CheckpointPacket" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + the goal's CONFIG FREEZE OPERATING RULES
  (read-only instrument, no FROZEN_TRADING_PATH writes, no config shipped by this
  tool -- it only reads and reports). Guard:
  backtest/tests/test_checkpoint_packet_2026_09_05.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\checkpoint_packet.py"
$taskName     = "Gamma_CheckpointPacket"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# checkpoint_packet.py defaults its generation date to today (ET, via et_clock)
# internally when --date is omitted, so the fire command is a fixed argument list.
# 2026-09-05 SILENT-RIG fix: both hops now run the SYSTEM pythonw (GUI subsystem, no console
# window under any circumstance) -- backtest\.venv\Scripts\pythonw.exe is a launcher STUB
# whose base executable is console python.exe (GetConsoleWindow() != 0 under the stub, proven
# 2026-09-05) and was the root cause of the 730-window flash. Dependencies from the venv
# reach the script via --env PYTHONPATH, not via the venv's own pythonw.exe.
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# 21:30 MT = 23:30 ET, EVERY day (weekends included -- the 09-29/10-30 checkpoint
# reads must reflect the prior night's evidence even across a weekend gap).
$trigger = New-ScheduledTaskTrigger -Daily -At "21:30"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Nightly checkpoint-packet generator (GOAL-CHECKPOINT-PACKET-2026-09-29 " + `
    "C4). Runs checkpoint_packet.py -> analysis/recommendations/checkpoint-packet-<date>.json " + `
    "+ GENERATES markdown/planning/CHECKPOINT-2026-09-29.md and -2026-10-30.md (never " + `
    "hand-edit). Read-only; never touches a FROZEN_TRADING_PATH file. Fires 23:30 ET daily " + `
    "(21:30 MT). Pure Python (backtest venv), `$0. Guard: " + `
    "backtest/tests/test_checkpoint_packet_2026_09_05.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for daily 21:30 MT (23:30 ET)"
Write-Output "    State:    $((Get-ScheduledTask -TaskName $taskName).State)"
Write-Output "    Output:   analysis\recommendations\checkpoint-packet-<date>.json"
Write-Output "              markdown\planning\CHECKPOINT-2026-09-29.md"
Write-Output "              markdown\planning\CHECKPOINT-2026-10-30.md"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
