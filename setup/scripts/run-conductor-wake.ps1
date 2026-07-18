#requires -Version 5.1
<#
.SYNOPSIS
  Gamma Conductor WAKE-ON-EVENT watcher. Every 5 min, 24/7, $0.

.DESCRIPTION
  Fires from Gamma_ConductorWake. Runs conductor_wake_watch.py: scans discord-outbox.jsonl
  + STATUS.md "## Known broken" for a NEW RED-grade infra alert since the last watermark,
  and if found (and not debounced within the last 30 min), fires the right conductor mode
  for the current ET time-of-day via `schtasks /Run` -- Gamma_ConductorRTH during weekday
  RTH (bounded verify-and-flag), Gamma_Conductor otherwise (the full loop).

  Pure Python, no Claude call, $0. Fail-open by construction (the script itself catches
  everything internally and always exits 0) -- this wrapper adds no extra risk surface.
#>

$ErrorActionPreference = "Continue"
$projectRoot = "C:\Users\jackw\Desktop\42"
Set-Location $projectRoot

. "$PSScriptRoot\_shared.ps1"

$task = "conductor-wake"
$result = Invoke-PythonHidden -ScriptPath "setup\scripts\conductor_wake_watch.py" `
    -ArgList @() -TaskName $task -TimeoutSec 30

if ($result.Stdout) {
    Write-TaskLog -TaskName $task -Message ($result.Stdout.Trim())
}
if ($result.ExitCode -ne 0) {
    Write-TaskLog -TaskName $task -Message ("conductor-wake: unexpected exit=" + $result.ExitCode + " stderr=" + $result.Stderr)
}
exit 0
