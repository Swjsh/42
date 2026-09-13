# allow-tv-face-firewall.ps1 -- ONE inbound Windows Firewall rule so the TV can load Gamma's face.
# J runs this himself (right-click -> Run with PowerShell as Administrator). Never run by automation:
# Windows security settings are J's hands only (GAMMA-STATION security posture, 2026-09-13).
#
# What it allows: TCP port 80 on this PC, ONLY from the TV's LAN address, ONLY to the Python interpreter
# that runs setup/scripts/station_serve.py (which itself binds the PC's LAN IP and 403s every other client).
# Revoke: Remove-NetFirewallRule -DisplayName "Gamma Station face (TV only)"
param(
    [string]$TvIp = "192.168.0.10",
    [string]$Python = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\python.exe"
)
$name = "Gamma Station face (TV only)"
if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
    Write-Output "rule already exists: $name"
} else {
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow -Protocol TCP -LocalPort 80 `
        -RemoteAddress $TvIp -Program $Python -Profile Private, Public | Out-Null
    Write-Output "created: $name (TCP 80 from $TvIp to $Python)"
}
Get-NetFirewallRule -DisplayName $name | Select-Object DisplayName, Enabled, Profile, Action | Format-Table -AutoSize
