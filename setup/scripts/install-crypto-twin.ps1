#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_CryptoTwin -- the CRYPTO TWIN 24/7 mechanism-validation training
  ground (markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md, J requirement
  2026-07-10: "get an MCP that trades crypto and just replicate the engine there and
  use that as a training ground... I can't keep fixing four things and waiting for
  the next day"). Fires every 1 min, 24/7 -- crypto never closes, so unlike every
  RTH-gated SPY task there is deliberately NO day/time restriction here.

  CADENCE-TUNE (2026-08-01, J latency drill): was every 5 min 2026-07-10..2026-07-31,
  now every 1 min. Real measured latency drill (5 forced round trips, real Alpaca paper
  fills) found the twin's J-visible glance file (twin-health.json) can lag a real fill
  by up to a full cadence period (observed: one forced entry landed off-cycle and
  twin-health.json didn't reflect it until the next scheduled tick, ~4m36s later).
  Separately, 1-min BTC/USD realized-vol evidence (48h weekend sample) showed a 5-min
  look-away exposes ~2-2.6x the adverse-move blind spot of a 1-min one (median adverse
  move per window: $35.04 @ 5min vs $13.25 @ 1min; p95: $115.72 vs $57.59) -- and
  crypto_twin_core.manage_positions reads a LIVE bid/ask quote every tick (not just the
  5m bar close), so a tighter task cadence genuinely shortens catastrophe-cap/TP1/
  trailing-stop reaction time, not just visibility latency. Cost: $0 either way (pure
  Python, no LLM on this path) -- the existing task Settings already carry
  `-MultipleInstances IgnoreNew` + a 3-min ExecutionTimeLimit, so a tick that
  occasionally overruns 60s (e.g. a full 3x20s passive-entry-miss poll) is safely
  skipped rather than double-run; no settings change needed for that safety property.
  Twin-only -- the SPY heartbeat (Gamma_HeartbeatCore, already 1-min) is untouched.

  Each fire runs setup/scripts/crypto_twin_health.py --live, which wraps
  crypto_twin_core.run_tick() (T1/T2, tested 40/40: SEE bars -> DECIDE ribbon+level
  trigger -> risk_gate -> ACT place -> manage exit_manager -> journal, against
  BTC/USD on Alpaca crypto PAPER) in a catch-all error-capture layer and writes
  automation/state/twin-health.json + automation/state/crypto-twin/soak-log.jsonl
  every tick (T3, OP-33c visibility).

  T2's real-order path is CURRENTLY a safe no-op (BLOCKED_NO_ACCOUNT -- no dedicated
  twin Alpaca account configured yet). Registering with --live now is intentional and
  SAFE: crypto_twin_core.run_tick() checks `creds is None` BEFORE ever calling the
  broker and short-circuits straight to action=BLOCKED_NO_ACCOUNT, so this task
  places NOTHING until J drops real creds into
  automation/state/crypto-twin/secrets.json (template:
  automation/state/crypto-twin/secrets.json.example) -- at which point the very next
  tick starts placing real crypto PAPER orders with ZERO code changes.

  REAPER EXEMPTION -- verified against the REAL committed source, not assumed (guard:
  backtest/tests/test_crypto_twin_reaper_exemption.py). setup/scripts/_shared.ps1's
  Stop-StaleClaudeProcesses reaps stale claude.exe/node.exe/python.exe/uv.exe/uvx.exe
  processes referencing this repo every ~3-5 min unless EXEMPT_DAEMONS matches. TWO
  independent exemption layers apply here:
    1. PRIMARY (by construction): 'pythonw.exe' is NOT in Stop-StaleClaudeProcesses's
       Win32_Process -Filter Name clause at all -- this task's spawned process is
       therefore never even fetched by the reaper's query, independent of
       EXEMPT_DAEMONS string matching.
    2. DEFENSE IN DEPTH: the twin is launched via backtest\.venv\Scripts\pythonw.exe
       (NOT system pythonw), so its CommandLine also contains the literal substring
       'backtest\.venv', which IS one of $EXEMPT_DAEMONS's existing entries -- so if a
       future edit ever widens the Name filter to include pythonw.exe, this task
       stays exempt with zero further changes needed.

  WIRING PATTERN (2026-08-07 CORRECTED -- see VBS-WRAPPER-EXIT-CODE-BLIND-SPOT drift
  finding, queue.md): this task was migrated onto the run_cmd_hidden.py relay by
  fix-venv-pythonw-console-leak.ps1 (commit 306e5075, "popup storm" fix), but THIS
  install script's own template was never updated to match -- so the very next
  legitimate re-run of install-crypto-twin.ps1 (af849657, the 2026-08-01 cadence-tune,
  an ordinary maintenance edit unrelated to the relay fix) silently re-registered the
  task with the OLD direct-wiring action, undoing the fix with zero error/log/visible
  symptom (confirmed live 2026-08-07: task was back to bare venv-pythonw invocation).
  This is the durable fix -- the relay wiring now lives at the SOURCE OF TRUTH so any
  future legitimate re-run of this script (cadence tunes, trigger edits, etc.) can
  never again regress it:
    wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest\.venv\Scripts\pythonw.exe crypto_twin_health.py --live
  run_cmd_hidden.py runs the child SYNCHRONOUSLY and logs the real exit code to
  automation/state/logs/run-cmd-hidden-<date>.log (self_check.check_run_cmd_hidden_
  masked_exit already reads it every ~30min, zero further wiring needed). backtest-venv
  pythonw remains the INNER interpreter (crypto_twin_core imports exit_manager/
  risk_gate/crypto.lib.* and needs pandas); system pythonw is only the OUTER relay hop
  (stdlib-only, per run_cmd_hidden.py's own docstring either hop is safe -- system
  matches the other 18 already-migrated tasks' convention).

  CADENCE: `-Once` base trigger + `-RepetitionInterval 1min` (was 5min, see the
  2026-08-01 CADENCE-TUNE note above) + a ~10-year `-RepetitionDuration` -- the
  verified-live pattern (install-ccr-keepalive.ps1, matches
  Gamma_CryptoGrinderKeepalive's real NextRunTime behavior: recalculates every fire,
  never goes dark; this is NOT the one-time-trigger foot-gun where a trigger has no
  repetition set at all).

  To verify after running: Get-ScheduledTask -TaskName Gamma_CryptoTwin
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_CryptoTwin"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script       = Join-Path $root "setup\scripts\crypto_twin_health.py"

if (-not (Test-Path $sysPythonw))   { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $pythonwVenv))  { throw "backtest venv pythonw.exe not found at $pythonwVenv" }
if (-not (Test-Path $script))       { throw "crypto_twin_health.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest-venv pythonw crypto_twin_health.py --live
# (2026-08-07 fix -- see WIRING PATTERN note above: this is the durable, source-of-truth
# version of the relay fix fix-venv-pythonw-console-leak.ps1 applied imperatively on
# 2026-07-14 and this script's own re-registration silently undid on 2026-08-01.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonwVenv`" `"$script`" `"--live`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 1 min, 24/7 -- crypto never closes, no day/time restriction (unlike RTH tasks).
# CADENCE-TUNE 2026-08-01: was 5 min 2026-07-10..2026-07-31 -- see the docstring's
# CADENCE-TUNE block for the measured-latency + realized-vol evidence.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 1) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "CRYPTO TWIN -- 24/7 mechanism-validation training ground (J requirement 2026-07-10, markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md). Every 1 min, 24/7 (CADENCE-TUNE 2026-08-01, was 5 min -- see this script's docstring for the measured-latency + realized-vol evidence): crypto_twin_health.py --live wraps crypto_twin_core.run_tick() (SEE BTC/USD bars -> DECIDE ribbon+level trigger -> risk_gate -> ACT place -> manage exit_manager -> journal, T1/T2 tested 40/40) with error-capture, and writes automation/state/twin-health.json + automation/state/crypto-twin/soak-log.jsonl every tick (T3). T2's order path is LIVE (dedicated Alpaca paper account PA38EG1JTFBT, configured 2026-07-11). Reaper-exempt: pythonw.exe is outside Stop-StaleClaudeProcesses's Name filter, plus backtest\.venv path match as defense in depth (guard: test_crypto_twin_reaper_exemption.py). Built 2026-07-10, cadence-tuned 2026-08-01." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
