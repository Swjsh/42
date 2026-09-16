# hq_capture.ps1 -- full-resolution REAL-SCREEN capture of the live HQ world (the only proof a scene change counts; the Browser pane hides tabs and pauses the canvas). Moved into the repo 2026-09-14 from the overnight scratchpad so every builder and the Station loop use ONE tool.
# `?tour=0` (no other cam param) is the documented OVERVIEW shot -- lands on the exact
# OVERVIEW_CAM_POS/DEFAULT_LOOKAT pose (MONITORS-READABLE fix, 2026-09-15: this was previously
# bugged -- `?tour=0` alone parked wherever the Canvas' initial camera happened to be, inside the
# hub near the core, not the overview; fixed in Scene.tsx#CameraRig + lib/hq-camera-params.ts
# #shouldParkTourAtOverview). Add `&cam=x,y,z,tx,ty,tz` for an arbitrary pose instead.
# Opens ONE private kiosk Edge window on the PC monitor (no sync dialog, no profile), waits
# for the world to load and settle, copies the primary screen to a PNG, then kills only the
# Edge process tree it launched (matched by the unique --user-data-dir it was given).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File hq_capture.ps1 -Out <png> [-Url <url>] [-SettleSec 35]
#
# World-2 MOTION-FIX (2026-09-14): -Frames/-IntervalMs added -- grabs N consecutive
# CopyFromScreen frames spaced IntervalMs apart (after the same settle window) instead of
# one, so a Pillow analyzer (setup/scripts/hq_frames_analyze.py) can measure real per-frame
# pixel deltas on J's actual 480Hz monitor -- the "owed video" proof instrument for motion/
# jitter fixes, where a single screenshot cannot show motion at all. -Frames 1 (the default)
# is BYTE-IDENTICAL to this script's prior behavior (same single $Out path, same inline
# black-frame check, no "-01" suffix) -- only -Frames 2+ takes the new numbered-file path.
param(
    [string]$Out = "",
    [string]$Url = "http://127.0.0.1:3000/hq?tier=ultra&kiosk=1",
    [int]$SettleSec = 35,
    [int]$Frames = 1,
    [int]$IntervalMs = 0
)
$ErrorActionPreference = "Continue"
# Gaming guard (J 2026-09-14 20:5x ET: "stop opening it up on microsoft edge so you dont steal focus ...
# go silent so i can game"): when automation/state/station/mode.json says gaming/off, a kiosk Edge on
# J's own monitor is exactly the focus theft he banned. Refuse loudly unless HQ_CAPTURE_FORCE=1 marks a
# deliberate exception. Verification while J games goes through the Claude desktop Browser pane / DOM.
$stationModeFile = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) "automation\state\station\mode.json"
if ((Test-Path $stationModeFile) -and (-not $env:HQ_CAPTURE_FORCE)) {
    try {
        $stationMode = (Get-Content $stationModeFile -Raw | ConvertFrom-Json).mode
        if ($stationMode -eq "gaming" -or $stationMode -eq "off") {
            Write-Output "REFUSED: station mode is '$stationMode' (J is gaming) -- no kiosk capture on J's monitor; verify via the Claude desktop Browser pane instead"
            exit 2
        }
    } catch { }
}
if ($Out -eq "") { $Out = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) ("automation\state\station\captures\hq-" + (Get-Date -Format "yyyyMMdd-HHmm") + ".png") }
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { $edge = "C:\Program Files\Microsoft\Edge\Application\msedge.exe" }
$profileDir = Join-Path $env:TEMP ("hq-capture-profile-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
$args = @(
    "--inprivate", "--kiosk", "--no-first-run", "--no-default-browser-check", "--disable-sync",
    "--window-position=0,0", "--window-size=2560,1440", "--start-fullscreen",
    ("--user-data-dir=" + $profileDir),
    $Url
)
$t0 = Get-Date
$p = Start-Process -FilePath $edge -ArgumentList $args -PassThru
Write-Output ("edge launched pid=" + $p.Id + " profile=" + $profileDir)
Start-Sleep -Seconds $SettleSec

# Screen bounds of the primary display (physical pixels are what CopyFromScreen reads under
# the process's DPI awareness; report them so the caller can judge the capture).
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds

function Save-OneFrame([string]$path) {
    $bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $g.Dispose()
    $dir = Split-Path $path -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    # Cheap black-frame check: sample a grid of pixels; a sleeping monitor / DWM off gives all-black.
    $nonBlack = 0; $samples = 0
    for ($x = 20; $x -lt $bounds.Width; $x += 160) {
        for ($y = 20; $y -lt $bounds.Height; $y += 160) {
            $c = $bmp.GetPixel($x, $y); $samples++
            if (($c.R + $c.G + $c.B) -gt 30) { $nonBlack++ }
        }
    }
    $bmp.Dispose()
    Write-Output ("saved " + $path + " " + $bounds.Width + "x" + $bounds.Height + " nonblack=" + $nonBlack + "/" + $samples)
}

if ($Frames -le 1) {
    # Unchanged single-shot path -- byte-identical to this script's behavior before -Frames existed.
    Save-OneFrame $Out
} else {
    # Numbered-sequence path: "<Out>-01.png" .. "<Out>-NN.png", IntervalMs apart (no sleep
    # after the LAST frame -- nothing left to wait for).
    $digits = [Math]::Max(2, [string]$Frames.ToString().Length)
    for ($i = 1; $i -le $Frames; $i++) {
        $suffix = $i.ToString().PadLeft($digits, '0')
        Save-OneFrame ($Out + "-" + $suffix + ".png")
        if ($i -lt $Frames -and $IntervalMs -gt 0) { Start-Sleep -Milliseconds $IntervalMs }
    }
}

# Kill ONLY the Edge tree we launched: every msedge.exe whose command line carries our profile dir.
$mine = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like ("*" + $profileDir + "*") }
$killed = 0
foreach ($m in $mine) { try { Stop-Process -Id $m.ProcessId -Force -ErrorAction Stop; $killed++ } catch { } }
Start-Sleep -Seconds 2
try { Remove-Item -Recurse -Force $profileDir -ErrorAction SilentlyContinue } catch { }
Write-Output ("edge tree killed=" + $killed + " elapsed=" + [int]((Get-Date) - $t0).TotalSeconds + "s")
