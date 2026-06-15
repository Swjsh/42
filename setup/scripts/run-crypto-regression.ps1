#requires -Version 5.1
<#
.SYNOPSIS
  Crypto regression check -- runs crypto/validators/runner.py and crypto/benchmarks/analyze_grinder.py.

.DESCRIPTION
  Fires from Gamma_CryptoRegression task on a 30-min cadence.
  Writes scorecards to crypto/data/scorecards/.
  On FAIL, appends a one-line entry to automation/overnight/STATUS.md `Known broken` section
  so the wake fires (per OP 24) pick it up.

  Pure Python execution. Zero LLM cost. ALL Python spawned via Invoke-PythonHidden
  (CREATE_NO_WINDOW) per OP-27 L41 -- bare `python script.py` leaks conhost windows on WT-default Win11.
#>

$ErrorActionPreference = "Continue"
. "$PSScriptRoot\_shared.ps1"

$projectRoot = $WorkDir
Set-Location $projectRoot

$logFile = Join-Path $LogDir ("crypto-regression-" + (Get-Date -Format "yyyy-MM-dd") + ".log")
$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

Add-Content -Path $logFile -Value "[$now] crypto-regression: starting"

# 1. Validator suite
$runner = Invoke-PythonHidden -ScriptPath "crypto\validators\runner.py" -TaskName "crypto-regression-runner" -TimeoutSec 600
$runnerExit = $runner.ExitCode
Add-Content -Path $logFile -Value ("[$now] runner exit=$runnerExit log=" + $runner.LogFile)

# 2. Grinder analyzer (only if grinder.jsonl exists)
$grinderPath = Join-Path $projectRoot "crypto\data\scorecards\grinder.jsonl"
if (Test-Path $grinderPath) {
    $analyzer = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\analyze_grinder.py" -TaskName "crypto-regression-analyzer" -TimeoutSec 120
    Add-Content -Path $logFile -Value ("[$now] analyzer exit=" + $analyzer.ExitCode)
}

# 3. Drift tracker (outer loop per OP-11)
$drift = Invoke-PythonHidden -ScriptPath "crypto\benchmarks\track_drift.py" -TaskName "crypto-regression-drift" -TimeoutSec 120
Add-Content -Path $logFile -Value ("[$now] drift exit=" + $drift.ExitCode)

# 4. Surface RED health to STATUS.md (OP-26 + OP-25) -- read drift_report.json directly in PS instead of `python -c`
$driftJson = Join-Path $projectRoot "crypto\data\scorecards\drift_report.json"
if (Test-Path $driftJson) {
    try {
        $driftObj = Get-Content $driftJson -Raw -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
        $health = $driftObj.overall_health
        if ($health -eq "RED") {
            $statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
            if (Test-Path $statusPath) {
                $alertsText = ($driftObj.alerts -join ' | ')
                Add-Content -Path $statusPath -Value "`n- [$now] crypto-harness drift RED :: $alertsText :: see crypto/data/scorecards/drift_report.json"
            }
        }
    } catch {
        Add-Content -Path $logFile -Value "[$now] drift_report.json parse error: $_"
    }
}

# 5. One-line summary + RED escalation
$summary = if ($runnerExit -eq 0) {
    "[$now] crypto-regression PASS"
} else {
    "[$now] crypto-regression FAIL (exit=$runnerExit)"
}
$statusPath = Join-Path $projectRoot "automation\overnight\STATUS.md"
if ($runnerExit -ne 0 -and (Test-Path $statusPath)) {
    Add-Content -Path $statusPath -Value "`n- $summary - see $logFile"
}
Add-Content -Path $logFile -Value $summary

exit $runnerExit
