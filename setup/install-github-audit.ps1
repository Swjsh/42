#requires -Version 5.1
<#
.SYNOPSIS
  Install Gamma_GitHubAudit -- fires every 2 days at 21:00 MT (~23:00 ET).

.DESCRIPTION
  Runs github_audit.py against all git-tracked files. GREEN = silent. Any
  HIGH or MEDIUM finding (hardcoded key, missing gitignore pattern, blocked
  tracked file) triggers a Discord ping with an itemized summary. LOW-only
  findings are suppressed (heuristic noise). Never fires during market hours.

  Pure Python, stdlib only. Zero LLM cost. ~14s per run on 4000+ files.

  Per CLAUDE.md GitHub doctrine (## GitHub) + OP-25 engine-benefit autonomy.
  Uses OP-27 canonical zero-leak chain (wscript -> pythonw -> run_ps1_hidden).
#>

$ErrorActionPreference = "Stop"
$WorkDir   = "C:\Users\jackw\Desktop\42"
$ScriptsDir = Join-Path $WorkDir "setup\scripts"
$TaskName  = "Gamma_GitHubAudit"

$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pythonw)) {
    Write-Error "System pythonw not found at $pythonw"
    exit 1
}

$runPs1Hidden = Join-Path $ScriptsDir "run_ps1_hidden.py"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$targetPs1    = Join-Path $ScriptsDir "run-github-audit.ps1"
$auditPy      = Join-Path $ScriptsDir "github_audit.py"

foreach ($p in @($runPs1Hidden, $runExeHidden, $targetPs1, $auditPy)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

$action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "//nologo `"$runExeHidden`" `"$pythonw`" `"$runPs1Hidden`" `"$targetPs1`""

# Every 2 days at 21:00 MT (~23:00 ET). After all EOD pipelines have committed.
# DaysInterval=2 starting from today. Adjust start date if a different day is preferred.
$trigger = New-ScheduledTaskTrigger -Daily -At "21:00" -DaysInterval 2

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Secrets + privacy audit for public repo Swjsh/42. Runs github_audit.py every 2 days. GREEN=silent. RED=Discord ping with file:line summary. Zero LLM cost."

Write-Output "OK: Registered $TaskName (every 2 days at 21:00 MT / ~23:00 ET)"
Write-Output "    Audit script: setup\scripts\github_audit.py"
Write-Output "    Runner:       setup\scripts\run-github-audit.ps1"
Write-Output "    Test now:     Start-ScheduledTask -TaskName $TaskName"
Write-Output "    Manual run:   python setup\scripts\github_audit.py"
