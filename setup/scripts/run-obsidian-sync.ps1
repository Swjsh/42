# Gamma_ObsidianSync -- render live firm state into the Obsidian vault (HOME.md + daily note).
#
# WHY: the repo root has been an Obsidian vault since 2026-07-09 and went unused because opening
# it showed 343 markdown files with no entry point, while J's standing complaint was that Gamma
# is invisible. This is the reading surface, not a note system -- nothing is filed by hand.
#
# Cadence: 16:45 ET weekdays (after Gamma_EodFlatten 15:55 and Gamma_WinnerAutopsy 16:25, so the
# daily note captures the settled book). Also safe to run ad hoc any time -- it is idempotent and
# only rewrites the frontmatter keys it owns plus the GAMMA-EOD marker block.
#
# Cost: $0 (pure Python + broker reads, no LLM). Places no orders. Reads only.
# Fails open: the Python entrypoint swallows its own exceptions and exits 0 by design, so a
# reporting failure can never cascade. Guard: backtest/tests/test_obsidian_vault_sync.py.

. "$PSScriptRoot\_shared.ps1"

$task = "obsidian-sync"
$et   = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }

$script = Join-Path $WorkDir "setup\scripts\obsidian_vault_sync.py"
if (-not (Test-Path $script)) {
    Write-TaskLog -TaskName $task -Message "MISSING_SCRIPT $script"
    exit 0
}

$r = Invoke-PythonHidden -ScriptPath $script -TaskName $task -TimeoutSec 300

$summary = ($r.Stdout -split "`n" | Where-Object { $_ -match "\[obsidian\]" }) -join " | "
Write-TaskLog -TaskName $task -Message "exit=$($r.ExitCode) $summary"

# Surface only genuine failure -- a clean run stays quiet (STATUS.md is for signal, not noise).
if ($r.ExitCode -ne 0 -or -not (Test-Path (Join-Path $WorkDir "HOME.md"))) {
    $statusMd = Join-Path $WorkDir "automation\overnight\STATUS.md"
    $line = "- [$($et.ToString('MM-dd HH:mm')) ET] ObsidianSync: exit=$($r.ExitCode), HOME.md missing or run failed"
    try { Add-Content -Path $statusMd -Value $line -Encoding utf8 } catch { }
}

exit 0
