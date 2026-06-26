# Grind + funnel watchdog (Gamma_Grind_Watchdog, every 60s). Self-healing + auto-scaling:
#  - keeps the single Gamma_Grind_all task alive until all 3360 combos are done;
#  - keeps the validation-funnel workers (Gamma_Funnel_0..5) alive while bangers remain
#    unreviewed, and SCALES them: 2 workers while the grind still holds the cores, 6 once
#    the grind is complete and the full machine is free.
# Resume/dedup in each tool means a restart never loses or re-does work.
$reco = "C:\Users\jackw\Desktop\42\analysis\recommendations"
$log  = "$reco\mass-grind-watchdog.log"
function WLog($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Add-Content $log }

# --- grind progress (union of all progress shards) ---
$union = 0
Get-ChildItem "$reco\mass-grind-progress*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    $union += (Get-Content $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
}
# Dynamic matrix total (the grind writes it; falls back to the original 3360).
$gtotal = 3360
try { $gtotal = [int](Get-Content "$reco\mass-grind-total.json" -Raw | ConvertFrom-Json).total } catch {}
$grindDone = $union -ge $gtotal

if (-not $grindDone) {
    $state = (Get-ScheduledTask -TaskName 'Gamma_Grind_all' -ErrorAction SilentlyContinue).State
    if ($state -ne 'Running') {
        Start-ScheduledTask -TaskName 'Gamma_Grind_all' -ErrorAction SilentlyContinue
        WLog ("RESTART Gamma_Grind_all union={0} of 3360 was {1}" -f $union, $state)
    }
}

# --- funnel: keep the active worker set alive while bangers remain unreviewed ---
$bangers = 0
Get-ChildItem "$reco\mass-grind-progress*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    Get-Content $_.FullName -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_ -match '"edge_capture":\s*([0-9.]+)' -and [double]$matches[1] -ge 771 -and $_ -match '"op16_reject":\s*false' -and $_ -match '"wf":\s*([0-9.]+)' -and [double]$matches[1] -ge 0.70) { $bangers++ }
    }
}
$reviewed = 0
Get-ChildItem "$reco\mass-grind-funnel-*.jsonl" -ErrorAction SilentlyContinue | ForEach-Object {
    $reviewed += (Get-Content $_.FullName -ErrorAction SilentlyContinue | Measure-Object -Line).Lines
}

# Active funnel shards: 2 while grind runs (cores busy), all 6 once grind is done.
$activeShards = if ($grindDone) { 0, 1, 2, 3, 4, 5 } else { 0, 1 }

if ($reviewed -lt $bangers -or $bangers -eq 0) {
    foreach ($s in $activeShards) {
        $task = "Gamma_Funnel_$s"
        $state = (Get-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue).State
        if ($state -and $state -ne 'Running') {
            Start-ScheduledTask -TaskName $task -ErrorAction SilentlyContinue
            WLog ("START {0} reviewed={1} of {2} bangers grindDone={3} was {4}" -f $task, $reviewed, $bangers, $grindDone, $state)
        }
    }
}

if ($grindDone -and $bangers -gt 0 -and $reviewed -ge $bangers) {
    WLog ("COMPLETE grind={0}/{1} funnel={2}/{3} - running consolidation + phase5 + disabling watchdog" -f $union, $gtotal, $reviewed, $bangers)
    $py = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
    $wd = "C:\Users\jackw\Desktop\42\backtest"
    # Final consolidation: P4 elites -> distinct setups -> deploy shortlist.
    try {
        Start-Process -FilePath $py -ArgumentList "-m", "autoresearch.consolidate_elites" -WorkingDirectory $wd -WindowStyle Hidden -Wait
        WLog "consolidation done -> elite-consolidation.json"
    } catch { WLog ("consolidation FAILED: " + $_.Exception.Message) }
    # Phase 5: the deploy-grade gate (neighborhood plateau + every-quarter-positive).
    try {
        Start-Process -FilePath $py -ArgumentList "-m", "autoresearch.mass_grind_phase5" -WorkingDirectory $wd -WindowStyle Hidden -Wait
        WLog "phase5 done -> mass-grind-phase5-summary.json"
    } catch { WLog ("phase5 FAILED: " + $_.Exception.Message) }
    Disable-ScheduledTask -TaskName 'Gamma_Grind_Watchdog' -ErrorAction SilentlyContinue | Out-Null
}
