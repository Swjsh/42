#requires -Version 5.1
<#
.SYNOPSIS
  Launch GAMMA HQ -- the always-on VISIBLE terminal window where Gamma narrates,
  in first person, what it is doing and wanting RIGHT NOW.

  THE GAP THIS CLOSES (J, repeated ask): "Gamma works but is invisible." This
  opens ONE glanceable window that stays up on J's desktop and redraws itself
  every 30s from setup/scripts/gamma_hq.py.

  INTENTIONAL WINDOW -- SANCTIONED INVERSE OF THE WINDOW-LEAK DOCTRINE (OP-27
  L41). Every other launcher in this directory exists to make sure NOTHING
  flashes a console (pythonw + CREATE_NO_WINDOW + the wscript/vbs hidden chain --
  see audit_window_leak_compliance.py, whose entire job is catching accidental
  visible windows on scheduled-task ticks). This script is the deliberate,
  documented exception: it opens a REAL, VISIBLE PowerShell window on purpose,
  and is meant to be run once at logon (via install-gamma-hq.ps1's Startup
  shortcut) or by hand. Do not "fix" this by hiding it, and do not let a future
  window-leak sweep flag this file -- it is not scheduled via Task Scheduler
  (see install-gamma-hq.ps1's own header for why that also keeps it outside
  audit_window_leak_compliance.py check 4's live-registry scan).

  REAPER EXEMPTION: gamma_hq.py runs forever (an intentional infinite render
  loop) as an interpreter process. setup/scripts/_shared.ps1's
  Stop-StaleClaudeProcesses -- called at the top of many run-*.ps1 task scripts
  throughout the day -- reaps any stale such process whose CommandLine
  references this repo's WorkDir and is older than 5 minutes, UNLESS it also
  matches an $EXEMPT_DAEMONS substring. 'backtest\.venv' is already on that list
  (the long-running backtest-grind exemption), so launching via the FULL venv
  interpreter path below keeps GAMMA HQ safe from the reaper by construction. Do
  NOT swap in the system interpreter for this script -- that would silently lose
  the exemption and the window would die on the next scheduled-task tick that
  happens to call the reaper (an intermittent, very confusing failure mode if it
  ever regresses).

.DESCRIPTION
  Idempotent: if a powershell.exe process already has gamma_hq.py on its command
  line, this does nothing and exits 0 rather than opening a second window.
#>
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"

$root       = "C:\Users\jackw\Desktop\42"
$venvPython = Join-Path $root "backtest\.venv\Scripts\python.exe"
$script     = Join-Path $root "setup\scripts\gamma_hq.py"
$title      = "GAMMA HQ"

foreach ($p in @($venvPython, $script)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

# Idempotency check: is a powershell.exe already running gamma_hq.py? We match on
# the CHILD process's CommandLine (what we launch below), not the window Title --
# a Title is only settable AFTER a process starts and isn't a WMI/CIM-queryable
# property up front, so it can't be used to pre-check before spawning.
$already = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and ($_.CommandLine -like "*gamma_hq.py*") }

if ($already) {
    $pids = ($already | ForEach-Object { $_.ProcessId }) -join ", "
    Write-Host "GAMMA HQ already running (pid=$pids) -- not relaunching."
    exit 0
}

# Built as a single-quoted (fully literal) here-string so $Host/$b/$w below are
# NOT expanded by THIS (outer) script -- they must survive verbatim into the
# child powershell's -Command string and be evaluated there. Resize is
# best-effort: Windows Terminal (Win11's default host) largely ignores the
# legacy console BufferSize/WindowSize APIs and manages tab size itself, so this
# is wrapped in try/catch -- if it no-ops or throws, the window still opens, just
# at whatever size the host defaults to.
$resizeAndTitle = @'
$Host.UI.RawUI.WindowTitle = 'GAMMA HQ'
try {
    $b = $Host.UI.RawUI.BufferSize
    $b.Width = 100
    $Host.UI.RawUI.BufferSize = $b
    $w = $Host.UI.RawUI.WindowSize
    $w.Width = 100
    $w.Height = 35
    $Host.UI.RawUI.WindowSize = $w
} catch {}
'@

$launchLine = "& '$venvPython' '$script'"
$inner = $resizeAndTitle + "`n" + $launchLine

Start-Process -FilePath "powershell.exe" `
    -ArgumentList @('-NoExit', '-Command', $inner) `
    -WindowStyle Normal

Write-Host "GAMMA HQ launched (title='$title')."
