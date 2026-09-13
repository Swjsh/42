#requires -Version 5.1
<#
.SYNOPSIS
  Creates 3 Desktop shortcuts for J's Gamma Station mode switch (GOAL-GAMMA-
  STATION-2026-09-13 item 5's desktop-mode-shortcuts deliverable).

.DESCRIPTION
  "Gamma - Gaming mode", "Gamma - Work mode", "Gamma - Off" each run
  gamma_mode.ps1 -Mode <gaming|work|off> through the SAME hidden
  wscript.exe -> run_exe_hidden.vbs -> powershell.exe chain every other
  silent-rig launcher uses (see install-station-kiosk.ps1's identical
  argument-array-then-join construction) -- double-clicking never flashes a
  console window (CLAUDE.md "silent rig: no console windows ever").

  Idempotent: re-running this script overwrites the same 3 .lnk files with
  identical content via WScript.Shell's CreateShortcut, never duplicates them.
#>
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"

$WorkDir      = "C:\Users\jackw\Desktop\42"
$ScriptsDir   = Join-Path $WorkDir "setup\scripts"
$runExeHidden = Join-Path $ScriptsDir "run_exe_hidden.vbs"
$gammaMode    = Join-Path $ScriptsDir "gamma_mode.ps1"
$psExe        = Join-Path $env:WINDIR "System32\WindowsPowerShell\v1.0\powershell.exe"
$desktop      = [Environment]::GetFolderPath("Desktop")

foreach ($p in @($runExeHidden, $gammaMode, $psExe)) {
    if (-not (Test-Path $p)) {
        Write-Error "Required file missing: $p"
        exit 1
    }
}

$modes = @(
    @{ Name = "Gamma - Gaming mode"; Mode = "gaming" },
    @{ Name = "Gamma - Work mode";   Mode = "work" },
    @{ Name = "Gamma - Off";         Mode = "off" }
)

$shell = New-Object -ComObject WScript.Shell
$created = @()

try {
    foreach ($m in $modes) {
        $lnkPath = Join-Path $desktop ($m.Name + ".lnk")

        # Same array-then-join quoting technique as install-station-kiosk.ps1 --
        # each element becomes one independently-quoted token in
        # run_exe_hidden.vbs's own command line (its "Usage: wscript //nologo
        # run_exe_hidden.vbs <exe-path> [args...]"), which is exactly what
        # powershell.exe's argv parser expects regardless of the quoting.
        $psArgs = @(
            $psExe,
            "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", $gammaMode,
            "-Mode", $m.Mode
        )
        $quoted = $psArgs | ForEach-Object { '"' + $_ + '"' }
        $argumentString = "//nologo `"$runExeHidden`" " + ($quoted -join " ")

        $shortcut = $shell.CreateShortcut($lnkPath)
        $shortcut.TargetPath = "wscript.exe"
        $shortcut.Arguments = $argumentString
        $shortcut.WorkingDirectory = $WorkDir
        $shortcut.Description = "Gamma Station mode: $($m.Mode) (hidden -- no console window)"
        $shortcut.IconLocation = "$psExe,0"
        $shortcut.Save()
        $created += $lnkPath
    }
} finally {
    [Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
}

Write-Output "OK: created/updated $($created.Count) shortcuts:"
$created | ForEach-Object { Write-Output "    $_" }
