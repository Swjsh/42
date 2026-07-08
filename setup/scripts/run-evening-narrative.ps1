# Gamma evening narrative — the colleague voice (J directive 2026-07-08).
# Fires 16:20 ET weekdays: gamma_narrative.py gathers the day's deterministic
# facts (fill funnel, P&L, kitchen R&D, commits), writes Gamma's first-person
# SAW/DID/LEARNED/CHANGING narrative (+ one untested lever + one question for J)
# to gamma-narrative.json + journal + Discord outbox, then chains gamma_speak.py
# (Kokoro TTS, setup/.tts-venv) to synthesize gamma-voice-{date}.wav.
. "$PSScriptRoot\_shared.ps1"

$task = "evening-narrative"
$et = Get-EtNow

if (-not (Test-WeekDay $et)) { exit 0 }

$today = $et.ToString("yyyy-MM-dd")
$scriptPath = Join-Path $WorkDir "setup\scripts\gamma_narrative.py"

Write-TaskLog -TaskName $task -Message "FIRE date=$today et=$($et.ToString('HH:mm:ss'))"

$res = Invoke-PythonHidden -ScriptPath $scriptPath `
    -ArgList @("--date", $today) `
    -TaskName $task `
    -TimeoutSec 900

if ($res.ExitCode -eq 0) {
    Write-TaskLog -TaskName $task -Message "OK narrative + voice shipped (state/gamma-narrative.json, gamma-voice-$today.wav, outbox)"
} else {
    Write-TaskLog -TaskName $task -Message "ERROR exit=$($res.ExitCode)"
    Write-TaskLog -TaskName $task -Message "STDERR: $($res.Stderr | Select-Object -First 5 | Out-String)"
}

exit $res.ExitCode
