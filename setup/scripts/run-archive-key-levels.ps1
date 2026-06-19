# run-archive-key-levels.ps1 -- Gamma_ArchiveKeyLevels wrapper
# Snapshots key-levels.json + today-bias.json into analysis/level-quality/snapshots/{date}/
# Idempotent: second run logs SKIP_EXISTS and exits 0.
# Proposed slot: 16:05 ET weekdays (see automation/state/SCHEDULED-TASKS.md).
#
# Per CLAUDE.md: engine-benefit instrumentation, ships without J ratification.
# Does NOT modify heartbeat.md, params*.json, or key-levels.json. Never places orders.

$ROOT    = "C:\Users\jackw\Desktop\42"
$SCRIPT  = "$ROOT\automation\scripts\archive_key_levels.py"
$PYTHON  = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe"
$LOG_DIR = "$ROOT\automation\logs"
$LOG     = "$LOG_DIR\archive-key-levels-$(Get-Date -Format 'yyyyMMdd').log"

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Force $LOG_DIR | Out-Null }

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LOG -Value "[$ts] Gamma_ArchiveKeyLevels starting"

try {
    & $PYTHON $SCRIPT *>> $LOG
    $ts2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LOG -Value "[$ts2] Gamma_ArchiveKeyLevels completed (exit $LASTEXITCODE)"
} catch {
    $ts2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LOG -Value "[$ts2] Gamma_ArchiveKeyLevels ERROR: $_"
    exit 1
}
