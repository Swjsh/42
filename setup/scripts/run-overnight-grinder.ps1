# Gamma_OvernightGrinder fire — invokes Claude Code with the wake prompt.
# Each fire = a fresh Claude session that grinds one task from the queue.
#
# Cost: ~$0.30/fire on Sonnet. Total ~$4-5/night across 14 fires.

$ErrorActionPreference = 'Continue'  # don't crash if claude exits non-zero

$repoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$wakePrompt = Join-Path $repoRoot 'automation\overnight\wake-prompt.txt'
$logDir = Join-Path $repoRoot 'automation\overnight'
$fireLog = Join-Path $logDir 'fires.log'

if (-not (Test-Path $wakePrompt)) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] wake-prompt.txt missing at $wakePrompt" | Out-File -FilePath $fireLog -Append -Encoding utf8
    exit 1
}

# Locate claude CLI (try common install locations)
$claudeExe = (Get-Command claude -ErrorAction SilentlyContinue).Source
if (-not $claudeExe) {
    foreach ($p in @(
        "$env:LOCALAPPDATA\Programs\claude\claude.exe",
        "$env:USERPROFILE\.npm-global\claude.cmd",
        "$env:APPDATA\npm\claude.cmd"
    )) {
        if (Test-Path $p) { $claudeExe = $p; break }
    }
}
if (-not $claudeExe) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] claude CLI not found on PATH or common locations" | Out-File -FilePath $fireLog -Append -Encoding utf8
    exit 1
}

$promptText = Get-Content $wakePrompt -Raw
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [FIRE] starting grinder fire (claude=$claudeExe)" | Out-File -FilePath $fireLog -Append -Encoding utf8

# Pipe prompt to claude --print via stdin. Use Sonnet for cost-efficient reasoning.
# 30-min wall clock cap — if claude hangs, the next scheduled fire will try again.
$startInfo = New-Object System.Diagnostics.ProcessStartInfo
$startInfo.FileName = $claudeExe
$startInfo.Arguments = "--print --model sonnet --effort medium --max-budget-usd 1.50 --permission-mode acceptEdits --add-dir `"$repoRoot`""
$startInfo.WorkingDirectory = $repoRoot
$startInfo.UseShellExecute = $false
$startInfo.CreateNoWindow = $true
$startInfo.RedirectStandardInput = $true
$startInfo.RedirectStandardOutput = $true
$startInfo.RedirectStandardError = $true

$proc = [System.Diagnostics.Process]::Start($startInfo)
$proc.StandardInput.Write($promptText)
$proc.StandardInput.Close()

# 30 min wall-clock cap
$timeoutMs = 30 * 60 * 1000
if (-not $proc.WaitForExit($timeoutMs)) {
    try { $proc.Kill() } catch {}
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [TIMEOUT] grinder fire killed after 30min" | Out-File -FilePath $fireLog -Append -Encoding utf8
    exit 124
}

$out = $proc.StandardOutput.ReadToEnd()
$err = $proc.StandardError.ReadToEnd()
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [DONE] exit=$($proc.ExitCode)" | Out-File -FilePath $fireLog -Append -Encoding utf8

# Save full transcript per-fire for audit (last 50 fires kept; rotate older)
$transcriptDir = Join-Path $logDir 'transcripts'
if (-not (Test-Path $transcriptDir)) { New-Item -ItemType Directory -Path $transcriptDir -Force | Out-Null }
$ts = Get-Date -Format 'yyyy-MM-ddTHH-mm-ss'
$transcript = Join-Path $transcriptDir "fire-$ts.txt"
"=== STDOUT ===`n$out`n`n=== STDERR ===`n$err" | Out-File -FilePath $transcript -Encoding utf8

# Rotate old transcripts (keep last 50)
Get-ChildItem -Path $transcriptDir -Filter 'fire-*.txt' | Sort-Object Name -Descending | Select-Object -Skip 50 | Remove-Item -Force -ErrorAction SilentlyContinue

exit $proc.ExitCode
