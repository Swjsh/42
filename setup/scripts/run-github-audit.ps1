# run-github-audit.ps1 -- secrets & privacy audit for Swjsh/42 (PUBLIC repo).
# Invoked by Gamma_GitHubAudit every 2 days (~21:00 MT / ~23:00 ET, after-hours).
#
# Behaviour:
#   GREEN  -> silent (no Discord ping, no log noise)
#   YELLOW/RED (any HIGH or MEDIUM finding) -> Discord ping with itemized summary
#
# Never runs during market hours; audit-only, never edits files.
. "$PSScriptRoot\_shared.ps1"

$task    = "github-audit"
$workDir = $Global:WorkDir
$et      = Get-EtNow

# Hard gate: never run during market hours (audit is cheap but shares the Max pool)
if ((Test-WeekDay -Et $et) -and (Test-MarketHours -Et $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP market hours ($($et.ToString('HH:mm')) ET)"
    exit 0
}

Write-TaskLog -TaskName $task -Message "FIRE et=$($et.ToString('yyyy-MM-dd HH:mm')) -- running github_audit.py"

$auditScript = Join-Path $workDir "setup\scripts\github_audit.py"

$result = Invoke-PythonHidden `
    -ScriptPath $auditScript `
    -ArgList @("--json") `
    -TaskName $task `
    -TimeoutSec 120

Write-TaskLog -TaskName $task -Message "EXIT=$($result.ExitCode)"

# EXIT 0 = GREEN -- stay silent
if ($result.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "VERDICT: GREEN -- no findings, staying silent"
    exit 0
}

# EXIT 2 = tool error (git not found, etc.)
if ($result.ExitCode -eq 2) {
    $msg = "GitHub audit ERROR -- could not run scan. Check: $auditScript"
    Write-TaskLog -TaskName $task -Message "ERROR: $($result.Stderr)"
    & "$PSScriptRoot\gamma-notify.ps1" -Message $msg
    exit 2
}

# EXIT 1 = YELLOW (LOW only) or RED (HIGH/MEDIUM) -- parse and decide
try {
    $report = $result.Stdout | ConvertFrom-Json
} catch {
    $msg = "GitHub audit: could not parse JSON output -- run manually: python setup/scripts/github_audit.py"
    Write-TaskLog -TaskName $task -Message "JSON parse failed: $_"
    & "$PSScriptRoot\gamma-notify.ps1" -Message $msg
    exit 1
}

$verdict     = $report.verdict
$highCount   = ($report.findings | Where-Object { $_.severity -eq "HIGH" } | Measure-Object).Count
$medCount    = ($report.findings | Where-Object { $_.severity -eq "MEDIUM" } | Measure-Object).Count
$actionable  = $highCount + $medCount

# YELLOW with only LOW findings -- stay silent (false-positive heuristic noise)
if ($actionable -eq 0) {
    Write-TaskLog -TaskName $task -Message "VERDICT: YELLOW/LOW-only -- staying silent ($($report.findings.Count) LOW findings)"
    exit 0
}

# RED -- build concise Discord summary (max 3 example findings, then truncate)
$lines = @("**GitHub audit $verdict** -- $actionable HIGH/MEDIUM finding(s) in PUBLIC repo Swjsh/42")

$shown = 0
foreach ($f in ($report.findings | Where-Object { $_.severity -eq "HIGH" -or $_.severity -eq "MEDIUM" })) {
    if ($shown -ge 3) {
        $remaining = $actionable - $shown
        $lines += "  ...and $remaining more. Run: python setup/scripts/github_audit.py"
        break
    }
    $loc = if ($f.line) { "$($f.path):$($f.line)" } else { $f.path }
    $lines += "  [$($f.severity)]  $loc -- $($f.label)"
    $shown++
}

$lines += "Fix before next git push. Full report: ``python setup/scripts/github_audit.py``"

$msg = $lines -join "`n"
Write-TaskLog -TaskName $task -Message "VERDICT: $verdict -- notifying Discord`n$msg"

& "$PSScriptRoot\gamma-notify.ps1" -Message $msg
exit 1
