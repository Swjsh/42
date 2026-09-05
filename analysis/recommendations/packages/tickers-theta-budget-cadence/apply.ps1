#requires -Version 5.1
<#
.SYNOPSIS
  Applies the tickers-theta-budget-cadence package (packet row `tickers-theta-budget-cadence`). CONFIG FREEZE: refuses unless
  $env:GAMMA_FREEZE_OVERRIDE = "1". -DryRun prints the plan and changes nothing.
#>
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Repo = "C:\Users\jackw\Desktop\42"
$PkgDir = $PSScriptRoot
$Patch = Join-Path $PkgDir "change.patch"
$Python = Join-Path $Repo "backtest\.venv\Scripts\python.exe"

$plan = @(
    "1. git apply `"$Patch`"",
    "2. <TODO: Unregister-ScheduledTask / other organ-specific stop action, if any>",
    "3. $Python `"$PkgDir\guard_test.py`"  -- refuse (git apply -R the patch) if non-zero exit",
    "4. $Python backtest\tests\run_safety_gate.py  -- refuse if non-zero exit",
    "5. Report APPLIED only if 3 and 4 both exit 0"
)

if ($DryRun) {
    Write-Output "DRY RUN -- plan only, nothing on disk or in Task Scheduler changes:"
    $plan | ForEach-Object { Write-Output "  $_" }
    exit 0
}

if ($env:GAMMA_FREEZE_OVERRIDE -ne "1") {
    Write-Error "CONFIG FREEZE (2026-08-31 -> 2026-10-30): refusing to apply without `$env:GAMMA_FREEZE_OVERRIDE = '1'`."
    exit 2
}

if (-not (Test-Path $Patch)) { Write-Error "Patch not found: $Patch"; exit 1 }
if ((Get-Item $Patch).Length -eq 0) { Write-Error "change.patch is still the empty scaffold placeholder -- fill it in before applying."; exit 1 }

Push-Location $Repo
try {
    Write-Output "Applying $Patch ..."
    git apply $Patch
    if ($LASTEXITCODE -ne 0) { throw "git apply failed (exit $LASTEXITCODE)" }

    # TODO: organ-specific stop action (e.g. Unregister-ScheduledTask -TaskName ... -Confirm:$false)

    Write-Output "Running guard_test.py ..."
    & $Python (Join-Path $PkgDir "guard_test.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "guard_test.py is RED -- reverting patch."
        git apply -R $Patch
        exit 1
    }

    Write-Output "Running backtest/tests/run_safety_gate.py ..."
    & $Python (Join-Path $Repo "backtest\tests\run_safety_gate.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "run_safety_gate.py is RED -- reverting patch."
        git apply -R $Patch
        exit 1
    }

    Write-Output "APPLIED: tickers-theta-budget-cadence"
}
finally {
    Pop-Location
}
