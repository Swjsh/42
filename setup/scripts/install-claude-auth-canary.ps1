#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_ClaudeAuthCanary -- daily deterministic check that the standalone Claude
  CLI is still logged in. Fires daily 16:00 MT local (18:00 ET -- this box is Mountain,
  ET=local+2h).

.DESCRIPTION
  WHY THIS EXISTS (incident verified 2026-09-15 ~08:45 ET): the standalone CLI lost its
  saved claude.ai login. `claude auth status` returned loggedIn=false; the refresh token
  had expired 2026-09-14 10:25 local and the tokens on disk were blank from 13:55 local.
  Nothing flagged it until Gamma_Premarket failed at 08:30 ET ("Not logged in - Please run
  /login") and fell back to a degraded deterministic bias. Gamma_Premarket, the secondary
  15:55 flatten net, the conductor, EOD summary, analyst and scout personas all depend on
  the same CLI session.

  setup/scripts/claude_auth_canary.py runs `claude auth status` (resolved via the same
  claude.exe path Invoke-Claude uses in _shared.ps1), separately reads (never logs the
  value of) ~/.claude/.credentials.json's claudeAiOauth.refreshTokenExpiresAt, and writes
  a verdict (OK/EXPIRING/LOGGED_OUT/UNKNOWN) to automation/state/claude-auth-canary.json.
  On anything but OK it upserts a deduped CLAUDE_AUTH: line into STATUS.md's '## Known
  broken' section via the existing status_known_broken.py writer (setup/scripts/
  claude_auth_canary_surface.py) -- and clears that line automatically once the login is
  restored. Zero LLM spend: pure stdlib Python, one subprocess call.

  TIMING -- 18:00 ET is EVENING, after the trading day's CLI-dependent chain (premarket,
  heartbeat is deterministic Python and does NOT depend on the CLI, EOD flatten) and
  before the overnight build loop and any late-evening persona fires that DO depend on the
  CLI (conductor, analyst). Catches an overnight-style logout (like this incident) the
  SAME evening instead of waiting for the next morning's premarket failure to surface it.

  WIRING PATTERN (flash-free, cloned from install-task-staleness.ps1 /
  install-prereg-hygiene.ps1):
    wscript -> run_exe_hidden.vbs -> system pythonw -> run_cmd_hidden.py --cwd <repo>
      -- system pythonw -> claude_auth_canary.py
  System pythonw (pure stdlib, no third-party deps) -- no console popups.

  Output:
    automation/state/claude-auth-canary.json -- latest verdict
    automation/overnight/STATUS.md '## Known broken' -- CLAUDE_AUTH: line on non-OK
    automation/state/logs/run-cmd-hidden-<date>.log -- the real exit code, dated

  To verify: Get-ScheduledTask -TaskName Gamma_ClaudeAuthCanary | Get-ScheduledTaskInfo
  To test now: Start-ScheduledTask -TaskName Gamma_ClaudeAuthCanary
  REVERT: Unregister-ScheduledTask -TaskName "Gamma_ClaudeAuthCanary" -Confirm:$false

  Per CLAUDE.md OP-3 ($0, pure Python) + OP-25 (fail loud, never silent) + OP-33
  (visibility is the product). Guard: setup/scripts/test_claude_auth_canary.py.
#>

$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$script       = Join-Path $root "setup\scripts\claude_auth_canary.py"
$taskName     = "Gamma_ClaudeAuthCanary"

foreach ($p in @($vbs, $sysPythonw, $runCmdHidden, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

$wscriptArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- `"$sysPythonw`" `"$script`""

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument $wscriptArgs `
    -WorkingDirectory $root

# Daily 16:00 LOCAL (Mountain) = 18:00 ET.
$trigger = New-ScheduledTaskTrigger -Daily -At "16:00"

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description ("Daily deterministic Claude CLI auth canary (incident 2026-09-15): " + `
    "runs 'claude auth status' + checks ~/.claude/.credentials.json refresh-token expiry " + `
    "(never reads token values) and writes automation/state/claude-auth-canary.json. On " + `
    "LOGGED_OUT/EXPIRING/UNKNOWN, upserts a deduped CLAUDE_AUTH: line into STATUS.md's " + `
    "Known broken section via status_known_broken.py; clears it on recovery. Zero LLM " + `
    "spend, pure stdlib Python, `$0/day. Daily 16:00 MT (18:00 ET), same evening as any " + `
    "logout. Guard: setup/scripts/test_claude_auth_canary.py.") `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $taskName | Get-ScheduledTaskInfo
Write-Output "OK: Registered $taskName for daily 16:00 MT (18:00 ET)"
Write-Output "    State:    automation\state\claude-auth-canary.json"
Write-Output "    Test now: Start-ScheduledTask -TaskName $taskName"
Write-Output "    Next run: $($info.NextRunTime)"
