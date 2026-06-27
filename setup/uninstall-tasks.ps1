# Uninstall-tasks.ps1 — removes all Gamma_* tasks from Task Scheduler.

$ErrorActionPreference = "Continue"

$tasks = @(
    "Gamma_LaunchTV",
    "Gamma_Premarket",
    "Gamma_Heartbeat",
    "Gamma_EodFlatten",
    "Gamma_EodSummary",
    "Gamma_DailyReview",
    "Gamma_WeeklyReview",
    "Gamma_Heartbeat_Aggressive",
    "Gamma_EodFlatten_Aggressive"
)

foreach ($t in $tasks) {
    try {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction Stop
        Write-Host "  Removed: $t"
    } catch {
        Write-Host "  (not present): $t"
    }
}

Write-Host ""
Write-Host "Uninstalled. Re-register via the per-task installers in automation\state\SCHEDULED-TASKS.md"
Write-Host "(install-tasks.ps1 was RETIRED 2026-06-27 - it registered a stale 2h-late chain)."
