#!/usr/bin/env pwsh
$pythonProcs = Get-Process -Name 'python' -ErrorAction SilentlyContinue
if ($pythonProcs) {
    foreach ($p in $pythonProcs) {
        Write-Output ("python PID " + $p.Id + " StartTime: " + $p.StartTime)
    }
} else {
    Write-Output "no python procs found"
}
