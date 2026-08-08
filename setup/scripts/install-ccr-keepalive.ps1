#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_CcrKeepalive -- keepalive for the claude-code-router (CCR) gateway
  that every `claude` CLI session routes through (~/.claude/settings.json
  ANTHROPIC_BASE_URL -> 127.0.0.1:3456, since 2026-07-08).

  WHY: CCR died overnight 07-08->07-09 with no auto-restart; every LLM scheduled
  fire failed ConnectionRefused until a manual restart the next day. Same treatment
  as Gamma_DiscordBridge / Gamma_CryptoGrinderKeepalive / Gamma_KitchenDaemonKeepalive:
  a 5-min, 24/7 TCP-probe + auto-restart + episode-deduped Discord ping.

  WIRING PATTERN (2026-08-08 VBS-WRAPPER-EXIT-CODE-BLIND-SPOT migration -- now on
  the run_cmd_hidden.py relay, matches install-crypto-twin.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> ccr_keepalive.py
  Both hops stay system pythonw (ccr_keepalive.py is stdlib-only, no venv needed).
  run_cmd_hidden.py runs the child SYNCHRONOUSLY and logs the real exit code to
  automation/state/logs/run-cmd-hidden-<date>.log. Prior wiring was fire-and-forget
  (LastTaskResult always fake-0) -- one of the 31 direct-invocation tasks named in
  VBS-WRAPPER-EXIT-CODE-BLIND-SPOT's 2026-08-07 audit (queue.md).

  CADENCE (matches install-crypto-grinder-keepalive.ps1's trigger idiom): a `-Once`
  base trigger + `-RepetitionInterval 5min` + a ~10-year `-RepetitionDuration` is the
  correct Windows Task Scheduler pattern for "every 5 min, forever" -- verified live
  against Gamma_CryptoGrinderKeepalive's actual NextRunTime (recalculates every fire,
  never goes dark). This is NOT the one-time-trigger foot-gun (project_scheduled_task_
  onetime_trigger_dark) -- that lesson is about a trigger with NO repetition set at all.
  24/7 (not RTH-gated): LLM scheduled fires run overnight too (kitchen/overnight
  sessions), so CCR must stay up around the clock, not just during market hours.

  To verify after running: Get-ScheduledTask -TaskName Gamma_CcrKeepalive
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root      = "C:\Users\jackw\Desktop\42"
$taskName  = "Gamma_CcrKeepalive"

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "Unregistered $taskName."
    }
    return
}

$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonw      = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\ccr_keepalive.py"

if (-not (Test-Path $pythonw))      { throw "system pythonw.exe not found at $pythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $script))       { throw "ccr_keepalive.py not found at $script" }

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
#   -- system pythonw -> ccr_keepalive.py
$wscriptArgs = "//nologo `"$vbs`" `"$pythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$pythonw`" `"$script`""
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $wscriptArgs -WorkingDirectory $root

# Every 5 min, 24/7 -- LLM overnight/kitchen fires need CCR up outside RTH too.
$startBoundary = (Get-Date).AddMinutes(1)
$trigger = New-ScheduledTaskTrigger -Once -At $startBoundary `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([System.TimeSpan]::FromDays(365 * 10))

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Keepalive for the claude-code-router (CCR) gateway (127.0.0.1:3456) every claude CLI session routes through. TCP-probes every 5 min 24/7; on down, restarts via direct node.exe invocation of the CCR CLI (falls back to ccr.ps1 if node/cli.js paths drift), re-probes after ~8s, writes automation/state/ccr-keepalive.json. Pings J once per failure-episode (>=3 consecutive down-probes), resets on recovery. Fail-open, `$0. Built 2026-07-09." `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Host "Registered $taskName. Next run: $($info.NextRunTime)"
