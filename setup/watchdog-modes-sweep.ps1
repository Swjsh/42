# Watchdog for the autoresearch modes sweep.
# Runs every 30 minutes via Task Scheduler.
#
# Behaviour:
#   1. If a sweep python process is currently running -> log status, exit.
#   2. If NOT running:
#        a. Read per-mode iteration counts from state.json files.
#        b. If every mode has >= TARGET_ITERATIONS -> "DONE", regenerate
#           summary, exit cleanly.
#        c. Otherwise -> launch another batch of $BatchSize iterations with
#           --no-reset (continues from current state), in detached background.
#
# Output:
#   backtest/autoresearch/_state/watchdog.log  (append-only, every tick)
#   backtest/autoresearch/_state/sweep.log     (each batch tees here)
#
# Manual invocation (for testing):
#   .\setup\watchdog-modes-sweep.ps1 -TargetIterations 60 -BatchSize 10

param(
    [int]$TargetIterations = 60,
    [int]$BatchSize = 10
)

$ErrorActionPreference = 'Continue'
$Repo = "C:\Users\jackw\Desktop\42"
$Venv = "$Repo\backtest\.venv\Scripts\python.exe"
$StateDir = "$Repo\backtest\autoresearch\_state"
$WatchdogLog = "$StateDir\watchdog.log"
$SweepLog = "$StateDir\sweep.log"
$SummaryFile = "$Repo\analysis\autoresearch_results.md"

if (-not (Test-Path $StateDir)) { New-Item -Path $StateDir -ItemType Directory | Out-Null }

function Write-WatchdogLog {
    param([string]$Message)
    $line = "[$([DateTime]::Now.ToString('yyyy-MM-dd HH:mm:ss'))] $Message"
    Add-Content -Path $WatchdogLog -Value $line
    Write-Host $line
}

# --- 1. Is the sweep currently running? ---
# May match multiple processes (parent + child). Pick the workhorse (highest RAM).
$running = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine -match 'autoresearch\.loop' })

# Always regenerate the smart watchdog report (cheap, no LLM).
& $Venv -m autoresearch.watchdog_report 2>&1 | Out-Null

if ($running.Count -gt 0) {
    $procs = @($running | ForEach-Object {
        Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue
    } | Where-Object { $_ })
    $proc = $procs | Sort-Object WorkingSet64 -Descending | Select-Object -First 1
    if ($proc) {
        $runMin = [math]::Round(((Get-Date) - $proc.StartTime).TotalMinutes, 1)
        $cpu = if ($proc.CPU) { [math]::Round([double]$proc.CPU, 0) } else { 0 }
        $ramMB = [math]::Round([double]$proc.WorkingSet64 / 1MB, 0)
        # Last meaningful line from sweep.log (KEEP/REVERT/baseline/STARTING/FINISHED)
        $lastEvent = "(no events yet)"
        if (Test-Path $SweepLog) {
            $lastEvent = (Select-String -Path $SweepLog `
                          -Pattern '(STARTING MODE|FINISHED MODE|KEEP iter|REVERT iter|TRAIN:|VALIDATE:|baseline)' `
                          -SimpleMatch:$false -ErrorAction SilentlyContinue |
                          Select-Object -Last 1).Line
            if (-not $lastEvent) { $lastEvent = "(no sweep events yet)" }
        }
        Write-WatchdogLog "RUNNING pid=$($proc.Id) runtime=${runMin}min cpu=${cpu}s ram=${ramMB}MB last='$lastEvent'"
    } else {
        $pids = ($running | ForEach-Object { $_.ProcessId }) -join ','
        Write-WatchdogLog "RUNNING pids=$pids (Get-Process lookup failed for all)"
    }
    exit 0
}

# --- 2. Not running -> check per-mode iteration counts ---
$modes = @('strict', 'balanced', 'aggressive')
$counts = @{}
$allReached = $true
foreach ($mode in $modes) {
    $statePath = "$StateDir\$mode\state.json"
    if (Test-Path $statePath) {
        try {
            $state = Get-Content $statePath -Raw | ConvertFrom-Json
            $counts[$mode] = $state.iteration
        } catch {
            $counts[$mode] = -1
        }
    } else {
        $counts[$mode] = 0
    }
    if ($counts[$mode] -lt $TargetIterations) { $allReached = $false }
}

$countSummary = ($modes | ForEach-Object { "${_}=$($counts[$_])" }) -join ' '

if ($allReached) {
    Write-WatchdogLog "DONE all modes have reached target $TargetIterations iters [$countSummary]; regenerating summary"
    $summaryOut = & $Venv -m autoresearch.summarize --out $SummaryFile 2>&1 | Out-String
    Write-WatchdogLog "summary: $SummaryFile"
    exit 0
}

# --- 3. Restart with another batch ---
Write-WatchdogLog "STOPPED [$countSummary] - launching batch of $BatchSize iters/mode (--no-reset)"

# Detach so this watchdog tick can return immediately. The new process is
# parented to the system, not to us, so it survives our exit.
$logHandle = "$StateDir\sweep.log"
$cmd = @"
Set-Location '$Repo\backtest';
& '$Venv' -m autoresearch.loop ``
    --modes strict balanced aggressive ``
    --iterations $BatchSize ``
    --train-start 2025-01-01 --train-end 2026-02-13 ``
    --validate-start 2026-02-14 --validate-end 2026-05-07 2>&1 |
    Tee-Object -FilePath '$logHandle' -Append
"@

Start-Process -FilePath "powershell.exe" -ArgumentList @(
    "-NoProfile",
    "-WindowStyle", "Hidden",
    "-Command", $cmd
) -WindowStyle Hidden -PassThru | ForEach-Object {
    Write-WatchdogLog "launched detached pid=$($_.Id)"
}

exit 0
