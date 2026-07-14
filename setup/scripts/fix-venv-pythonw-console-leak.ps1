#requires -Version 5.1
<#
.SYNOPSIS
  Rewrap every scheduled task that directly launches backtest\.venv\Scripts\pythonw.exe
  via run_exe_hidden.vbs (wscript -> run_exe_hidden.vbs -> VENV-pythonw -> target.py) onto
  the two-hop relay: wscript -> run_exe_hidden.vbs -> SYSTEM-pythonw -> run_cmd_hidden.py
  --cwd <repo> -- VENV-pythonw target.py [args].

.CONTEXT (2026-07-14, J: "stop the fkin popus on my screen")
  Live-fire investigation (window-leak-detector.py re-armed this session) proved, via
  repeated clean Start-ScheduledTask reproductions in isolated quiet windows:
    - a MINIMAL stdlib-only script launched directly under backtest-venv-pythonw does NOT
      leak (noop_test.py, clean, twice)
    - a script that does `import pandas` (pulling in numpy) DOES leak a WindowsTerminal
      -Embedding console-host window, on EVERY tested launcher mechanism: Shell.Run
      (run_exe_hidden.vbs), WshShell.Exec (run_exe_hidden_exec.vbs), AND Python
      subprocess.Popen(creationflags=CREATE_NO_WINDOW) from inside a relay -- all three
      independently reproduced leaking, ruling out "wrong launcher API" as the cause
    - Python-level sys.stdout/stderr redirection, OS-level os.dup2 fd redirection, AND
      warnings.filterwarnings("ignore") were all tested live and NONE prevented it --
      ruling out "stdio write" as the trigger mechanism
  Root cause of the WINDOW ITSELF remains formally unresolved (something inside numpy/
  pandas' Windows import path touches console state below the level any of the above can
  intercept -- most likely a native AllocConsole()-class call, not a stdio write). This
  script does NOT claim to fix that. What it DOES fix: (1) real exit-code visibility --
  the old direct-venv-pythonw wiring went through Shell.Run which Task Scheduler always
  reports as LastTaskResult=0 regardless of the real child's outcome (same masking lesson
  as Gamma_EodFlattenCore); the relay's run_cmd_hidden.py captures and can surface the true
  exit code. (2) consistency with the codebase's one other already-correct precedent for
  this exact shape (the disabled Funnel_0-5/Grind_all tasks already used run_cmd_hidden.py).
  The ACTUAL popup suppression is a separate, already-deployed fix: window-leak-detector.py
  now auto-hides (ShowWindow SW_HIDE, never kill -- zero risk to the real work) any
  service-rooted WindowsTerminal/console-host window within its 0.5s poll cycle. Verified
  live end-to-end on Gamma_Confluence before this rollout: real output (confluence-
  zones.json) still produced correctly, exit=0 in run-cmd-hidden log, AND the leak entry
  logged `"mitigated": true`.

  Gamma_Confluence itself was already fixed + verified before this script existed -- it is
  included here too so a re-run of this script is idempotent/safe over the full set.

.USAGE
  Idempotent -- safe to re-run. Preserves each task's existing Trigger/Settings/Principal
  (Set-ScheduledTask action-only swap, same technique as fix-window-leak-task-actions.ps1).
#>
[CmdletBinding()] param()
$ErrorActionPreference = "Stop"

$root         = "C:\Users\jackw\Desktop\42"
$vbs          = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$sysPythonw   = "C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe"
$runCmdHidden = Join-Path $root "setup\scripts\run_cmd_hidden.py"
$venvPythonw  = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"

if (-not (Test-Path $vbs))          { throw "run_exe_hidden.vbs not found at $vbs" }
if (-not (Test-Path $sysPythonw))   { throw "system pythonw.exe not found at $sysPythonw" }
if (-not (Test-Path $runCmdHidden)) { throw "run_cmd_hidden.py not found at $runCmdHidden" }
if (-not (Test-Path $venvPythonw))  { throw "backtest venv pythonw.exe not found at $venvPythonw" }

