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

# --- Per-setup performance recompute (R-0007 fix) -- deterministic, runs on EVERY EOD path ---
# The free-tier EOD migration silently dropped the LLM Step-8 recompute, freezing
# setup-performance.json for ~37 days. This pure-Python regen keeps the deployment
# gate (>=20 trades, hit_rate>=0.45) reading REAL per-setup stats. $0, no LLM.
$setupPerfScript = Join-Path $WorkDir "backtest\scripts\update_setup_performance.py"
if ((Test-Path $venvPython) -and (Test-Path $setupPerfScript)) {
    Write-TaskLog -TaskName $task -Message "SETUP_PERF invoking update_setup_performance.py"
    $perfOut = & $venvPython $setupPerfScript 2>&1
    Write-TaskLog -TaskName $task -Message "SETUP_PERF output: $($perfOut -join ' | ')"
} else {
    Write-TaskLog -TaskName $task -Message "SETUP_PERF skipped (venv or script missing)"
}

# --- Decision grading (R-0008 fix) -- deterministic, runs on EVERY EOD path ---
# decision_grade was null on ~100% of rows for 5 weeks (the LLM hand-edit step never
# fired on the free-tier path). This pure-Python grader walks SPY 30min forward from
# each ungraded heartbeat decision and writes correct/wrong/ambiguous in place. $0, no LLM.
$gradeScript = Join-Path $WorkDir "setup\scripts\grade_decisions.py"
if ((Test-Path $venvPython) -and (Test-Path $gradeScript)) {
    Write-TaskLog -TaskName $task -Message "DECISION_GRADING invoking grade_decisions.py"
    $gradeOut = & $venvPython $gradeScript "--date" $todayDate 2>&1
    Write-TaskLog -TaskName $task -Message "DECISION_GRADING output: $($gradeOut -join ' | ')"
} else {
    Write-TaskLog -TaskName $task -Message "DECISION_GRADING skipped (venv or script missing)"
}

# --- Shadow model eval (Karpathy outer-loop re-activation) -- $0 free-tier, READ-ONLY, post-close ---
# System B: re-scores today's ticks under the free-tier Nemotron model -> shadow-model-decisions.jsonl.
# EOD-summary 8c diffs it into the 5-of-7 auto-ratify verdict. Runs LAST + hidden + bounded so it never
# delays the deterministic fixes above (partial runs still write incrementally). Never touches live
# params or the order path -- the model-shadow has hard $0 ceiling + no order imports by construction.
$shadowScript = Join-Path $WorkDir "setup\scripts\shadow_model_eval.py"
if (Test-Path $shadowScript) {
    Write-TaskLog -TaskName $task -Message "SHADOW_EVAL invoking shadow_model_eval.py (free-tier, read-only)"
    $shadowResult = Invoke-PythonHidden `
        -ScriptPath "setup\scripts\shadow_model_eval.py" `
        -ArgList @("--date", $todayDate, "--account", "both") `
        -TaskName $task `
        -TimeoutSec 240
    Write-TaskLog -TaskName $task -Message "SHADOW_EVAL exit=$($shadowResult.ExitCode)"
} else {
    Write-TaskLog -TaskName $task -Message "SHADOW_EVAL skipped (script missing)"
}

# Run state-validation post-flywheel so the next premarket inherits clean state.
# Repair-StateFiles is idempotent -- safe to call again here.
$postRepair = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "POST_FLYWHEEL_REPAIR validated=$($postRepair.Validated) restored=$($postRepair.Restored)"

exit $exit
