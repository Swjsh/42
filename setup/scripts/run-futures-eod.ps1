# Futures EOD review — fires 16:05 ET weekdays.
# Reviews trades, runs in-prompt replay, updates journal and trades.csv.
. "$PSScriptRoot\_shared.ps1"

$EnvFile = Join-Path $WorkDir ".env.tastytrade"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^#=][^=]*)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
        }
    }
}

$task = "futures-eod"
$et   = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}
if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

Repair-StateFiles -TaskName $task | Out-Null

Write-TaskLog -TaskName $task -Message "FIRE futures-eod et=$($et.ToString('HH:mm:ss'))"

$exit = Invoke-Claude `
    -PromptFile (Join-Path $WorkDir "automation\prompts\futures-eod.md") `
    -TaskName $task `
    -MaxBudgetUsd 2.00 `
    -TimeoutSec 240 `
    -Effort "medium"

$postStats = Repair-StateFiles -TaskName $task
Write-TaskLog -TaskName $task -Message "Done exitCode=$exit corrupted=$($postStats.Corrupted)"
exit $exit