# {TaskName -> @{ Target = <relative .py path>; Args = @(extra positional args) }}
$targets = [ordered]@{
    "Gamma_BrokerFills"    = @{ Target = "setup\scripts\broker_fills.py";               Args = @() }
    "Gamma_CboeOiBank"     = @{ Target = "backtest\tools\cboe_oi_bank.py";              Args = @() }
    "Gamma_Confluence"     = @{ Target = "setup\scripts\confluence_producer.py";        Args = @() }
    "Gamma_CryptoTwin"     = @{ Target = "setup\scripts\crypto_twin_health.py";         Args = @("--live") }
    "Gamma_DressRehearsal" = @{ Target = "setup\scripts\dress_rehearsal.py";            Args = @() }
    "Gamma_EmaSnapshot"    = @{ Target = "automation\scripts\compute_ema_snapshot.py";  Args = @() }
    "Gamma_FirmBrief"      = @{ Target = "setup\scripts\firm_brief.py";                 Args = @() }
    "Gamma_FreeModelAudit" = @{ Target = "setup\scripts\free_model_audit.py";           Args = @("--subject", "all") }
    "Gamma_FuturesMirror"  = @{ Target = "setup\scripts\futures_mirror_shadow.py";      Args = @("--once") }
    "Gamma_GuardsNightly"  = @{ Target = "setup\guard_runner_slow.py";                  Args = @() }
    "Gamma_LevelMemory"    = @{ Target = "setup\scripts\level_memory_producer.py";      Args = @() }
    "Gamma_OosCheck"       = @{ Target = "setup\scripts\oos_check_runner.py";           Args = @() }
    "Gamma_Prospector"     = @{ Target = "setup\scripts\prospector.py";                 Args = @() }
    "Gamma_SelfAudit"      = @{ Target = "setup\scripts\self_audit.py";                 Args = @() }
    "Gamma_TradeAutopsy"   = @{ Target = "setup\scripts\trade_autopsy.py";              Args = @() }
    "Gamma_TradeToday"     = @{ Target = "setup\scripts\trade_today_watcher.py";        Args = @() }
    "Gamma_Trendlines"     = @{ Target = "backtest\autoresearch\trendline_engine.py";   Args = @() }
    "Gamma_TwinSentinel"   = @{ Target = "setup\scripts\twin_sentinel.py";              Args = @() }
}

$results = @()

foreach ($name in $targets.Keys) {
    $cfg = $targets[$name]
    $targetPath = Join-Path $root $cfg.Target
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) {
        Write-Warning "$name -- NOT REGISTERED, skipping"
        $results += [PSCustomObject]@{ Task = $name; Status = "NOT_REGISTERED" }
        continue
    }
    if (-not (Test-Path $targetPath)) {
        Write-Warning "$name -- target script missing at $targetPath, skipping"
        $results += [PSCustomObject]@{ Task = $name; Status = "TARGET_MISSING" }
        continue
    }

    $oldAction = $task.Actions[0]
    $before = "EXEC='$($oldAction.Execute)' ARGS='$($oldAction.Arguments)'"

    $alreadyFixed = ($oldAction.Execute -eq "wscript.exe") -and
                    ($oldAction.Arguments -match [regex]::Escape("run_cmd_hidden.py")) -and
                    ($oldAction.Arguments -match [regex]::Escape($cfg.Target))
    if ($alreadyFixed) {
        Write-Host "$name -- already on the relay chain, no change needed"
        $results += [PSCustomObject]@{ Task = $name; Status = "ALREADY_FIXED"; Before = $before; After = $before }
        continue
    }

    $cmdParts = @("`"$venvPythonw`"", "`"$targetPath`"") + ($cfg.Args | ForEach-Object { "`"$_`"" })
    $cmdTail = $cmdParts -join " "
    $newArgs = "//nologo `"$vbs`" `"$sysPythonw`" `"$runCmdHidden`" --cwd `"$root`" -- $cmdTail"
    $newAction = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $newArgs -WorkingDirectory $root

    Set-ScheduledTask -TaskName $name -Action $newAction | Out-Null

    $verify = Get-ScheduledTask -TaskName $name
    $after = "EXEC='$($verify.Actions[0].Execute)' ARGS='$($verify.Actions[0].Arguments)'"

    Write-Host "$name -- FIXED"
    Write-Host "  BEFORE: $before"
    Write-Host "  AFTER:  $after"
    $results += [PSCustomObject]@{ Task = $name; Status = "FIXED"; Before = $before; After = $after }
}

Write-Host ""
Write-Host "=== SUMMARY ==="
$results | Format-Table -AutoSize -Wrap | Out-String -Width 300 | Write-Host

$outPath = Join-Path $root "automation\state\venv-pythonw-console-leak-fix-log.json"
$results | ConvertTo-Json -Depth 5 | Set-Content -Path $outPath -Encoding utf8
Write-Host "Log written: $outPath"
