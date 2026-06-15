# prune-crypto-hoard.ps1 - enforce OP-G footprint cap on the crypto scorecard hoard.
#
# Deep-Review H6: crypto/data/scorecards/ is a 1.6 GB write-only hoard - grinder.jsonl
# grows unbounded (~212 MB) and ~13 daily archives (~1.5 GB) are never pruned, and
# NOTHING reads them. This caps the live file and prunes old archives.
#
# DRY-RUN BY DEFAULT (CLAUDE.md mandate: trace every file before deleting). Review the
# output, then re-run with -Execute. Deletes go to a quarantine dir first (two-step),
# never a raw rm. Run on Windows (the Cowork mount forbids deletes - L78). PS 5.1, ASCII.

param(
    [switch]$Execute,                 # without this, only PRINTS what it would do
    [int]$LiveCapMB = 50,             # cap grinder.jsonl at this size (keep newest lines)
    [int]$KeepArchives = 2            # keep this many most-recent archive files
)

$ErrorActionPreference = "Stop"
$scorecards = "C:\Users\jackw\Desktop\42\crypto\data\scorecards"
$quarantine = "C:\Users\jackw\Desktop\42\crypto\data\_quarantine_prune"

if (-not (Test-Path $scorecards)) {
    Write-Host "No scorecards dir at $scorecards - nothing to do."
    exit 0
}

$mode = if ($Execute) { "EXECUTE" } else { "DRY-RUN (re-run with -Execute to apply)" }
Write-Host "=== prune-crypto-hoard [$mode] ==="

# 1. Archives: keep the N most recent, quarantine the rest.
$archives = Get-ChildItem $scorecards -Filter "grinder-archive-*.jsonl" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending
if ($archives) {
    $toPrune = $archives | Select-Object -Skip $KeepArchives
    $freed = ($toPrune | Measure-Object Length -Sum).Sum / 1MB
    Write-Host ("Archives: {0} total, keeping {1} newest, pruning {2} (~{3:N0} MB)" -f $archives.Count, $KeepArchives, $toPrune.Count, $freed)
    foreach ($f in $toPrune) {
        Write-Host ("  prune: {0} ({1:N0} MB)" -f $f.Name, ($f.Length / 1MB))
        if ($Execute) {
            if (-not (Test-Path $quarantine)) { New-Item -ItemType Directory -Path $quarantine | Out-Null }
            Move-Item $f.FullName (Join-Path $quarantine $f.Name) -Force
        }
    }
} else {
    Write-Host "Archives: none found."
}

# 2. Live grinder.jsonl: if over the cap, keep only the newest lines that fit.
$live = Join-Path $scorecards "grinder.jsonl"
if (Test-Path $live) {
    $sizeMB = (Get-Item $live).Length / 1MB
    Write-Host ("Live grinder.jsonl: {0:N0} MB (cap {1} MB)" -f $sizeMB, $LiveCapMB)
    if ($sizeMB -gt $LiveCapMB) {
        # Estimate how many trailing lines fit in the cap.
        $total = (Get-Content $live -ReadCount 0).Count
        $keep = [math]::Max(1000, [int]($total * ($LiveCapMB / $sizeMB)))
        Write-Host ("  over cap: would keep newest ~{0} of {1} lines" -f $keep, $total)
        if ($Execute) {
            $tail = Get-Content $live -Tail $keep
            $tmp = "$live.tmp"
            Set-Content $tmp $tail -Encoding UTF8
            Move-Item $tmp $live -Force
            Write-Host "  trimmed."
        }
    }
} else {
    Write-Host "Live grinder.jsonl: not present."
}

Write-Host ""
Write-Host "NOTE: the durable fix is to stop the 24/7 crypto grinder writing raw bar windows"
Write-Host "at all (Deep-Review: keep crypto/lib, retire the always-on validator as a pre-merge"
Write-Host "gate). Disable its scheduled task via: Get-ScheduledTask -TaskName 'Gamma_*Crypto*' |"
Write-Host "Disable-ScheduledTask  (confirm the exact name in automation/state/SCHEDULED-TASKS.md first)."
if ($Execute) { Write-Host "`nQuarantined files are in $quarantine - delete after you confirm nothing broke." }
exit 0
