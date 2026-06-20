# overnight-health-check.ps1
# Run this in the morning to instantly diagnose the overnight harness.
# Usage: pwsh setup\scripts\overnight-health-check.ps1

$ErrorActionPreference = 'Continue'
$repo = 'C:\Users\jackw\Desktop\42'

Write-Output ""
Write-Output "================================================================"
Write-Output "  GAMMA OVERNIGHT HARNESS - HEALTH CHECK"
$now = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Write-Output "  Time: $now"
Write-Output "================================================================"

# 1. STATUS.md freshness
Write-Output ""
Write-Output "[1/6] STATUS.md freshness"
$statusFile = Join-Path $repo 'automation\overnight\STATUS.md'
if (Test-Path $statusFile) {
    $lastWrite = (Get-Item $statusFile).LastWriteTime
    $age = (Get-Date) - $lastWrite
    $ageMin = [int]$age.TotalMinutes
    if ($ageMin -lt 90) {
        Write-Output "  [OK]   Updated $ageMin min ago"
    } else {
        $ageHr = [int]$age.TotalHours
        Write-Output "  [RED]  STALE - last update $ageHr h $($ageMin % 60) min ago. Harness likely died."
    }
    Write-Output "  --- first 30 lines ---"
    Get-Content $statusFile -TotalCount 30 | ForEach-Object { Write-Output "    $_" }
} else {
    Write-Output "  [RED]  STATUS.md MISSING - harness never bootstrapped"
}

# 2. Sniper PIDs
Write-Output ""
Write-Output "[2/6] Sniper grinder PIDs"
$pidsToCheck = @(
    @{ Name = 'Stage1 grinder'; Pid = 19876 }
    @{ Name = 'Pipeline orchestrator'; Pid = 14808 }
)
foreach ($entry in $pidsToCheck) {
    $name = $entry.Name
    $checkPid = $entry.Pid
    $proc = Get-Process -Id $checkPid -ErrorAction SilentlyContinue
    if ($proc) {
        $mb = [int]($proc.WorkingSet64 / 1MB)
        Write-Output "  [OK]   $name PID=$checkPid alive ($mb MB)"
    } else {
        Write-Output "  [???]  $name PID=$checkPid not running (may be expected if pipeline complete)"
    }
}

# 3. Sniper progress
Write-Output ""
Write-Output "[3/6] Sniper Stage 1 progress"
$progressFile = Join-Path $repo 'backtest\autoresearch\_state\sniper_stage1\progress.json'
if (Test-Path $progressFile) {
    $p = Get-Content $progressFile -Raw | ConvertFrom-Json
    $pct = if ($p.total_combos -gt 0) { [int]($p.completed * 100 / $p.total_combos) } else { 0 }
    Write-Output "  Status:    $($p.status)"
    Write-Output "  Combos:    $($p.completed)/$($p.total_combos) ($pct percent)"
    Write-Output "  Passed:    $($p.passed_floors)"
    Write-Output "  Keepers:   $($p.keepers)"
    Write-Output "  Best wide: `$$($p.best_wide_pnl)"
    Write-Output "  Best edge: `$$($p.best_edge_capture)"
} else {
    Write-Output "  [???]  progress.json missing"
}

# 4. Pipeline log tail
Write-Output ""
Write-Output "[4/6] Pipeline log (last 5 lines)"
$pipeLog = Join-Path $repo 'backtest\autoresearch\_state\sniper_pipeline\pipeline.log'
if (Test-Path $pipeLog) {
    Get-Content $pipeLog -Tail 5 | ForEach-Object { Write-Output "  $_" }
} else {
    Write-Output "  [???]  pipeline.log missing"
}

