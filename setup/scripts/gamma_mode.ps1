# gamma_mode.ps1 -- J's off switch / gaming switch for the Station (GAMMA-STATION item 4/8, 2026-09-13).
#   -Mode gaming : local inference PAUSES (Station loop yields; routed fires fall back to the Claude path), every
#                  loaded Ollama model is unloaded from VRAM right now so the whole GPU is J's.
#   -Mode off    : same as gaming but semantically "Station off" (use it when you want the old behaviour back).
#   -Mode work   : Station on (default when the file is absent).
#   -Mode status : print the current mode.
# Writes automation/state/station/mode.json. Read by station_loop.py (yield) and _brain.ps1 (Resolve-BrainModel).
# Never opens a console window when launched through setup/scripts/run_exe_hidden.vbs (desktop shortcuts).
param(
    [ValidateSet("gaming", "work", "off", "status")]
    [string]$Mode = "status"
)
$ErrorActionPreference = "SilentlyContinue"
$root = "C:\Users\jackw\Desktop\42"
$file = Join-Path $root "automation\state\station\mode.json"

if ($Mode -eq "status") {
    if (Test-Path $file) { Get-Content $file -Raw } else { '{"mode": "work", "note": "no mode file -> work"}' }
    exit 0
}

New-Item -ItemType Directory -Force -Path (Split-Path $file) | Out-Null
$obj = [ordered]@{
    mode          = $Mode
    changed_local = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    changed_by    = "gamma_mode.ps1"
    note          = $(if ($Mode -eq "work") { "Station on: loop runs, routed fires use the local brain" } else { "GPU reserved for J: loop yields, routed fires use the Claude path, models unloaded" })
}
[IO.File]::WriteAllText($file, ($obj | ConvertTo-Json), [Text.UTF8Encoding]::new($false))   # no BOM: python readers

$unloaded = @()
if ($Mode -in @("gaming", "off")) {
    $ps = & ollama ps 2>$null | Select-Object -Skip 1
    foreach ($line in $ps) {
        $name = ($line -split '\s+')[0]
        if ($name) { & ollama stop $name 2>$null | Out-Null; $unloaded += $name }
    }
}
$log = Join-Path $root "automation\state\logs\gamma-mode.log"
Add-Content -Path $log -Value ((Get-Date).ToString("yyyy-MM-dd HH:mm:ss") + " mode=" + $Mode + " unloaded=[" + ($unloaded -join ",") + "]")
"mode=$Mode written; unloaded: $($unloaded -join ', ')"
