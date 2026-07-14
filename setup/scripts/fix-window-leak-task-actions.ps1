#requires -Version 5.1
<#
.SYNOPSIS
  Rewrap the Action of every scheduled task still on a popup-capable launcher
  onto the proven hidden chain, WITHOUT touching Trigger/Settings/Principal or
  the target .ps1's own content.

.CONTEXT (2026-07-14, J: "stop the fkin popus on my screen")
  A live-registry audit (setup/scripts/audit_scheduled_tasks.py, fixed same day)
  found 5 tasks still on popup-capable actions that the OLD static-source-only
  compliance audit (audit_window_leak_compliance.py) never saw, because none of
  these patterns live inside any .ps1/.py file it scanned -- they live in Task
  Scheduler's own registered Action, or (for run_hidden.vbs) inside a .vbs file
  that audit never read:

    - Gamma_DiscordBridge / Gamma_EveningNarrative / Gamma_McpDailyAudit /
      Gamma_ShadowEval: wscript.exe //nologo run_hidden.vbs <ps1>
      run_hidden.vbs uses WScript.Shell.Run (ShellExecute), which routes through
      the Win11 DefaultTerminal handler and leaks a `WindowsTerminal -Embedding`
      window on EVERY fire (root-caused 2026-05-17, documented in
      run_ps1_hidden.py's own docstring -- this was the FIX that evening, just
      never applied to these 4 tasks). Gamma_DiscordBridge fires every 5 min,
      24/7 -- the dominant popup source on the box.

    - SwjshAK-BrainSync (SwjshAlgoKnife repo's daily git-sync, registered
      directly as a Windows Scheduled Task on this same user account): bare
      `powershell.exe -WindowStyle Hidden -File ...`. Task Scheduler allocates
      the console BEFORE PowerShell's own -WindowStyle Hidden takes effect --
      same Win11 OpenConsole-before-hidden flash, once/day at 04:00 MT.
      This script changes ONLY the Task Scheduler launch mechanism for
      SwjshAK-BrainSync -- it does not read, touch, or modify anything inside
      Desktop\SwjshAlgoKnife (that repo's own scope stays exactly as it was;
      sync-brain-to-git.ps1's content is byte-for-byte unchanged).

  FIX: wscript.exe //nologo run_exe_hidden.vbs <system pythonw.exe> run_ps1_hidden.py <same .ps1>
  run_ps1_hidden.py launches powershell.exe via Python subprocess.Popen with
  creationflags=CREATE_NO_WINDOW (0x08000000) -- CreateProcess directly, which
  Windows is REQUIRED to honor (no ShellExecute, no DefaultTerminal routing).
  Same proven chain as ~80 other Gamma_* tasks already use (e.g. install-crypto-twin.ps1).

  Uses Set-ScheduledTask (action-only swap) rather than unregister+reregister,
  so each task's exact existing Trigger/Settings/Principal survive untouched --
  minimal diff, lowest risk, fully reversible (exact prior Arguments are printed
  before every change).

.USAGE
  Idempotent -- safe to re-run. Reports "already fixed" for any task that no
  longer needs the swap (e.g. if run a second time, or after a partial prior run).
#>
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$vbs        = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$ps1Hidden  = Join-Path $root "setup\scripts\run_ps1_hidden.py"

if (-not (Test-Path $vbs))        { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $sysPythonw)) { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $ps1Hidden))  { throw "run_ps1_hidden.py not found at $ps1Hidden" }

# {TaskName -> target .ps1 path}. Target .ps1 files are UNCHANGED by this script --
# only the Task Scheduler launch mechanism (Action) is rewrapped.
$targets = [ordered]@{
    "Gamma_DiscordBridge"    = Join-Path $root "setup\scripts\ensure-discord-bridge-alive.ps1"
    "Gamma_EveningNarrative" = Join-Path $root "setup\scripts\run-evening-narrative.ps1"
    "Gamma_McpDailyAudit"    = Join-Path $root "setup\scripts\run-mcp-daily-audit.ps1"
    "Gamma_ShadowEval"       = Join-Path $root "setup\scripts\run-shadow-eval.ps1"
    "SwjshAK-BrainSync"      = "C:\Users\jackw\Desktop\SwjshAlgoKnife\scripts\sync-brain-to-git.ps1"
}

$results = @()

foreach ($name in $targets.Keys) {
    $ps1Target = $targets[$name]
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Warning "$name -- NOT REGISTERED, skipping"
        $results += [PSCustomObject]@{ Task = $name; Status = "NOT_REGISTERED"; Before = ""; After = "" }
        continue
    }
    if (-not (Test-Path $ps1Target)) {
        Write-Warning "$name -- target .ps1 missing at $ps1Target, skipping (would break the task)"
        $results += [PSCustomObject]@{ Task = $name; Status = "TARGET_MISSING"; Before = ""; After = "" }
        continue
    }

    $oldAction = $task.Actions[0]
    $before = "EXEC='$($oldAction.Execute)' ARGS='$($oldAction.Arguments)'"

    $alreadyFixed = ($oldAction.Execute -eq "wscript.exe") -and
                    ($oldAction.Arguments -match [regex]::Escape("run_exe_hidden.vbs")) -and
                    ($oldAction.Arguments -match [regex]::Escape("run_ps1_hidden.py"))
    if ($alreadyFixed) {
        Write-Host "$name -- already on the proven chain, no change needed"
        Write-Host "  CURRENT: $before"
        $results += [PSCustomObject]@{ Task = $name; Status = "ALREADY_FIXED"; Before = $before; After = $before }
        continue
    }

    $newArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$ps1Hidden`" `"$ps1Target`""
    $newAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $newArgs

    Set-ScheduledTask -TaskName $name -Action $newAction | Out-Null

    $verify = Get-ScheduledTask -TaskName $name
    $after = "EXEC='$($verify.Actions[0].Execute)' ARGS='$($verify.Actions[0].Arguments)'"

    Write-Host "$name -- FIXED"
    Write-Host "  BEFORE: $before"
    Write-Host "  AFTER:  $after"
    $results += [PSCustomObject]@{ Task = $name; Status = "FIXED"; Before = $before; After = $after }
}

Write-Host ""
Write-Host "=== SUMMARY ==="
$results | Format-Table -AutoSize -Wrap | Out-String -Width 300 | Write-Host

$outPath = Join-Path $root "automation\state\window-leak-task-fix-log.json"
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $outPath -Encoding utf8
Write-Host "Log written: $outPath"
