# hq_capture.ps1 -- full-resolution REAL-SCREEN capture of the live HQ world (the only proof a scene change counts; the Browser pane hides tabs and pauses the canvas). Moved into the repo 2026-09-14 from the overnight scratchpad so every builder and the Station loop use ONE tool.
# Opens ONE private kiosk Edge window on the PC monitor (no sync dialog, no profile), waits
# for the world to load and settle, copies the primary screen to a PNG, then kills only the
# Edge process tree it launched (matched by the unique --user-data-dir it was given).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File hq_capture.ps1 -Out <png> [-Url <url>] [-SettleSec 35]
param(
    [string]$Out = "",
    [string]$Url = "http://127.0.0.1:3000/hq?tier=ultra&kiosk=1",
    [int]$SettleSec = 35
)
$ErrorActionPreference = "Continue"
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
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$g.Dispose()
$dir = Split-Path $Out -Parent
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$bmp.Save($Out, [System.Drawing.Imaging.ImageFormat]::Png)
# Cheap black-frame check: sample a grid of pixels; a sleeping monitor / DWM off gives all-black.
$nonBlack = 0; $samples = 0
for ($x = 20; $x -lt $bounds.Width; $x += 160) {
    for ($y = 20; $y -lt $bounds.Height; $y += 160) {
        $c = $bmp.GetPixel($x, $y); $samples++
        if (($c.R + $c.G + $c.B) -gt 30) { $nonBlack++ }
    }
}
$bmp.Dispose()
Write-Output ("saved " + $Out + " " + $bounds.Width + "x" + $bounds.Height + " nonblack=" + $nonBlack + "/" + $samples)

# Kill ONLY the Edge tree we launched: every msedge.exe whose command line carries our profile dir.
$mine = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" | Where-Object { $_.CommandLine -like ("*" + $profileDir + "*") }
$killed = 0
foreach ($m in $mine) { try { Stop-Process -Id $m.ProcessId -Force -ErrorAction Stop; $killed++ } catch { } }
Start-Sleep -Seconds 2
try { Remove-Item -Recurse -Force $profileDir -ErrorAction SilentlyContinue } catch { }
Write-Output ("edge tree killed=" + $killed + " elapsed=" + [int]((Get-Date) - $t0).TotalSeconds + "s")
