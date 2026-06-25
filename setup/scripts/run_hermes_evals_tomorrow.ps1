# Run Hermes cold eval for 06-24 after daily quota reset.
# Hermes daily quota exhausted 2026-06-24 from runs across 4 dates.
# 05-19 (2/2=100%), 05-07 (2/2=100%), 05-20 (1/1=100%) are CLEAN — do NOT re-run.
# Only 06-24 (7 DTs, all HOLD_DEV bear=8) needs re-run.
#
# Usage:
#   & "C:\Users\jackw\Desktop\42\setup\scripts\run_hermes_evals_tomorrow.ps1"

$REPO = "C:\Users\jackw\Desktop\42"
$PYTHON = "$REPO\backtest\.venv\Scripts\python.exe"
$RUNNER = "$REPO\setup\scripts\run_cold_evals.py"

Write-Host "Hermes cold eval — 06-24 only (quota reset run)"
Write-Host "Sleep: 90s between DT calls (sleep_s), 120s between dates (not needed, single date)"
Write-Host ""

& $PYTHON $RUNNER `
  --models hermes `
  --dates 2026-06-24 `
  --clear

Write-Host ""
Write-Host "Done. Check analysis/shadow-model/hermes/2026-06-24-scorecard.md"
