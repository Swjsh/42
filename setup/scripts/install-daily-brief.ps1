#requires -Version 5.1
<#
.SYNOPSIS
  Register Gamma_MorningBrief + Gamma_EodBrief -- the GAMMA DAILY PRESENCE loop (J directive
  2026-07-22, verbatim frustration: "I need to figure out how to turn gamma into a real
  person... I can't prompt it over and over... obviously gamma's not doing anything").

  ROOT CAUSE fixed: Gamma runs 10-20 autonomous fires/day (conductor/kitchen/analyst/autopsy)
  but had ZERO PROACTIVE touchpoints -- J only ever met Gamma when HE prompted it. These two
  tasks are the first self-initiated daily contact: a short, first-person, honest voice brief
  assembled DETERMINISTICALLY ($0, no LLM) from state files that already exist, spoken via the
  existing Kokoro TTS pipeline (setup/tts/, gamma_speak.py's --text-file mode) and delivered as
  a Discord AUDIO FILE attachment through the discord-bridge outbox (drain_outbox extended with
  an optional `file` field -- see discord-bridge.py).

  Gamma_MorningBrief  08:45 ET weekdays -- bias/hypothesis, both kill-switches armed?, nearest
                       key levels, what the overnight conductor shipped.
  Gamma_EodBrief       16:20 ET weekdays -- scheduled AFTER Gamma_TradeAutopsy (16:15 ET) so its
                       output is citable. Per-account realized P&L, fills + setups traded, an
                       honest wins/losses one-liner, tonight's backlog, film-room availability.

  WIRING PATTERN (flash-free, matches install-futures-edge3-sim.ps1 exactly):
    wscript -> run_exe_hidden.vbs -> backtest\.venv\Scripts\pythonw.exe -> daily_brief.py --mode X
  Runs on the BACKTEST venv -- automatically reaper-exempt (backtest\.venv is already in
  _shared.ps1's EXEMPT_DAEMONS substring list).

  TZ RULE: this rig is Mountain Time (ET = local + 2h, year-round -- both zones share the same
  DST calendar). 08:45 ET -> 06:45 MT. 16:20 ET -> 14:20 MT. NEVER pass an ET literal to -At.
  WEEKLY trigger (Mon-Fri), NOT -Once (a one-shot TimeTrigger fires once ever then goes dark --
  project_scheduled_task_onetime_trigger_dark). A single fire per day, no repetition needed.

  To verify after running:
    Get-ScheduledTask -TaskName Gamma_MorningBrief | Get-ScheduledTaskInfo
    Get-ScheduledTask -TaskName Gamma_EodBrief | Get-ScheduledTaskInfo
  REVERT:
    Unregister-ScheduledTask -TaskName "Gamma_MorningBrief" -Confirm:$false
    Unregister-ScheduledTask -TaskName "Gamma_EodBrief" -Confirm:$false
#>

$ErrorActionPreference = "Stop"

$root        = "C:\Users\jackw\Desktop\42"
$vbs         = Join-Path $root "setup\scripts\run_exe_hidden.vbs"
$pythonwVenv = Join-Path $root "backtest\.venv\Scripts\pythonw.exe"
$script      = Join-Path $root "setup\scripts\daily_brief.py"
$etz         = [System.TimeZoneInfo]::FindSystemTimeZoneById('Eastern Standard Time')

foreach ($p in @($vbs, $pythonwVenv, $script)) {
    if (-not (Test-Path $p)) { Write-Error "Required file missing: $p"; exit 1 }
}

function Show-NextET {
    param([string]$Name)
    $info = Get-ScheduledTaskInfo -TaskName $Name -ErrorAction SilentlyContinue
    if ($info -and $info.NextRunTime) {
        $et = [System.TimeZoneInfo]::ConvertTime($info.NextRunTime, $etz)
        Write-Host ("  NextRun ET: {0}" -f $et.ToString("yyyy-MM-dd HH:mm"))
    } else {
        Write-Host "  NextRun ET: (none / on-demand)"
    }
}

function Install-BriefTask {
    param(
        [string]$TaskName,
        [string]$Mode,
        [string]$AtMT,          # Mountain-time HH:mm for -At
        [string]$Description
    )
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }

    # wscript -> run_exe_hidden.vbs -> backtest venv pythonw -> daily_brief.py --mode <Mode>
    $wscriptArgs = "//nologo `"$vbs`" `"$pythonwVenv`" `"$script`" --mode $Mode"

    $action = New-ScheduledTaskAction `
        -Execute "wscript.exe" `
        -Argument $wscriptArgs `
        -WorkingDirectory $root

    $trigger = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $AtMT

    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 6) `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description $Description `
        -Force | Out-Null

    Write-Host "Registered $TaskName ($AtMT MT, Mon-Fri)"
    Show-NextET $TaskName
}

Install-BriefTask -TaskName "Gamma_MorningBrief" -Mode "morning" -AtMT "06:45" `
    -Description ("GAMMA DAILY PRESENCE (J directive 2026-07-22): 08:45 ET weekdays " + `
    "(06:45 MT). daily_brief.py --mode morning assembles a <=140-word first-person script " + `
    "from today-bias.json + both circuit-breaker.json files + key-levels.json + STATUS.md's " + `
    "newest overnight headers -- pure state-file assembly, `$0, no LLM, no broker calls. " + `
    "Voices it via the existing Kokoro TTS pipeline (setup/.tts-venv, gamma_speak.py " + `
    "--text-file) and delivers it as a Discord audio-file attachment through the " + `
    "discord-bridge outbox (file field). Fails open to a text-only Discord brief if TTS or " + `
    "the bridge is unavailable -- never silent. Places NOTHING, touches NO trading-path file.")

Install-BriefTask -TaskName "Gamma_EodBrief" -Mode "eod" -AtMT "14:20" `
    -Description ("GAMMA DAILY PRESENCE (J directive 2026-07-22): 16:20 ET weekdays " + `
    "(14:20 MT) -- scheduled AFTER Gamma_TradeAutopsy (16:15 ET) so its output is citable. " + `
    "daily_brief.py --mode eod assembles a <=140-word first-person script from " + `
    "pnl-statement.json (via fill_funnel.trades_pnl_today, T1 broker-truth), trade-today.json, " + `
    "today's decisions.jsonl setups, queue.md's active backlog, and today's dojo film-room " + `
    "brief if one exists -- pure state-file assembly, `$0, no LLM, no broker calls. Same " + `
    "TTS + Discord audio-file delivery path as Gamma_MorningBrief. Honest wins/losses one- " + `
    "liner, no sugar-coating a losing day. Fails open to text-only on any TTS/bridge miss.")

Write-Host ""
Write-Host "GAMMA DAILY PRESENCE loop wired. Verify with:"
Write-Host "  Get-ScheduledTask -TaskName Gamma_MorningBrief | Get-ScheduledTaskInfo"
Write-Host "  Get-ScheduledTask -TaskName Gamma_EodBrief | Get-ScheduledTaskInfo"
