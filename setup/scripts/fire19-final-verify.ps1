#!/usr/bin/env pwsh
# Fire #19 final verification — confirm v15 pin + TV CDP after recovery
$ErrorActionPreference = "Continue"

$p = Get-Content 'C:\Users\jackw\Desktop\42\automation\state\params.json' -Raw | ConvertFrom-Json
Write-Output ("rule_version: " + $p.rule_version)
Write-Output ("ratified_at: " + $p.rule_version_ratified_at)

$hbLine = Select-String -Path 'C:\Users\jackw\Desktop\42\automation\prompts\heartbeat.md' -Pattern 'RULE_VERSION\s*=\s*' | Select-Object -First 1
Write-Output ("heartbeat.md RULE_VERSION line: " + $hbLine.Line.Trim())

$pmLine = Select-String -Path 'C:\Users\jackw\Desktop\42\automation\prompts\premarket.md' -Pattern 'RULE_VERSION_EXPECTED' | Select-Object -First 1
Write-Output ("premarket.md pin: " + $pmLine.Line.Trim())

$cdp = Test-NetConnection -ComputerName 127.0.0.1 -Port 9222 -InformationLevel Quiet -WarningAction SilentlyContinue
Write-Output ("TV CDP port 9222 listening: " + $cdp)

# Show TV PIDs for forensics
$tvProcs = Get-Process | Where-Object { $_.ProcessName -like '*TradingView*' } | Select-Object Id, ProcessName, StartTime
foreach ($proc in $tvProcs) {
    Write-Output ("TV PID " + $proc.Id + " (" + $proc.ProcessName + ") started " + $proc.StartTime)
}
