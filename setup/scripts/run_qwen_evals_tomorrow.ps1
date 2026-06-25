# Run Qwen cold evals after daily quota reset.
# Qwen's OpenRouter RPD was exhausted 2026-06-24 from retried runs.
# Run this script after midnight or next morning before market hours.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\run_qwen_evals_tomorrow.ps1"

$REPO = "C:\Users\jackw\Desktop\42"
$PYTHON = "$REPO\backtest\.venv\Scripts\python.exe"
$RUNNER = "$REPO\setup\scripts\run_cold_evals.py"

Write-Host "Qwen cold eval batch — dates with clean DT coverage"
Write-Host "Sleep: 62s between DT calls (new sleep_s), 90s between dates"
Write-Host ""

& $PYTHON $RUNNER `
  --models qwen `
  --dates 2026-05-07 2026-05-20 2026-06-24 `
  --clear

Write-Host ""
Write-Host "Done. Check analysis/shadow-model/qwen/ for scorecards."
Write-Host "05-19 already clean (2/2 = 100%) — no need to re-run."
