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
  layers exist; only the first is now load-bearing for the actual tick process (see
  2026-09-03 CORRECTION below):
    1. PRIMARY (by construction, unconditional): 'pythonw.exe' is NOT in
       Stop-StaleClaudeProcesses's Win32_Process -Filter Name clause at all -- this
       task's spawned process (outer relay AND the inner crypto_twin_health.py child
       run_cmd_hidden.py spawns) is therefore never even fetched by the reaper's
       query, independent of EXEMPT_DAEMONS string matching or which pythonw binary
       is used. This is the ONLY protection the inner tick process gets today.
    2. DEFENSE IN DEPTH (OUTER hop only, since 2026-09-03 -- see correction below):
       the OUTER run_cmd_hidden.py relay process's own CommandLine contains the
       literal substring 'backtest\.venv' (via its `--env PYTHONPATH=...` argument),
       which IS one of $EXEMPT_DAEMONS's existing entries. The INNER child process
       run_cmd_hidden.py subprocess.run()s to actually execute crypto_twin_health.py
       does NOT carry that substring in its own CommandLine (its argv is just
       `<system-pythonw> crypto_twin_health.py --live`; PYTHONPATH is an env var, not
       an argv token) -- so layer 2 no longer covers the inner process either. If a
       future edit ever widens the Name filter to include pythonw.exe, layer 1 alone
       would no longer save this task -- that would need a real design change, not a
       config tweak, since neither hop's CommandLine reliably carries the marker for
       the process that actually matters.

  WIRING PATTERN (2026-09-03 CORRECTED -- VENV-PYTHONW-REDIRECTS-TO-CONSOLE-PYTHON,
  queue.md recipe (a), status:recipe-proven, root cause PANDAS-CONSOLE-LEAK-ROOT-CAUSE):
  backtest\.venv\Scripts\pythonw.exe is CPython's venvwlauncher redirector, but the
  venv's pyvenv.cfg records only a console `executable=` path (no GUI variant) --
  EVERY venv-pythonw launch of a script that imports pandas (crypto_twin_core does)
  re-execs the base install's CONSOLE python.exe internally and leaks a console-host
  window regardless of launcher mechanism or CREATE_NO_WINDOW (live-verified
  2026-09-03 on a sibling task, see install-fee-recalibrate.ps1's WIRING comment for
  the full investigation). Fix, already applied here (superseding the 2026-08-07
  relay-migration note this docstring used to carry): launch the BASE system
  pythonw.exe for BOTH hops and activate the backtest venv via environment
  (PYTHONPATH=backtest\.venv\Lib\site-packages) instead of via the venv's own
  launcher stub:
    wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
      --env PYTHONPATH=<repo>\backtest\.venv\Lib\site-packages
      -- SYSTEM pythonw crypto_twin_health.py --live
  There is no `$pythonwVenv` variable in this script (a prior version of this
  docstring described one; it was aspirational text that never matched the code even
  before the 2026-09-03 recipe existed -- see the FULL-SUITE-RED-TRIAGE-2026-09-10
  goal's disposition for backtest/tests/test_crypto_twin_reaper_exemption.py).
  run_cmd_hidden.py runs the child SYNCHRONOUSLY and logs the real exit code to
  automation/state/logs/run-cmd-hidden-<date>.log (self_check.check_run_cmd_hidden_
  masked_exit already reads it every ~30min, zero further wiring needed). Live-verified
  working (this goal, 2026-09-10): automation/state/twin-health.json shows 719 ticks
  today, soak-log.jsonl shows n_errors=0 across every rolling hour -- crypto_twin_core's
  pandas import resolves fine under this env-activation pattern in production.

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
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\crypto_twin_health.py"

if (-not (Test-Path $sysPythonw))   { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "crypto_twin_health.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> SYSTEM pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- backtest-venv pythonw crypto_twin_health.py --live
# (2026-08-07 fix -- see WIRING PATTERN note above: this is the durable, source-of-truth
# version of the relay fix fix-venv-pythonw-console-leak.ps1 applied imperatively on
# 2026-07-14 and this script's own re-registration silently undid on 2026-08-01.)
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" `"--live`""
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
    -Description "CRYPTO TWIN -- 24/7 mechanism-validation training ground (J requirement 2026-07-10, markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md). Every 1 min, 24/7 (CADENCE-TUNE 2026-08-01, was 5 min -- see this script's docstring for the measured-latency + realized-vol evidence): crypto_twin_health.py --live wraps crypto_twin_core.run_tick() (SEE BTC/USD bars -> DECIDE ribbon+level trigger -> risk_gate -> ACT place -> manage exit_manager -> journal, T1/T2 tested 40/40) with error-capture, and writes automation/state/twin-health.json + automation/state/crypto-twin/soak-log.jsonl every tick (T3). T2's order path is LIVE (dedicated Alpaca paper account PA38EG1JTFBT, configured 2026-07-11). Reaper-exempt: pythonw.exe is outside Stop-StaleClaudeProcesses's Name filter (the only protection the inner tick process has since the 2026-09-03 venv-pythonw-console-leak fix moved both hops onto system pythonw; guard: test_crypto_twin_reaper_exemption.py). Built 2026-07-10, cadence-tuned 2026-08-01." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
