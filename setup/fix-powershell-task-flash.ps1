#requires -Version 5.1
<#
.SYNOPSIS
  Convert Gamma scheduled tasks that use a DIRECT `powershell.exe -WindowStyle Hidden`
  action to the proven windowless `wscript -> run_exe_hidden.vbs -> pythonw ->
  run_ps1_hidden.py -> <ps1>` chain.

.WHY (2026-06-20 -- the actual "random black cmd popup" root cause)
  Task Scheduler launching `powershell.exe -WindowStyle Hidden` directly does NOT prevent
  the console window: Windows allocates the console (routing through OpenConsole.exe
  -Embedding on Win11) and shows it BEFORE PowerShell applies -WindowStyle Hidden ~200ms
  later -> a visible black flash on every fire. Caught live: Gamma_CryptoGrinderKeepalive
  (every 5 min!) spawned `OpenConsole.exe -Embedding` at the same instant it launched.

  run_ps1_hidden.py spawns powershell via subprocess with CREATE_NO_WINDOW, so NO console
  is ever allocated (no OpenConsole, no flash). wscript + pythonw are GUI-subsystem. This
  is the same chain Gamma_Heartbeat/EOD use -- which do NOT flash.

  This is also why audit_scheduled_tasks.py's convention #1 ("powershell.exe -WindowStyle
  Hidden is acceptable") was WRONG and is being tightened in the same change.
#>
$ErrorActionPreference = "Stop"
$WorkDir = "C:\Users\jackw\Desktop\42"
$vbs     = Join-Path $WorkDir "setup\scripts\run_exe_hidden.vbs"
$runner  = Join-Path $WorkDir "setup\scripts\run_ps1_hidden.py"
$pythonw = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"

foreach($p in @($vbs,$runner,$pythonw)){ if(-not (Test-Path $p)){ Write-Error "missing: $p"; exit 1 } }

# Every Gamma task whose action is a bare powershell.exe (flashes OpenConsole on Win11).
$targets = @(
  'Gamma_ContextGuard','Gamma_CryptoDaily','Gamma_CryptoGrinderKeepalive',
  'Gamma_CryptoRegression','Gamma_FuturesEod','Gamma_FuturesHeartbeat','Gamma_FuturesPremarket'
)

foreach($name in $targets){
  $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if(-not $t){ Write-Host "SKIP   $name (not registered)"; continue }
  $act = $t.Actions[0]
  if("$($act.Execute)" -notmatch 'powershell'){ Write-Host "SKIP   $name (already '$($act.Execute)')"; continue }
  $a = "$($act.Arguments)"
  if($a -match '-File\s+"([^"]+)"(.*)$'){ $ps1 = $matches[1].Trim(); $extra = $matches[2].Trim() }
  elseif($a -match '-File\s+(\S+)(.*)$'){ $ps1 = $matches[1].Trim(); $extra = $matches[2].Trim() }
  else { Write-Host "SKIP   $name (no -File in args: $a)"; continue }

  $arg = "//nologo `"$vbs`" `"$pythonw`" `"$runner`" `"$ps1`""
  if($extra){ $arg += " `"$extra`"" }   # e.g. ContextGuard's -AutoFix (single token)

  $newAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $arg
  Set-ScheduledTask -TaskName $name -Action $newAction | Out-Null   # preserves triggers/settings/principal
  Write-Host "CONVERT $name  ->  wscript hidden chain   (ps1=$([IO.Path]::GetFileName($ps1)) extra='$extra')"
}
Write-Host ""
Write-Host "Done. Verify: python setup\scripts\audit_scheduled_tasks.py   (after the audit tightening, bare powershell = VISIBLE_WINDOW)"
