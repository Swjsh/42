#requires -Version 5.1
# Gamma_JournalCalendar runner -- keep the trading journal calendar current.
# ASCII-ONLY (PS 5.1 reads BOM-less files as Windows-1252; non-ASCII = silent parse death).
#
# WHY THIS TASK EXISTS (2026-08-20): journal_calendar.py shipped 2026-08-19 with NO
# scheduler entry, so it ran exactly once. By the next evening calendar-data.json was
# 24.4h stale and did not contain that day at all -- a +$811 session was missing from
# the journal AND from the cockpit's money card, which reads the same file. A generated
# surface with no generator schedule is a surface that silently rots.
#
# CADENCE: the rebuild takes ~0.25s and reads only the local fills ledger (no broker
# call, no network, no LLM), so cost is not the constraint. Fires on the half hour
# through the session and once after the close, so a mid-day glance is never more than
# 30 minutes behind and the final EOD number lands before the digest reads it.
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"
$repo = "C:\Users\jackw\Desktop\42"
$py   = Join-Path $repo "backtest\.venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }   # fail open to system python
$script = Join-Path $repo "setup\scripts\journal_calendar.py"
$logDir = Join-Path $repo "automation\state\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$log = Join-Path $logDir ("journal-calendar-" + (Get-Date -Format "yyyy-MM-dd") + ".log")

# EAP=Continue while capturing: a native stderr line under redirection can abort the
# runner on the FIRST warning. UTF-8 append, not PS 5.1's default UTF-16LE.
$ErrorActionPreference = "Continue"
$out = & $py $script 2>&1 | Out-String
$rc = $LASTEXITCODE
$ErrorActionPreference = "Stop"
Add-Content -Path $log -Value (("[" + (Get-Date -Format "HH:mm:ss") + "] ") + $out) -Encoding UTF8
if ($rc -ne 0) {
    Add-Content -Path $log -Value ("[run-journal-calendar] NONZERO EXIT " + $rc) -Encoding UTF8
}

# The cockpit embeds this calendar, so refresh it in the same breath -- otherwise the
# journal is current and the page J actually opens is still a day behind.
$home_py = Join-Path $repo "setup\scripts\gamma_home.py"
if (Test-Path $home_py) {
    $ErrorActionPreference = "Continue"
    $out2 = & $py $home_py --quiet 2>&1 | Out-String
    $ErrorActionPreference = "Stop"
    Add-Content -Path $log -Value ("[cockpit] " + $out2) -Encoding UTF8
}
exit $rc
