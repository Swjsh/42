# One-shot vwap_continuation strategy-family pipeline: grind -> funnel -> consolidation.
#
# Launched hidden via the OP-27 L42 zero-leak chain
#   (wscript -> run_exe_hidden.vbs -> pythonw -> run_ps1_hidden.py -> THIS).
#
# Adds the SECOND family to the strategy table (the first grind covered only the ribbon
# rejection/reclaim entry). SINGLE 8-worker grind process — do NOT shard into multiple
# processes; concurrent grind processes deadlock on the OPRA cache (CLAUDE.md grind-reaper
# lesson). The backtest .venv interpreter is reaper-EXEMPT (_shared.ps1 EXEMPT_DAEMONS).
#
# Re-run is safe: the grind RESUMES from mass-grind-vwap-progress*.jsonl (skips done cells);
# for a clean re-grind, delete those files first. Real OPRA fills only (C1). $0 (pure Python).
param()
$ErrorActionPreference = "Continue"

$python  = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
$workdir = "C:\Users\jackw\Desktop\42\backtest"
$reco    = "C:\Users\jackw\Desktop\42\analysis\recommendations"
$log     = Join-Path $reco "grind-vwap-pipeline.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Add-Content $log
}

$env:GAMMA_GRIND_WORKERS = "8"
$env:PYTHONPATH = $workdir
Set-Location $workdir

Write-Log "=== vwap pipeline START (workers=$($env:GAMMA_GRIND_WORKERS)) ==="

Write-Log "Stage 1/3: grind (mass_grind_vwap, 8 workers, single process)"
& $python -m autoresearch.mass_grind_vwap *> (Join-Path $reco "mass-grind-vwap-stdout.log")
Write-Log "Stage 1 (grind) exit=$LASTEXITCODE"

Write-Log "Stage 2/3: funnel (mass_grind_vwap_funnel, P2->P3->P4)"
& $python -m autoresearch.mass_grind_vwap_funnel *> (Join-Path $reco "mass-grind-vwap-funnel-stdout.log")
Write-Log "Stage 2 (funnel) exit=$LASTEXITCODE"

Write-Log "Stage 3/3: consolidation (consolidate_elites_vwap)"
& $python -m autoresearch.consolidate_elites_vwap *> (Join-Path $reco "consolidate-vwap-stdout.log")
Write-Log "Stage 3 (consolidate) exit=$LASTEXITCODE"

Write-Log "=== vwap pipeline DONE ==="
