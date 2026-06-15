# ============================================================================
# Project Gamma -- Parallel EOD Summary (Multi-Agent Gamma 2.0)
# ============================================================================
#
# Replaces run-eod-summary.ps1 with the orchestrator/worker pattern. The
# orchestrator prompt (eod-orchestrator.md) dispatches 4 parallel sub-agents
# via the Agent tool; sub-agents write JSON to automation/state/eod-workers/;
# orchestrator synthesizes the journal entry.
#
# Key differences from legacy:
#   - Single Claude invocation (parent orchestrator)
#   - Parent uses Agent tool to fan out to 4 workers in parallel
#   - Budget bumped from 4 USD to 6 USD (parent + 4 workers, each ~$1)
#   - Timeout bumped from 480s to 600s (allow chart-walks worker headroom)
#   - Workers write JSON; orchestrator merges (no live race conditions)
#
# Cost model (operating principle 3):
#   - Orchestrator + Worker A (metrics): ~$0.50
#   - Worker B (predictions): ~$0.50
#   - Worker C (chart-walks): ~$1.00 (heaviest, TradingView replays)
#   - Worker D (shadow + dark-pool): ~$0.50
#   - Total: ~$2.50/night = ~$55/mo (vs $80/mo monolithic) = NET SAVINGS
#
# Wall time: ~3 min (vs ~8 min monolithic), per Big Win #4 spec.
#
# Doctrine: docs/plans/multi-agent-gamma.md, Big Win #4
# ============================================================================

. "$PSScriptRoot\_shared.ps1"

$task = "eod-summary-parallel"
$et = Get-EtNow
if (-not (Test-WeekDay $et)) { exit 0 }
if (Test-HolidayFromAlpaca) { exit 0 }

# Reap stale processes (5+ min old). Same pattern as legacy.
$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

# Ensure worker output directory exists.
$workerDir = Join-Path $WorkDir "automation\state\eod-workers"
if (-not (Test-Path $workerDir)) {
    New-Item -ItemType Directory -Path $workerDir -Force | Out-Null
    Write-TaskLog -TaskName $task -Message "CREATED worker dir $workerDir"
}

# Clean any worker outputs from PRIOR days to avoid stale-read confusion.
# Keep today's (in case of mid-run restart we'd want resume-friendly behavior).
$today = $et.ToString("yyyy-MM-dd")
$prior = Get-ChildItem $workerDir -Filter "*.json" -ErrorAction SilentlyContinue | Where-Object {
    $_.Name -notmatch "^$today-"
}
if ($prior.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "PURGING $($prior.Count) prior-day worker JSONs"
    $prior | Remove-Item -Force -ErrorAction SilentlyContinue
}

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('HH:mm:ss')) workers_dir=$workerDir"

# Invoke orchestrator (parent agent). The parent uses Agent tool to fan out
# to workers. Parent budget covers all 4 workers via shared session billing.
$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\eod-orchestrator.md") `
    -TaskName $task `
    -MaxBudgetUsd 6 `
    -TimeoutSec 600 `
    -Effort "medium"

# Karpathy data flywheel (NEW 2026-05-09, preserved from legacy run-eod-summary.ps1)
$venvPython = Join-Path $WorkDir "backtest\.venv\Scripts\python.exe"
$appendScript = Join-Path $WorkDir "backtest\tools\append_today.py"
if ((Test-Path $venvPython) -and (Test-Path $appendScript)) {
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL invoking append_today.py"
    $appendOut = & $venvPython $appendScript 2>&1
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL output: $($appendOut -join ' | ')"
} else {
    Write-TaskLog -TaskName $task -Message "DATA_FLYWHEEL skipped (venv or script missing)"
}

# Post-flywheel state validation
$postRepair = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "POST_FLYWHEEL_REPAIR validated=$($postRepair.Validated) restored=$($postRepair.Restored)"

# Sanity check: did all 4 workers write outputs?
$expectedWorkers = @("metrics", "predictions", "chart-walks", "shadow-darkpool")
$missing = @()
foreach ($w in $expectedWorkers) {
    $expected = Join-Path $workerDir "$today-$w.json"
    if (-not (Test-Path $expected)) { $missing += $w }
}
if ($missing.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "WARN missing worker outputs: $($missing -join ',')"
} else {
    Write-TaskLog -TaskName $task -Message "OK all 4 worker outputs present"
}

exit $exit
