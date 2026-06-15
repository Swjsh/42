# Launch TradingView Desktop (MSIX version) with Chrome DevTools Protocol enabled
# Must use UseShellExecute=$false to bypass the MSIX package activator,
# which strips --remote-debugging-port when launching via ShellExecute/Start-Process default.
#
# Usage: .\setup\launch_tv_debug.ps1 [-Port 9222] [-Kill]

param(
    [int]$Port = 9222,
    [switch]$Kill
)

$pkg = Get-AppxPackage -Name "TradingView.Desktop" -ErrorAction SilentlyContinue
if (-not $pkg) {
    Write-Error "TradingView Desktop not found. Download from tradingview.com."
    exit 1
}

$tvExe = Join-Path $pkg.InstallLocation "TradingView.exe"

if ($Kill) {
    taskkill /F /IM TradingView.exe 2>$null
    Start-Sleep -Seconds 2
}

Write-Host "Launching TradingView with --remote-debugging-port=$Port ..."
Write-Host "Exe: $tvExe"

$psi = New-Object System.Diagnostics.ProcessStartInfo($tvExe, "--remote-debugging-port=$Port")
$psi.UseShellExecute = $false
$psi.WorkingDirectory = $pkg.InstallLocation
$proc = [System.Diagnostics.Process]::Start($psi)

Write-Host "PID: $($proc.Id) - waiting for CDP..."

$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest "http://localhost:$Port/json/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        $info = $r.Content | ConvertFrom-Json
        Write-Host ""
        Write-Host "CDP ready at http://localhost:$Port"
        Write-Host "Browser: $($info.Browser)"
        Write-Host "WebSocket: $($info.webSocketDebuggerUrl)"
        $ready = $true
        break
    } catch { Write-Host "." -NoNewline }
}

if (-not $ready) {
    Write-Warning "CDP not responding after 20s. TradingView may still be loading - try tv_health_check in Claude Code."
}
