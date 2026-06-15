# Register Gamma_GhostOrderReconciler scheduled task.
# Per OP-27 L42 canonical chain: wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> ps1

$taskName = "Gamma_GhostOrderReconciler"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$vbs = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$launcher = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$ps1 = "C:\Users\jackw\Desktop\42\setup\scripts\run-ghost-reconciler.ps1"

$argString = '//nologo "{0}" "{1}" "{2}" "{3}"' -f $vbs, $pyw, $launcher, $ps1
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $argString

# Build trigger: daily at 09:30 ET, repeat every 1 min for 6h25m (covers 09:30-15:55)
$startTime = (Get-Date).Date.AddHours(9).AddMinutes(30)
$trigger = New-ScheduledTaskTrigger -Daily -At $startTime
$rep = New-ScheduledTaskTrigger -Once -At $startTime -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 25)
$trigger.Repetition = $rep.Repetition

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Unregistered existing $taskName"
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Ghost order reconciler -- detects ENTER decisions without matching Alpaca orders. Alert-only V1 per OP-21. Shipped 2026-05-22 09:30 ET per J directive."

$t = Get-ScheduledTask -TaskName $taskName
$info = $t | Get-ScheduledTaskInfo
$trig = $t.Triggers | Select-Object -First 1
$nextRun = $info.NextRunTime
$repInt = if ($trig.Repetition) { $trig.Repetition.Interval } else { "ONCE" }
Write-Host ("VERIFIED: state=" + $t.State + " repeat=" + $repInt + " nextRun=" + $nextRun)
