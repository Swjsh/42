# run-voice-bot.ps1 -- start the Gamma Discord voice bot (gamma-voicebot/bot.js).
# PS 5.1-safe. Resolves the repo root from this script's own location so it works
# from the main checkout or any worktree. Skips a duplicate start if a bot is
# already running from this repo (one gateway session per token per repo copy).
#
#   powershell -ExecutionPolicy Bypass -File setup\scripts\run-voice-bot.ps1
#
# Long-term home: if this graduates to a Windows scheduled task, wrap it in the
# wscript->hidden chain like the other daemons (window-leak trap, CLAUDE.md L41).

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$bot = Join-Path $repo "gamma-voicebot\bot.js"
$logDir = Join-Path $repo "automation\state\logs"

if (-not (Test-Path $bot)) { Write-Output "FATAL: $bot not found"; exit 1 }
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }

# Already running from this repo copy? (match node.exe with our bot.js in the command line)
$botEsc = $bot.Replace("\", "\\")
$existing = Get-WmiObject Win32_Process -Filter "Name='node.exe'" |
  Where-Object { $_.CommandLine -like "*gamma-voicebot*bot.js*" }
if ($existing) {
  Write-Output "voice bot already running (pid $($existing[0].ProcessId)) -- not starting a second"
  exit 0
}

$env:GAMMA_WORKSPACE = $repo
$out = Join-Path $logDir "voice-bot.stdout.log"
$err = Join-Path $logDir "voice-bot.stderr.log"
$p = Start-Process -FilePath "node" -ArgumentList "`"$bot`"" -WorkingDirectory (Join-Path $repo "gamma-voicebot") `
  -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
Write-Output "voice bot started pid=$($p.Id) log=$out"
