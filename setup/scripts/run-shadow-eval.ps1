# Shadow model daily evaluator — fires after market close on weekdays.
# Runs shadow_model_eval.py for today's date on both Safe + Bold accounts.
# Primary: Nemotron ($0 cost, full eval). Challengers: Hermes + Qwen (dt-only, Safe only).
# Challenger failures do NOT abort the primary Nemotron eval.
. "$PSScriptRoot\_shared.ps1"

$task = "shadow-eval"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }

$today = $et.ToString("yyyy-MM-dd")
$scriptPath = Join-Path $WorkDir "setup\scripts\shadow_model_eval.py"

Write-TaskLog -TaskName $task -Message "FIRE date=$today et=$($et.ToString('HH:mm:ss'))"

# --- Primary: Nemotron (production model, full eval, both accounts) ---
$res = Invoke-PythonHidden -ScriptPath $scriptPath `
    -ArgList @("--date", $today, "--account", "both") `
    -TaskName $task `
    -TimeoutSec 1800

if ($res.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "OK nemotron scorecard=analysis/shadow-model/$today-scorecard.md"
} else {
    Write-TaskLog -TaskName $task -Message "ERROR nemotron exit=$($res.ExitCode)"
    Write-TaskLog -TaskName $task -Message "STDERR: $($res.Stderr | Select-Object -First 5 | Out-String)"
}

# --- Challengers: Hermes + Qwen (dt-only, Safe account only, failures non-fatal) ---
# dt-only: skip non-DT ticks to stay within free-tier daily quota (~20 calls/day)
# Safe only: Bold DTs can double the call count; start conservative
foreach ($model in @("hermes", "qwen")) {
    Write-TaskLog -TaskName $task -Message "CHALLENGER $model date=$today"
    $chalRes = Invoke-PythonHidden -ScriptPath $scriptPath `
        -ArgList @("--date", $today, "--account", "safe", "--model", $model, "--dt-only") `
        -TaskName $task `
        -TimeoutSec 3600

    if ($chalRes.ExitCode -eq 0) {
        Write-TaskLog -TaskName $task -Message "OK $model scorecard=analysis/shadow-model/$model/$today-scorecard.md"
    } else {
        Write-TaskLog -TaskName $task -Message "WARN $model exit=$($chalRes.ExitCode) (non-fatal — quota or model issue)"
    }
}

Write-TaskLog -TaskName $task -Message "DONE all models complete for $today"

exit $res.ExitCode   # primary Nemotron exit code determines task success
