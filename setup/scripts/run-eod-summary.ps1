# EOD summary write -- fires at 16:00 ET weekdays.
# OP-30 FREE-TIER-FIRST: tries Nemotron/DeepSeek/MiniMax-free ladder first ($0).
# Only escalates to Claude if the entire free-tier ladder fails.
. "$PSScriptRoot\_shared.ps1"

$task = "eod-summary"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) { Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')" }

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss'))"
$todayDate = $et.ToString("yyyy-MM-dd")

# ── STEP 1: Free-tier primary (Nemotron → DeepSeek → MiniMax-free → MiniMax-paid) ──
Write-TaskLog -TaskName $task -Message "eod-summary: trying free-tier primary (Nemotron ladder)"
$freeTierResult = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\eod_fallback.py" `
    -ArgList @("--task", "eod-summary", "--date", $todayDate, "--primary") `
    -TaskName $task `
    -TimeoutSec 360

$exit = $freeTierResult.ExitCode
if ($exit -eq 0) {
    Write-TaskLog -TaskName $task -Message "eod-summary: free-tier PRIMARY OK"
} else {
    Write-TaskLog -TaskName $task -Message "eod-summary: free-tier failed exit=$exit -- escalating to Claude"
    # ── STEP 2: Claude fallback (only if entire free-tier ladder failed) ──
    # 8-min hard cap, medium effort. No FallbackScript -- free-tier was already the fallback.
    $exit = Invoke-ClaudeWithRetry `
        -PromptFile (Join-Path $WorkDir "automation\prompts\eod-summary.md") `
        -TaskName $task `
        -MaxBudgetUsd 4 `
        -TimeoutSec 480 `
        -Effort "medium" `
        -MaxRateLimitWaitSec 7200
}

# --- Karpathy data flywheel (NEW 2026-05-09) ---
# After Claude finishes the reflection, append today's bars to the canonical
# backtest dataset. This is pure Python (no LLM tokens) -- runs whether or not
# the EOD-summary itself succeeded. If append fails, Claude's pre-flight on
# tomorrow morning will surface stale-data warning via append-versions log.
$venvPython = Join-Path $WorkDir "backtest\.venv\Scripts\python.exe"
$appendScript = Join-Path $WorkDir "backtest\tools\append_today.py"
if ((Test-Path $venvPython) -and (Test-Path $appendScript)) {
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL invoking append_today.py"
    $appendOut = & $venvPython $appendScript 2>&1
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL output: $($appendOut -join ' | ')"
} else {
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL skipped (venv or script missing -- backfill manually)"
}

# Run state-validation post-flywheel so the next premarket inherits clean state.
# Repair-StateFiles is idempotent -- safe to call again here.
$postRepair = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "POST_FLYWHEEL_REPAIR validated=$($postRepair.Validated) restored=$($postRepair.Restored)"

exit $exit
