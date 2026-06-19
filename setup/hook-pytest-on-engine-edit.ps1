#!/usr/bin/env pwsh
# hook-pytest-on-engine-edit.ps1 - PostToolUse hook (NON-BLOCKING).
#
# When Claude edits ENGINE / WATCHER / VALIDATOR .py code, kick off the fast
# graduated-guards regression suite (`-m "not slow"`, see guard_runner.py) IN THE
# BACKGROUND, then return instantly. The slow, data-heavy guards (full backtests)
# are excluded from the per-edit run so it can never time out / false-block an edit;
# they run nightly / on demand via `-m slow`.
# This box runs 9+ always-on python daemons, so a synchronous pytest run would
# block the user for minutes - which violates the highest-priority "never disturb
# the user" rule. So instead:
#
#   * On this edit: surface the PREVIOUS run's result if it FAILED (deferred signal),
#     then (if no run is already in flight) launch a fresh headless guard run.
#   * The background runner (setup/guard_runner.py) writes the verdict to
#     automation/state/guard-watch.json and self-clears its lock.
#
# Net effect: the user is never blocked, but a regression surfaces LOUDLY within
# an edit or two (exit 2 routes the failure summary back to Claude to fix).
# Per CLAUDE.md OP-25 (silent failure is the only true failure) + lesson C8
# (headless Windows spawn). Never edits code, never places orders.

$ErrorActionPreference = "Continue"
$ROOT  = "C:\Users\jackw\Desktop\42"
$STATE = Join-Path $ROOT "automation\state"
$WATCH = Join-Path $STATE "guard-watch.json"
$LOCK  = Join-Path $STATE ".guard-watch.lock"

# --- parse hook payload ---
$raw = [Console]::In.ReadToEnd()
if (-not $raw) { exit 0 }
try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }
$fp = $null
if ($payload.tool_input -and $payload.tool_input.file_path) { $fp = "$($payload.tool_input.file_path)" }
if (-not $fp) { exit 0 }
$norm = $fp.Replace("\", "/")

# --- only fire on engine / watcher / validator .py code ---
if (-not ($norm -match "\.py$")) { exit 0 }
$engineGlobs = @("backtest/lib/", "backtest/autoresearch/", "crypto/validators/")
$isEngine = $false
foreach ($g in $engineGlobs) { if ($norm -like "*$g*") { $isEngine = $true; break } }
if (-not $isEngine) { exit 0 }

# --- 1. surface a prior FAILED run (deferred signal), once ---
if (Test-Path $WATCH) {
    try {
        $w = Get-Content $WATCH -Raw | ConvertFrom-Json
        if (($w.status -eq "fail" -or $w.status -eq "error" -or $w.status -eq "timeout") -and (-not $w.surfaced)) {
            $w.surfaced = $true
            # .NET WriteAllText = UTF-8 without BOM (PS 5.1 Set-Content -Encoding UTF8 adds a
            # BOM that breaks python json.load consumers of guard-watch.json).
            [System.IO.File]::WriteAllText($WATCH, ($w | ConvertTo-Json -Depth 6))
            [Console]::Error.WriteLine("GRADUATED-GUARDS regression detected (from edit to $($w.edited_file)): $($w.summary)")
            if ($w.tail) { [Console]::Error.WriteLine(($w.tail -join "`n")) }
            [Console]::Error.WriteLine("Fix before continuing. Re-run (fast): cd backtest; python -m pytest tests/test_graduated_guards.py -m 'not slow' -q")
            # still launch a fresh run below? No - let the fix land first. Exit now.
            exit 2
        }
    } catch { }
}

# --- 2. don't pile on if a run is already in flight ---
if (Test-Path $LOCK) {
    try {
        $lpid = (Get-Content $LOCK -Raw).Trim()
        if ($lpid -and (Get-Process -Id $lpid -ErrorAction SilentlyContinue)) { exit 0 }
    } catch { }
}

# --- 3. launch a fresh headless guard run (no window, fully detached) ---
try {
    $proc = Start-Process -FilePath "pythonw" `
        -ArgumentList @((Join-Path $ROOT "setup\guard_runner.py"), $norm) `
        -WindowStyle Hidden -PassThru
    Set-Content -Path $LOCK -Value $proc.Id -Encoding ASCII
} catch {
    # if spawn fails, stay silent - this is a best-effort guard, not a blocker
}
exit 0
