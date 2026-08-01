# Register Gamma_FleetExecutor scheduled task.
# Per OP-27 L42 canonical chain: wscript -> run_exe_hidden.vbs -> sys-pythonw -> run_ps1_hidden.py -> ps1
#
# TIMEZONE (project_scheduled_task_tz foot-gun): the rig is Mountain. To fire at
# 09:31 ET we schedule 07:31 LOCAL (= 09:31 ET = EDT, 1 min behind the 07:30 MT
# heartbeat so decisions.jsonl is fresh). The wrapper itself self-gates the exact
# ET market window (09:30-15:55), so the trigger only needs to cover that span.
#
# CADENCE (tightened 3min -> 1min, 2026-08-02): safe ONLY because of the order-level
# idempotency guard in fleet_live.py::_place_live (claim file + broker open-orders
# re-verify, closes the double-entry hole documented in analysis/deep-research/
# FLEET-RACE-AND-LATENCY-2026-08-01.md section 3). Now matches Gamma_HeartbeatCore's
# own 1-min cadence exactly (same +1-min stagger, so fleet always reads the freshest
# possible core-decisions.jsonl row). Revert: change RepetitionInterval back to 3.

$taskName = "Gamma_FleetExecutor"
$pyw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$vbs = "C:\Users\jackw\Desktop\42\setup\scripts\run_exe_hidden.vbs"
$launcher = "C:\Users\jackw\Desktop\42\setup\scripts\run_ps1_hidden.py"
$ps1 = "C:\Users\jackw\Desktop\42\setup\scripts\run-fleet-executor.ps1"

$argString = '//nologo "{0}" "{1}" "{2}" "{3}"' -f $vbs, $pyw, $launcher, $ps1
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $argString

# 07:31 LOCAL (MT) = 09:31 ET; repeat every 1 min for 6h30m (covers 09:31-16:01 ET).
$startTime = (Get-Date).Date.AddHours(7).AddMinutes(31)
$trigger = New-ScheduledTaskTrigger -Daily -At $startTime
$rep = New-ScheduledTaskTrigger -Once -At $startTime -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Hours 6 -Minutes 30)
$trigger.Repetition = $rep.Repetition

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Unregistered existing $taskName"
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Fleet executor (champion/challenger) -- one perception (heartbeat) -> N policies. WATCH mode: logs per-arm decisions for safe-3/risky-1/risky-3 vs the live signal; places nothing until per-arm live:true. Pure Python, 0 LLM. Wired 2026-06-21 (Milestone-2). Cadence 3min->1min 2026-08-02 (order-level idempotency guard is the precondition -- see fleet_live.py)."

$t = Get-ScheduledTask -TaskName $taskName
$info = $t | Get-ScheduledTaskInfo
$trig = $t.Triggers | Select-Object -First 1
$repInt = if ($trig.Repetition) { $trig.Repetition.Interval } else { "ONCE" }
Write-Host ("VERIFIED: state=" + $t.State + " repeat=" + $repInt + " nextRun=" + $info.NextRunTime)
