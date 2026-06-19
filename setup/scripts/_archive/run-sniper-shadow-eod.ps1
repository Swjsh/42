# run-sniper-shadow-eod.ps1 -- Gamma_SniperShadowEOD wrapper
# Runs the SNIPER shadow EOD watcher to build J's OP-16 anchor dataset.
# Scheduled: 16:05 ET weekdays.
#
# Per CLAUDE.md: engine-benefit infrastructure, ships without J ratification.
# Does NOT modify heartbeat.md or params*.json. Never places orders.

$ROOT    = "C:\Users\jackw\Desktop\42"
$SCRIPT  = "$ROOT\automation\scripts\sniper_shadow_eod.py"
$PYTHON  = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe"
$LOG_DIR = "$ROOT\automation\logs"
$LOG     = "$LOG_DIR\sniper-shadow-eod-$(Get-Date -Format 'yyyyMMdd').log"

if (-not (Test-Path $LOG_DIR)) { New-Item -ItemType Directory -Force $LOG_DIR | Out-Null }

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $LOG -Value "[$ts] Gamma_SniperShadowEOD starting"

try {
    & $PYTHON $SCRIPT --days 30 *>> $LOG
    $ts2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LOG -Value "[$ts2] Gamma_SniperShadowEOD completed (exit $LASTEXITCODE)"
} catch {
    $ts2 = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LOG -Value "[$ts2] Gamma_SniperShadowEOD ERROR: $_"
    exit 1
}
