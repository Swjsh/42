#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_TrendCacheProducer -- daily 16:20 ET (after the close, before the
  16:30 vault sync) $0 extension of the trend-classification SPY-daily-bar cache
  (TREND-CLASSIFICATION-CACHE-STALE-SINCE-07-14, automation/overnight/queue.md).

.DESCRIPTION
  THE GAP THIS CLOSES: analysis/backtests/cache/trend-alignment-spy-daily-2024-07-01_
  2026-07-14.json is a FROZEN, untracked one-off build artifact (produced 2026-07-14 by
  backtest/tools/trend_alignment_correlation_study.py's --build-cache step, whose own
  FETCH_START/FETCH_END constants are pinned for THAT study's reproducibility and will
  never advance). Nothing has extended it since -- 269/403 (67%) real trades and all 6
  go-live-gate evidence days classify trend='unknown' via the guarded reader in
  backtest/tools/regime_conditioned_validation.py (the raw, unguarded classify_trend_asof
  would instead FABRICATE a plausible-looking trend for those dates -- verified).

  Runs setup/scripts/trend_cache_producer.py, which:
    - reads whatever cache regime_classifier.DAILY_SPY_CACHE currently resolves to for
      its EXISTING bars (the frozen file on day 1, its own prior output after that),
    - fetches ONLY a small overlapping tail via the SAME paginated Alpaca REST daily-bar
      pull trend_alignment_correlation_study.py's fetch_historical_bars uses (same
      credential loader, same URL shape -- no new vendor, $0, already-wired creds),
    - merges append-only (existing bars outside the fetch window survive byte-for-byte;
      fetched bars win only on a genuine timestamp overlap),
    - writes a NEW dated file `trend-alignment-spy-daily-2024-07-01_<END>.json` and
      updates the stable pointer `automation/state/trend-alignment-latest.json`,
    - NEVER writes to the frozen 2026-07-14 filename (explicit guard, raises loudly if
      that would ever happen -- this should be structurally impossible since "today" is
      always after 2026-07-14).

  NEVER redefines trend classification -- classify_trend_asof / RegimeCalendar in
  regime_classifier.py are untouched; this script produces DATA (daily OHLC bars), never
  a label. regime_classifier.py and regime_conditioned_validation.py were re-pointed
  (2026-09-03) to resolve the pointer file automatically, falling back to the frozen file
  if the pointer is absent -- so this task's FIRST fire (or any day it fails) degrades to
  exactly today's status quo, never a crash for downstream readers.

  WIRING PATTERN (flash-free, cloned from install-context-bundle.ps1 /
  install-crypto-twin.ps1's verified reaper-exempt shape):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- backtest\.venv\Scripts\pythonw.exe -> trend_cache_producer.py --once
  Uses the BACKTEST VENV pythonw (not system pythonw) because it needs the repo's own
  et_clock.py + context_bundle_producer.py imports via sys.path (pure stdlib otherwise --
  no pandas/numpy required) -- pythonw.exe also sits outside Stop-StaleClaudeProcesses's
  Win32_Process Name filter entirely, PLUS the backtest\.venv path substring matches an
  existing $EXEMPT_DAEMONS entry (defense in depth, same as the crypto twin tasks).

  TZ RULE: rig is Mountain (ET = local + 2h). -At is LOCAL. 14:20 MT = 16:20 ET, after
  the 15:55 ET EOD flatten and before the 16:30 ET Obsidian vault sync / first-live-day
  review, so the extended cache is on disk before either downstream consumer might read
  it same-day. A DAILY trigger, never one-time (project_scheduled_task_onetime_trigger_
  dark).

  Output:
    analysis/backtests/cache/trend-alignment-spy-daily-2024-07-01_<END>.json -- new cache
    automation/state/trend-alignment-latest.json -- pointer (readers repoint automatically)
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  Per CLAUDE.md OP-3 ($0, pure Python, reuses already-wired Alpaca creds), OP-25 (fail
  loud -- a failed fetch raises, leaving yesterday's cache/pointer untouched, never a
  partial write), OP-33 (visibility is the product -- prints the full result JSON).
  Guard: backtest/tests/test_trend_cache_producer_2026_09_03.py (13/13, 3-mutation
  RED-proofed).
  REVOKE: Unregister-ScheduledTask -TaskName Gamma_TrendCacheProducer -Confirm:$false
  (readers fall back to the frozen 2026-07-14 file automatically once the pointer is
  stale/missing -- no other file needs touching to revert).
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$pythonPath   = Join-Path $root "backtest\.venv\Lib\site-packages"
$script       = Join-Path $root "setup\scripts\trend_cache_producer.py"
$taskName     = "Gamma_TrendCacheProducer"

foreach ($p in @($vbs, $pythonwVenv, $runCmdHidden, $sysPythonw, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> vbs -> SYSTEM pythonw (hidden launcher) -> run_cmd_hidden.py -- BACKTEST VENV
# pythonw (reaper-exempt: outside Stop-StaleClaudeProcesses's Name filter + backtest\.venv
# path match, same verified pattern install-context-bundle.ps1/install-crypto-twin.ps1 use)
# -> trend_cache_producer.py --once
$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --env `"PYTHONPATH=$pythonPath`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`" --once"

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily 14:20 LOCAL (Mountain) = 16:20 ET -- after the 15:55 ET flatten, before the
# 16:30 ET vault sync / first-live-day review.
$trigger = New-ScheduledTaskTrigger -Daily -At "14:20"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Daily 16:20 ET `$0 extension of the frozen trend-classification SPY-" + `
    "daily-bar cache (TREND-CLASSIFICATION-CACHE-STALE-SINCE-07-14, queue.md). Reads the " + `
    "current cache, fetches only the missing tail via the SAME paginated Alpaca REST pull " + `
    "trend_alignment_correlation_study.py uses (no new vendor), writes a NEW dated file + " + `
    "updates automation/state/trend-alignment-latest.json. NEVER overwrites the frozen " + `
    "2026-07-14 artifact (explicit guard). Never redefines trend classification -- data " + `
    "only. Guard: backtest/tests/test_trend_cache_producer_2026_09_03.py (13/13). REVOKE: " + `
    "Unregister-ScheduledTask -TaskName Gamma_TrendCacheProducer -Confirm:`$false") `
    | Out-Null

Write-Host "[install] Registered $taskName -- daily 14:20 MT (16:20 ET)."
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | Format-Table -AutoSize
