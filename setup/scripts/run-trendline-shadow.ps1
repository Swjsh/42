# Trendline shadow ledger runner — fires 14:20 MT / 16:20 ET daily.
#
# TIMING IS LOAD-BEARING, and both ends are tight:
#   14:16 MT  the day's cumulative spy_5m_2026-05-19_<date>.csv lands
#   14:20 MT  THIS runs (needs those bars)
#   14:30 MT  Gamma_EodFullAudit runs and reads the ledger for its mandatory
#             "do we see any trend lines?" section
# Moving this outside that window silently blanks the EOD section.
#
# The box runs Mountain time, so the trigger is registered in LOCAL MT (14:20),
# matching every other Gamma_Eod* task — Gamma_EodSummary is 14:00 MT for 16:00 ET.
#
# The ET date comes from et_clock.py, never from Get-Date: local is MT and ET is
# local+2, so a naive local date is wrong for any fire after 22:00 MT.
#
# $0 — pure Python, no LLM, no MCP, no orders. Read-only except the shadow ledger.

$ErrorActionPreference = "Continue"

$repoRoot   = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$venvPython = Join-Path $repoRoot "backtest\.venv\Scripts\python.exe"
$logFile    = Join-Path $repoRoot "automation\state\trendline-shadow.log"
$logDir     = Split-Path -Parent $logFile

if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }

$exe = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $exe) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] no python found" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}

# ET date via the DST-aware clock (TZ-SYSTEMIC fix — never Get-Date, never bash TZ)
# et_clock.py has a __main__ that PRINTS a human line but takes no flags (there is no
# argparse in it), so the date is read by importing et_now rather than by passing a
# switch it does not have.
$etDate = (& $exe -c "import sys;sys.path.insert(0,r'$repoRoot\setup\scripts');from et_clock import et_now;print(et_now().strftime('%Y-%m-%d'))")
if ($LASTEXITCODE -ne 0 -or -not $etDate) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [ERROR] et_clock unreadable -- refusing to guess ET" | Out-File -FilePath $logFile -Append -Encoding utf8
    exit 1
}
$etDate = $etDate.Trim()

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [START] trendline-shadow date=$etDate" | Out-File -FilePath $logFile -Append -Encoding utf8

$out = & $exe (Join-Path $repoRoot "setup\scripts\trendline_shadow.py") --date $etDate 2>&1
$rc = $LASTEXITCODE
$out | Out-File -FilePath $logFile -Append -Encoding utf8

# Exit 2 means the bar file for that session never landed. That is a FAILURE, and it
# has to reach STATUS.md — a silently-empty ledger reads downstream as "no trendlines
# today", which is the exact confusion this whole ledger exists to prevent (C7).
if ($rc -eq 2) {
    $status = Join-Path $repoRoot "automation\overnight\STATUS.md"
    if (Test-Path $status) {
        $text = Get-Content $status -Raw
        $marker = "## Known broken"
        $line = "- [$etDate] TRENDLINE-SHADOW BLIND :: no usable 5m bars for $etDate " +
                "(cumulative spy_5m file did not refresh) :: EOD trendline section will " +
                "read BLIND :: re-run: backtest/.venv/Scripts/python.exe " +
                "setup/scripts/trendline_shadow.py --date $etDate"

        # Recreate the section when missing rather than dropping the report -- the June
        # 2026 outage (test_status_known_broken_section_2026_08_20.py): the heading rolled
        # into the monthly archive and every writer that merely checked for it discarded
        # its failures in silence for two months.
        if (-not $text.Contains($marker)) { $text = $marker + "`r`n`r`n" + $text }

        # Insert by INDEX, not by matching "$marker`n". STATUS.md is CRLF, so searching
        # for the marker followed by a bare LF matched nothing and this whole escalation
        # no-op'd silently -- the same failure mode one level down. IndexOf is agnostic
        # to the line ending, so it cannot rot if the file is ever rewritten as LF.
        $at = $text.IndexOf($marker) + $marker.Length
        $text = $text.Substring(0, $at) + "`r`n`r`n" + $line + $text.Substring($at)
        Set-Content -Path $status -Value $text -Encoding utf8
    }
}

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [DONE] rc=$rc" | Out-File -FilePath $logFile -Append -Encoding utf8
exit $rc
