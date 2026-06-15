#!/usr/bin/env pwsh
$ErrorActionPreference = "Continue"
$cacheDir = 'C:\Users\jackw\Desktop\42\backtest\data\options'
$all = Get-ChildItem $cacheDir -File

Write-Output "--- 2026 J ANCHOR DAYS ---"

$days = @(
    @{ Date = '260429'; Note = '4/29/26 J: 710P x6 -> +342' },
    @{ Date = '260501'; Note = '5/01/26 J: 721P x20 -> +470' },
    @{ Date = '260504'; Note = '5/04/26 J: 721P x10 -> +730' },
    @{ Date = '260505'; Note = '5/05/26 J: 722P x20 -> -260' },
    @{ Date = '260506'; Note = '5/06/26 J: 730P x10 -> -300' },
    @{ Date = '260507'; Note = '5/07/26 J: 734C/737C losers' },
    @{ Date = '260512'; Note = '5/12/26 J: 736 break' },
    @{ Date = '260513'; Note = '5/13/26 J real-money + engine' }
)

foreach ($d in $days) {
    $files = $all | Where-Object { $_.Name -like ('*' + $d.Date + '*') }
    Write-Output ($d.Date + " (" + $d.Note + "): " + $files.Count + " files")
    if ($files.Count -gt 0) {
        $strikes = $files | ForEach-Object {
            if ($_.Name -match ('SPY' + $d.Date + '([CP])(\d+)')) {
                $cp = $matches[1]
                $strike = [int]$matches[2] / 1000.0
                "$cp$strike"
            }
        } | Sort-Object | Select-Object -Unique
        $minStrike = ($strikes | ForEach-Object { [double]($_ -replace '[CP]', '') } | Measure-Object -Min).Minimum
        $maxStrike = ($strikes | ForEach-Object { [double]($_ -replace '[CP]', '') } | Measure-Object -Max).Maximum
        Write-Output ("  strike range: " + $minStrike + " to " + $maxStrike)
    }
}
