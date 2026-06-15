#!/usr/bin/env pwsh
$ErrorActionPreference = "Continue"
$cacheDir = 'C:\Users\jackw\Desktop\42\backtest\data\options'
$all = Get-ChildItem $cacheDir -File

Write-Output "--- 4/29 J ANCHOR ---"
$apr29 = $all | Where-Object { $_.Name -like '*250429*' }
Write-Output ("apr29_files: " + $apr29.Count)
$apr29 | Select-Object -First 6 Name

Write-Output ""
Write-Output "--- 5/12 J ANCHOR ---"
$may12 = $all | Where-Object { $_.Name -like '*250512*' }
Write-Output ("may12_files: " + $may12.Count)
$may12 | Select-Object -First 6 Name

Write-Output ""
Write-Output "--- 5/13 ENGINE WIN DAY ---"
$may13 = $all | Where-Object { $_.Name -like '*250513*' }
Write-Output ("may13_files: " + $may13.Count)
$may13 | Select-Object -First 6 Name

Write-Output ""
Write-Output "--- ZERO-BYTE FILES ---"
$zero = $all | Where-Object { $_.Length -eq 0 }
Write-Output ("zero_byte_count: " + $zero.Count)
$zero | Select-Object Name
