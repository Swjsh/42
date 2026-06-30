# PreToolUse(Edit|Write|MultiEdit) -- market-hours doctrine guard for LIVE-TRADING config.
# Enforces Rule 9 (NO mid-session rule changes) on a NARROW denylist ONLY, during 09:30-15:55 ET.
#
# OP-32 SAFETY (the 2026-05-22 market-hours-firewall LOCKOUT must NEVER recur):
#   FAIL-OPEN everywhere -- any error/uncertainty -> exit 0 = ALLOW. The ONLY path to a soft
#   block (exit 2) is (denylist live-trading file) AND (market hours via et_clock) AND (no
#   override token). It can NEVER block general work (code/markdown/journals/dashboard) and so
#   can never lock J out of his session. Override in one move: put GAMMA_RULE9_OVERRIDE in the edit.
#   Soft block = exit 2 returns a message to Claude to reconsider; it is NOT a session-killing
#   firewall. Trusted clock = et_clock.py (DST-aware ET), NEVER Bash TZ (the original lockout cause).

$ErrorActionPreference = 'Continue'   # never let our own error block an edit
try {
    $raw = [Console]::In.ReadToEnd()
    if (-not $raw) { exit 0 }
    $payload = $raw | ConvertFrom-Json
    $fp = [string]$payload.tool_input.file_path
    if (-not $fp) { exit 0 }
    $norm = $fp.Replace('\', '/').ToLowerInvariant()

    # NARROW denylist == Rule-9 live-trading config ONLY. Everything else is ALWAYS allowed.
    $deny = @(
        'automation/state/params.json',
        'automation/state/aggressive/params.json',
        'automation/prompts/heartbeat.md',
        'automation/prompts/heartbeat-v14-prod-backup.md'
    )
    $hit = $false
    foreach ($d in $deny) { if ($norm -like "*$d") { $hit = $true; break } }
    # also catch any future params*.json under automation/state(/aggressive)
    if (-not $hit -and ($norm -match 'automation/state/(aggressive/)?params[^/]*\.json$')) { $hit = $true }
    if (-not $hit) { exit 0 }   # not a live-trading file -> ALWAYS allow

    # explicit override token anywhere in the edit body -> allow (intentional production change)
    $body = "$($payload.tool_input.new_string)$($payload.tool_input.content)$($payload.tool_input.old_string)"
    if ($body -match 'GAMMA_RULE9_OVERRIDE') { exit 0 }

    # trusted ET via et_clock.py (DST-aware). NEVER Bash TZ. Prefer the backtest venv (guaranteed deps).
    $pyExe = 'C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe'
    if (-not (Test-Path $pyExe)) { $pyExe = 'C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe' }
    if (-not (Test-Path $pyExe)) { $pyExe = 'python' }
    $et = & $pyExe -c "import sys; sys.path.insert(0, r'C:/Users/jackw/Desktop/42/setup/scripts'); from et_clock import et_now; n=et_now(); print('%d,%d' % (n.weekday(), n.hour*60+n.minute))" 2>$null
    if (-not $et) { exit 0 }   # FAIL-OPEN: clock unreadable -> allow
    $parts = ([string]$et).Trim().Split(',')
    if ($parts.Count -lt 2) { exit 0 }
    $wd = [int]$parts[0]; $mins = [int]$parts[1]
    $inMarket = ($wd -le 4) -and ($mins -ge 570) -and ($mins -le 955)   # Mon-Fri 09:30(570)-15:55(955) ET
    if (-not $inMarket) { exit 0 }   # outside market hours -> allow

    # SOFT BLOCK: exit 2 returns the message to Claude. Overridable + after-hours-clearable.
    [Console]::Error.WriteLine("BLOCKED (Rule 9 -- no mid-session changes to live-trading config during 09:30-15:55 ET). File: $fp. Soft block: make the change AFTER 15:55 ET, or include the token GAMMA_RULE9_OVERRIDE in the edit to proceed intentionally. (et_clock-trusted; fails open on any error -- cannot lock you out.)")
    exit 2
}
catch { exit 0 }   # ANY failure -> ALLOW. This guard can never be the thing that blocks J.