# 5. Sniper scorecard + morning brief
Write-Output ""
Write-Output "[5/6] Final outputs"
$scorecard = Join-Path $repo 'analysis\recommendations\sniper-v1.json'
$morningBrief = Join-Path $repo 'markdown\research\SNIPER-MORNING-BRIEF.md'
$consolidated = Join-Path $repo 'docs\MORNING-BRIEF-2026-05-13.md'
if (Test-Path $scorecard) {
    Write-Output "  [OK]   sniper-v1.json EXISTS"
    $sc = Get-Content $scorecard -Raw | ConvertFrom-Json
    if ($sc.summary_metrics) {
        Write-Output "         edge_capture: `$$($sc.summary_metrics.edge_capture)"
        Write-Output "         wide_pnl:     `$$($sc.summary_metrics.wide_pnl)"
        Write-Output "         wide_n:       $($sc.summary_metrics.wide_n_trades)"
        Write-Output "         wide_wr:      $($sc.summary_metrics.wide_wr)"
    }
} else {
    Write-Output "  [???]  sniper-v1.json missing"
}
if (Test-Path $morningBrief) {
    Write-Output "  [OK]   markdown\research\SNIPER-MORNING-BRIEF.md EXISTS"
} else {
    Write-Output "  [???]  markdown\research\SNIPER-MORNING-BRIEF.md missing"
}
if (Test-Path $consolidated) {
    Write-Output "  [OK]   docs\MORNING-BRIEF-2026-05-13.md EXISTS"
} else {
    Write-Output "  [???]  docs\MORNING-BRIEF-2026-05-13.md missing (final 06:55 fire didn't run)"
}

# 6. Wake fires summary
Write-Output ""
Write-Output "[6/7] Wake fires summary"
$wakeLog = Join-Path $repo 'automation\overnight\log.md'
if (Test-Path $wakeLog) {
    $entries = Get-Content $wakeLog | Where-Object { $_ -match '^\d{4}-\d{2}-\d{2}T' }
    Write-Output "  Total entries in log.md: $($entries.Count)"
    Write-Output "  --- last 5 entries ---"
    $entries | Select-Object -Last 5 | ForEach-Object { Write-Output "    $_" }
} else {
    Write-Output "  [???]  log.md missing"
}

# 7. Keepers tally across all grinders (T26 — added 2026-05-13)
Write-Output ""
Write-Output "[7/7] Keepers tally across all grinders"
$stateDir = Join-Path $repo 'backtest\autoresearch\_state'
$grinders = @(
    @{Name='sniper_stage1'; Path='sniper_stage1\keepers.jsonl'},
    @{Name='sniper_stage2'; Path='sniper_stage2\keepers.jsonl'},
    @{Name='sniper_stages345'; Path='sniper_stages345\stage4_keepers.jsonl'},
    @{Name='v14_enhanced_stage1'; Path='v14_enhanced_stage1\keepers.jsonl'},
    @{Name='vwap_stage1'; Path='vwap_stage1\keepers.jsonl'},
    @{Name='opening_drive_fade_stage1'; Path='opening_drive_fade_stage1\keepers.jsonl'}
)
foreach ($g in $grinders) {
    $full = Join-Path $stateDir $g.Path
    if (Test-Path $full) {
        $lines = Get-Content $full -ErrorAction SilentlyContinue
        $count = if ($lines) { ($lines | Measure-Object).Count } else { 0 }
        if ($count -gt 0) {
            # Parse last keeper to show top metrics
            try {
                $latest = $lines | Select-Object -Last 1 | ConvertFrom-Json
                $edge = if ($latest.edge_capture) { $latest.edge_capture } else { 'n/a' }
                $wide = if ($latest.wide_pnl) { $latest.wide_pnl } else { 'n/a' }
                $wr = if ($latest.wide_wr) { $latest.wide_wr } else { 'n/a' }
                Write-Output "  [$($g.Name)] keepers=$count  latest: edge=`$$edge wide=`$$wide wr=$wr"
            } catch {
                Write-Output "  [$($g.Name)] keepers=$count (parse error on latest)"
            }
        } else {
            Write-Output "  [$($g.Name)] keepers=0"
        }
    } else {
        Write-Output "  [$($g.Name)] keepers.jsonl missing (not yet produced)"
    }
}

Write-Output ""
Write-Output "================================================================"
Write-Output "  KEY FILES TO READ:"
Write-Output "    1. automation\overnight\STATUS.md       (current health)"
Write-Output "    2. automation\overnight\queue.md        (what's done/pending)"
Write-Output "    3. automation\overnight\log.md          (wake-by-wake history)"
Write-Output "    4. markdown\research\SNIPER-MORNING-BRIEF.md         (sniper results)"
Write-Output "    5. analysis\recommendations\sniper-v1.json  (scorecard)"
Write-Output "    6. docs\MORNING-BRIEF-2026-05-13.md     (consolidated brief)"
Write-Output "================================================================"
Write-Output ""
