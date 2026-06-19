# Futures pre-market routine — fires 08:30 ET weekdays.
# Sets key levels, bias, VIX gate, journal header for MNQ/MES session.
. "$PSScriptRoot\_shared.ps1"

# Load Tastytrade sandbox credentials into process env
$EnvFile = Join-Path $WorkDir ".env.tastytrade"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^([^#=][^=]*)=(.+)$') {
            [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
        }
    }
}

$task = "futures-premarket"
$et   = Get-EtNow

if (-not (Test-WeekDay $et)) {
    Write-TaskLog -TaskName $task -Message "SKIP weekend"
    exit 0
}
if (Test-HolidayFromAlpaca) {
    Write-TaskLog -TaskName $task -Message "SKIP holiday"
    exit 0
}

$reaped = Stop-StaleClaudeProcesses -StaleAfterMinutes 5
if ($reaped.Count -gt 0) {
    Write-TaskLog -TaskName $task -Message "REAPED stale: $($reaped -join ',')"
}

function Invoke-FuturesPremarketAttempt {
    param([int]$AttemptNum)
    Write-TaskLog -TaskName $task -Message "FIRE attempt=$AttemptNum et=$((Get-EtNow).ToString('HH:mm:ss'))"
    return Invoke-Claude `
        -PromptFile (Join-Path $WorkDir "automation\prompts\futures-premarket.md") `
        -TaskName $task `
        -MaxBudgetUsd 2.00 `
        -TimeoutSec 300 `
        -Effort "medium"
}

$exit = Invoke-FuturesPremarketAttempt -AttemptNum 1

if ($exit -ne 0) {
    $now = Get-EtNow
    $marketOpen = [DateTime]::new($now.Year, $now.Month, $now.Day, 9, 30, 0)
    $minutesUntilOpen = ($marketOpen - $now).TotalMinutes
    if ($minutesUntilOpen -gt 11) {
        Write-TaskLog -TaskName $task -Message ("RETRY exit=" + $exit + ", " + ([math]::Round($minutesUntilOpen,1)) + "min until open")
        Stop-StaleClaudeProcesses -StaleAfterMinutes 1 | Out-Null
        Start-Sleep -Seconds 5
        $exit = Invoke-FuturesPremarketAttempt -AttemptNum 2
    } else {
        Write-TaskLog -TaskName $task -Message ("NO_RETRY exit=" + $exit + ", only " + ([math]::Round($minutesUntilOpen,1)) + "min until open")
    }
}
exit $exit
