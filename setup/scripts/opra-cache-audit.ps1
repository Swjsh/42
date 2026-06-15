#!/usr/bin/env pwsh
# OPRA cache integrity audit - verify all 7,358+ contracts intact, no zero-byte files,
# spot-check J anchor day strikes are present.
$ErrorActionPreference = "Continue"

$cacheDir = 'C:\Users\jackw\Desktop\42\backtest\data\options'

Write-Output "=== OPRA CACHE INTEGRITY AUDIT ==="
Write-Output ("audit_at: " + (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"))
Write-Output ""

$all = Get-ChildItem $cacheDir -File
$total = $all.Count
$zeroByte = ($all | Where-Object { $_.Length -eq 0 }).Count
$small = ($all | Where-Object { $_.Length -lt 100 }).Count
$normal = ($all | Where-Object { $_.Length -ge 1000 }).Count

Write-Output ("total_csv:  " + $total)
Write-Output ("zero_byte:  " + $zeroByte)
Write-Output ("under_100B: " + $small)
Write-Output ("over_1KB:   " + $normal)
Write-Output ""

Write-Output "--- J ANCHOR DAY SPOT-CHECKS ---"

# 4/29 J anchor: SPY 710P x6 (J's actual trade)
$check429 = $all | Where-Object { $_.Name -match '^SPY250429.*710' }
Write-Output ("4/29 SPY 710P file count: " + $check429.Count)

# 5/01: 721P x20
$check501 = $all | Where-Object { $_.Name -match '^SPY250501.*721' }
Write-Output ("5/01 SPY 721P file count: " + $check501.Count)

# 5/04: 721P x10
$check504 = $all | Where-Object { $_.Name -match '^SPY250504.*721' }
Write-Output ("5/04 SPY 721P file count: " + $check504.Count)

# 5/12 J anchor: 736.13 break
$check512 = $all | Where-Object { $_.Name -match '^SPY250512.*736' }
Write-Output ("5/12 SPY 736 file count: " + $check512.Count)

# 5/13 (yesterday's actual J real-money + engine): 738C
$check513 = $all | Where-Object { $_.Name -match '^SPY250513.*738' }
Write-Output ("5/13 SPY 738 file count: " + $check513.Count)
Write-Output ""

Write-Output "--- DATE COVERAGE ---"
# Group by yymmdd from filename
$dateGroup = $all | ForEach-Object {
    if ($_.Name -match '^SPY(\d{6})') {
        $matches[1]
    }
} | Group-Object | Sort-Object Name

Write-Output ("unique_trading_dates: " + $dateGroup.Count)
Write-Output ("first_date: " + $dateGroup[0].Name)
Write-Output ("last_date:  " + $dateGroup[-1].Name)

# Average contracts per date
$avgPerDate = [math]::Round(($dateGroup | Measure-Object Count -Average).Average, 1)
Write-Output ("avg_contracts_per_date: " + $avgPerDate)
