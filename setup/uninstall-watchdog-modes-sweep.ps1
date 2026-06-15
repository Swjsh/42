# Unregister the autoresearch watchdog scheduled task.

$TaskName = "Gamma_AR_Watchdog"
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Unregistered $TaskName (if it existed)" -ForegroundColor Yellow
