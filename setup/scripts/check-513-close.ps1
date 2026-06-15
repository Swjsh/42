#!/usr/bin/env pwsh
$ErrorActionPreference = "Continue"
# Last 6 bars of 5/13 from the extended CSV
$rows = Get-Content 'C:\Users\jackw\Desktop\42\backtest\data\spy_5m_2026-05-08_2026-05-13.csv' | Select-Object -Last 6
foreach ($row in $rows) {
    Write-Output $row
}
Write-Output ""
Write-Output "--- 5/13 daily summary ---"
Write-Output "First open / final close from extended CSV"
$all = Get-Content 'C:\Users\jackw\Desktop\42\backtest\data\spy_5m_2026-05-08_2026-05-13.csv'
$may13 = $all | Where-Object { $_ -like "*2026-05-13*" }
Write-Output ("5/13 bar count: " + $may13.Count)
$first513 = $may13 | Select-Object -First 1
$last513 = $may13 | Select-Object -Last 1
Write-Output ("first: " + $first513)
Write-Output ("last:  " + $last513)
