# Kitchen reviewer -- fires every 2h. Triages recent cook outputs, queues follow-ups.
. "$PSScriptRoot\_shared.ps1"

$task = "kitchen-reviewer"
Write-TaskLog -TaskName $task -Message "FIRE et=$((Get-EtNow).ToString('HH:mm:ss'))"

$result = Invoke-PythonHidden `
    -ScriptPath "setup\scripts\kitchen_reviewer.py" `
    -ArgList @() `
    -TaskName $task `
    -TimeoutSec 480

Write-TaskLog -TaskName $task -Message "END exit=$($result.ExitCode)"
exit $result.ExitCode
