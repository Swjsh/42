# Kitchen seeder -- fires hourly. Generates 5 new cook tasks via Nemotron.
. "$PSScriptRoot\_shared.ps1"

$task = "kitchen-seeder"
Write-TaskLog -TaskName $task -Message "FIRE et=$((Get-EtNow).ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\kitchen_seeder.py" `
    -ArgList @() `
    -TaskName $task `
    -TimeoutSec 360

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode)"
exit $result.ExitCode
