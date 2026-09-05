#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_GuardsNightly scheduled task -- fires 22:30 local (Mountain) nightly.

.DESCRIPTION
  Runs the SLOW (data-heavy) graduated-guards regression set that the per-edit
  PostToolUse hook deliberately excludes. The hook runs only the fast logic guards
  (`-m "not slow"`, ~2s) so an engine edit is never blocked; the slow guards
  (`-m slow`, ~35 full backtests over the 16-month master CSV) must still run
  SOMEWHERE or that regression coverage is silently dropped. This task is that
  "somewhere".

  Mechanism: wscript -> run_exe_hidden.vbs -> backtest-venv pythonw -> guard_runner_slow.py
  (the canonical L42/C8 zero-leak hidden-spawn chain -- no console window flash).
  NOTE: the interpreter MUST be the backtest venv (it has pandas+pytest); the system
  Python313 does NOT have them, so a run there fails fast with "No module named pytest".

  Output:
    automation/state/guard-watch-slow.json -- latest verdict (always written)
    STATUS.md "## Known broken" line        -- appended ONCE on a transition into broken

  Timing: 22:30 MT (= 00:30 ET). After-hours under BOTH timezones and clear of the
  09:30-15:55 ET heartbeat window (07:30-13:55 MT) -- never starves the Max pool
  (L54). Runs after the after-4pm ET work block so it catches the evening's engine
  edits. NOTE: -At is LOCAL time (Task Scheduler convention). The rig is Mountain;
  do NOT relabel this as an ET hour (the project_scheduled_task_tz foot-gun).

  Per CLAUDE.md OP-25 (fail loud) + OP-26 (regression surface) + OP-3 ($0, pure
  Python, zero LLM cost). To disable: Unregister-ScheduledTask -TaskName Gamma_GuardsNightly.
#>

$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName = "Gamma_GuardsNightly"

# 2026-09-05 SILENT-RIG R6a fix: was backtest\.venv\Scripts\pythonw.exe run directly --
# that stub's base executable is the CONSOLE python.exe and opens a terminal window per
# fire from this windowless parent. The runner still needs pandas/pytest (the system
# Python313 does NOT have them installed), so the venv's site-packages are reached via
# run_cmd_hidden.py's --env PYTHONPATH instead of executing the venv's own (broken)
# pythonw.exe.
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $WorkDir "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $ScriptsDir "run_cmd_hidden.py"
if (-not (Test-Path $sysPythonw)) {
    Write-Error "system pythonw not found at $sysPythonw"
    exit 1
}

$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$runnerSlow   = Join-Path $WorkDir "setup\guard_runner_slow.py"

foreach ($p in @($runExeHidden, $runnerSlow, $runCmdHidden)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw (venv activated via --env PYTHONPATH) -> guard_runner_slow.py
$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$WorkDir`" -- `"$sysPythonw`" `"$runnerSlow`""

# 22:30 LOCAL (Mountain) = 00:30 ET. After-hours both ways; clear of market hours.
$trigger = New-ScheduledTaskTrigger -Daily -At "22:30"

# ExecutionTimeLimit (60 min) is intentionally WIDER than the runner's internal
# pytest timeout (3000s/50 min) so a hang produces a clean "timeout" verdict in the
# sentinel rather than Task Scheduler killing the process with no verdict written.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 60)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Nightly SLOW graduated-guards regression (the data-heavy backtests the per-edit hook excludes). Writes automation/state/guard-watch-slow.json; flags STATUS.md on a new break. 22:30 MT / 00:30 ET. Pure Python, zero LLM cost. OP-25/OP-26."

Write-Output "OK: Registered $TaskName for 22:30 MT (00:30 ET) daily"
Write-Output "    Verdict:  automation\state\guard-watch-slow.json"
Write-Output "    Audit:    python setup\scripts\audit_scheduled_tasks.py"
Write-Output "    Test now: Start-ScheduledTask -TaskName $TaskName   (runs ~12-20 min)"
