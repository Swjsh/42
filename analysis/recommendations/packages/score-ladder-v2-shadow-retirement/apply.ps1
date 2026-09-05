#requires -Version 5.1
<#
.SYNOPSIS
  Applies the score-ladder-v2-shadow-retirement package (packet row
  `score-ladder-v2-shadow-retirement`, checkpoint 2026-09-29). CONFIG FREEZE: refuses
  unless $env:GAMMA_FREEZE_OVERRIDE = "1". -DryRun prints the plan and changes nothing.

.DESCRIPTION
  1. git apply change.patch (retires the nightly ledger writer + tombstones the installer)
  2. Unregister-ScheduledTask -TaskName Gamma_LadderRungShadow
  3. Run guard_test.py -- refuse (git apply -R, re-register nothing) if it is red
  4. Run backtest/tests/run_safety_gate.py -- refuse if red
  Revert: git revert <sha-of-the-applying-commit>, then re-run
  setup/install-ladder-rung-shadow.ps1 to re-register the task.
#>
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Repo = "C:\Users\jackw\Desktop\42"
$PkgDir = $PSScriptRoot
$Patch = Join-Path $PkgDir "change.patch"
$TaskName = "Gamma_LadderRungShadow"
$Python = Join-Path $Repo "backtest\.venv\Scripts\python.exe"

$plan = @(
    "1. git apply `"$Patch`"  (retires backtest/tools/score_ladder_rung_shadow_nightly.py + tombstones setup/install-ladder-rung-shadow.ps1)",
    "2. Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false",
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
    Write-Error "CONFIG FREEZE (2026-08-31 -> 2026-10-30): refusing to apply without `$env:GAMMA_FREEZE_OVERRIDE = '1'`. This package is only applied on its checkpoint day (2026-09-29) by the conductor."
    exit 2
}

if (-not (Test-Path $Patch)) { Write-Error "Patch not found: $Patch"; exit 1 }
if (-not (Test-Path $Python)) { Write-Error "backtest venv python not found: $Python"; exit 1 }

Push-Location $Repo
try {
    Write-Output "Applying $Patch ..."
    git apply $Patch
    if ($LASTEXITCODE -ne 0) { throw "git apply failed (exit $LASTEXITCODE)" }

    Write-Output "Unregistering $TaskName ..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue

    Write-Output "Running guard_test.py ..."
    & $Python (Join-Path $PkgDir "guard_test.py")
    if ($LASTEXITCODE -ne 0) {
        Write-Error "guard_test.py is RED -- reverting patch (task un-registration is NOT reverted automatically; re-run setup\install-ladder-rung-shadow.ps1 to restore it if needed)."
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

    Write-Output "APPLIED: score-ladder-v2-shadow-retirement"
    Write-Output "  Revert: git revert <sha-of-this-commit>; setup\install-ladder-rung-shadow.ps1"
}
finally {
    Pop-Location
}
