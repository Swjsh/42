#requires -Version 5.1
<#
.SYNOPSIS
  Install GAMMA HQ autostart -- creates a Startup-folder shortcut (fires at every
  logon) plus a Desktop shortcut (manual launch), both pointing at
  gamma-hq-launch.ps1. Does NOT launch GAMMA HQ itself: nothing opens until the
  next logon, or until J double-clicks a shortcut / runs the launcher by hand.

  SHORTCUTS, NOT A SCHEDULED TASK -- BY DESIGN. GAMMA HQ is a manually-supervised,
  deliberately-visible window (see gamma-hq-launch.ps1's header for the full
  window-leak-doctrine rationale), not a background scheduled job, so it belongs
  in the Startup folder (a per-user logon mechanism), not Task Scheduler. This
  also means it sits outside audit_scheduled_tasks.py / audit_window_leak_
  compliance.py's live Task Scheduler enumeration (check 4) -- correctly so: that
  audit exists to catch ACCIDENTAL visible windows on scheduled ticks, and this
  is the one INTENTIONAL visible window on the whole rig.

.PARAMETER Uninstall
  Removes both shortcuts (Startup + Desktop) if present. Does not stop an
  already-running GAMMA HQ window -- close that by hand (Ctrl+C / close the
  window) if desired.
#>
[CmdletBinding()] param([switch]$Uninstall)
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$launcher     = Join-Path $root "setup\scripts\gamma-hq-launch.ps1"
$shortcutName = "GammaHQ.lnk"

$startupDir = [Environment]::GetFolderPath("Startup")
$desktopDir = [Environment]::GetFolderPath("Desktop")
$startupLnk = Join-Path $startupDir $shortcutName
$desktopLnk = Join-Path $desktopDir $shortcutName

if ($Uninstall) {
    foreach ($lnk in @($startupLnk, $desktopLnk)) {
        if (Test-Path $lnk) {
            Remove-Item -Path $lnk -Force
            Write-Host "Removed $lnk"
        } else {
            Write-Host "Not present: $lnk"
        }
    }
    Write-Host "GAMMA HQ autostart uninstalled. (Any already-running window is untouched.)"
    return
}

if (-not (Test-Path $launcher)) {
    Write-Error "Required file missing: $launcher"
    exit 1
}

$powershellExe = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path $powershellExe)) {
    # Fall back to PATH resolution if the canonical path is somehow absent.
    $cmd = Get-Command powershell.exe -ErrorAction SilentlyContinue
    if ($cmd) { $powershellExe = $cmd.Source }
    else { Write-Error "powershell.exe not found at $powershellExe or on PATH"; exit 1 }
}

function New-GammaHqShortcut {
    param([Parameter(Mandatory)][string]$Path)
    $wsh = New-Object -ComObject WScript.Shell
    try {
        $sc = $wsh.CreateShortcut($Path)
        $sc.TargetPath = $powershellExe
        $sc.Arguments = "-ExecutionPolicy Bypass -File `"$launcher`""
        $sc.WorkingDirectory = $root
        $sc.Description = "GAMMA HQ -- Gamma's always-on visible status window"
        $sc.WindowStyle = 1  # SW_SHOWNORMAL -- gamma-hq-launch.ps1 opens its own titled window regardless
        $sc.Save()
    } finally {
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wsh)
    }
}

New-GammaHqShortcut -Path $startupLnk
Write-Host "Startup shortcut: $startupLnk"

New-GammaHqShortcut -Path $desktopLnk
Write-Host "Desktop shortcut: $desktopLnk"

Write-Host ""
Write-Host "Installed. GAMMA HQ will open automatically at next logon."
Write-Host "To open it right now instead of waiting for a logon: double-click the"
Write-Host "Desktop shortcut, or run gamma-hq-launch.ps1 directly (this installer"
Write-Host "does NOT launch it)."
Write-Host "Uninstall: setup\scripts\install-gamma-hq.ps1 -Uninstall"
