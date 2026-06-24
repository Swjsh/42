# Shadow model daily evaluator — fires after market close on weekdays.
# Runs shadow_model_eval.py for today's date on both Safe + Bold accounts.
# Uses free-tier Nemotron ($0 cost). Writes scorecard to analysis/shadow-model/.
. "$PSScriptRoot\_shared.ps1"

$task = "shadow-eval"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }

$today = $et.ToString("yyyy-MM-dd")
Write-TaskLog -TaskName $task -Message "FIRE date=$today et=$($et.ToString('HH:mm:ss'))"

$scriptPath = Join-Path $WorkDir "setup\scripts\shadow_model_eval.py"
$res = Invoke-PythonHidden -ScriptPath $scriptPath `
    -ArgList @("--date", $today, "--account", "both") `
    -TaskName $task `
    -TimeoutSec 900

if ($res.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "OK scorecard=analysis/shadow-model/$today-scorecard.md"
} else {
    Write-TaskLog -TaskName $task -Message "ERROR exit=$($res.ExitCode)"
    Write-TaskLog -TaskName $task -Message "STDERR: $($res.Stderr | Select-Object -First 10 | Out-String)"
}

exit $res.ExitCode
