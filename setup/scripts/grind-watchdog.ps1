# Grind watchdog — checks every 60s, restarts mass_grind if dead.
# Launched via wscript shim to avoid window flash. Self-logs to watchdog.log.
param([int]$IntervalSec = 60)

$python  = "C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe"
$workdir = "C:\Users\jackw\Desktop\42\backtest"
$stdout  = "C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-stdout.log"
$stderr  = "C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-stderr.log"
$prog    = "C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-progress.jsonl"
$logfile = "C:\Users\jackw\Desktop\42\analysis\recommendations\mass-grind-watchdog.log"

function Write-Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$ts  $msg" | Add-Content $logfile
}

Write-Log "Watchdog started (interval=${IntervalSec}s)"

while ($true) {
    Start-Sleep -Seconds $IntervalSec

    $lines = 0
    if (Test-Path $prog) {
        $lines = (Get-Content $prog | Measure-Object -Line).Lines
    }
    if ($lines -ge 3360) {
        Write-Log "Grind complete ($lines lines). Exiting."
        break
    }

    # Use Get-Process on the venv python exe to avoid false-positive WMI commandline matches
    $grindProcs = Get-WmiObject Win32_Process | Where-Object {
        $_.ExecutablePath -like "*backtest*.venv*python*" -and
        $_.CommandLine -like "*mass_grind*" -and
        $_.CommandLine -notlike "*phase2*"
    }

    if ($grindProcs) {
        $pids = ($grindProcs | ForEach-Object { $_.ProcessId }) -join ","
        Write-Log "OK  $lines/3360  PIDs=$pids"
    } else {
        Write-Log "DEAD at $lines/3360 — restarting"
        # Kill any orphaned spawn workers first
        Get-WmiObject Win32_Process | Where-Object {
            $_.ExecutablePath -like "*backtest*.venv*python*" -and
            $_.CommandLine -like "*multiprocessing.spawn*"
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

        Start-Process -FilePath $python `
            -ArgumentList "-m", "autoresearch.mass_grind" `
            -WorkingDirectory $workdir `
            -WindowStyle Hidden `
            -RedirectStandardOutput $stdout `
            -RedirectStandardError $stderr
        Write-Log "Restarted."
    }
}
