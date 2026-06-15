#!/usr/bin/env pwsh
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    'C:\Users\jackw\Desktop\42\setup\scripts\launch-v14-enhanced-stage1.ps1',
    [ref]$tokens,
    [ref]$errors
) | Out-Null

if ($errors.Count -eq 0) {
    Write-Output "PARSE OK"
} else {
    Write-Output "PARSE ERRORS:"
    foreach ($e in $errors) {
        Write-Output ("  line " + $e.Extent.StartLineNumber + ": " + $e.Message)
    }
}
