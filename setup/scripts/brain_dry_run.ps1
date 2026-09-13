# brain_dry_run.ps1 -- prove the per-fire local brain path end to end through the SAME helper every
# automation launcher uses (Invoke-Claude in _shared.ps1), with automation/state/brain-mode.json honoured.
# Prints: resolved model, exit code, wall time, the answer line from the task log. $0, no orders, no state writes
# beyond the task log and the prompt file. Usage: powershell -File setup/scripts/brain_dry_run.ps1
param([string]$Tier = "sonnet", [int]$TimeoutSec = 300)
. "$PSScriptRoot\_shared.ps1"
. "$PSScriptRoot\_brain.ps1"
$pf = Join-Path $Global:WorkDir 'automation\state\station\brain-test-prompt.md'
Set-Content -Path $pf -Encoding utf8 -Value "Answer in ONE line, no preamble: per CLAUDE.md, what are the Rule 5 daily-loss kill-switch percentages for Gamma-Safe and Gamma-Bold, and the hard time-stop (ET)?"
$model = Resolve-BrainModel -Tier $Tier -TaskName 'Gamma_BrainTest'
"resolved: tier=$Tier -> model=$model | base=$env:ANTHROPIC_BASE_URL | cfg=$env:CLAUDE_CONFIG_DIR"
$sw = [Diagnostics.Stopwatch]::StartNew()
$rc = Invoke-Claude -PromptFile $pf -TaskName 'Gamma_BrainTest' -MaxBudgetUsd 1 -Model $model -TimeoutSec $TimeoutSec -Effort 'low'
$sw.Stop()
"Invoke-Claude rc=$rc in $([math]::Round($sw.Elapsed.TotalSeconds))s"
$log = Join-Path $Global:LogDir ("Gamma_BrainTest-" + (Get-EtNow).ToString('yyyy-MM-dd') + ".log")
"--- log tail"
Get-Content $log -Tail 12 | ForEach-Object { $_.Substring(0, [Math]::Min(240, $_.Length)) }
