# Monitoring instrument scored an every-N-day task as a 1-day task (GITHUB-AUDIT-FALSE-RED)

**Found:** 2026-08-28, AFTERHOURS conductor fire, via `desk_allocator.py` flagging SPY-0DTE
desk #1 on `self-check-last.json=DEGRADED` -> traced to `unattended_health.py` reporting
`github-audit` unit **RED**: `"Gamma_GitHubAudit: HAS NOT FIRED in 2.2d -- daily trigger,
budget 2.0d"`.

**Root cause:** `Gamma_GitHubAudit` is registered with a Windows `DailyTrigger` whose
`DaysInterval=2` (fires every 2 days, not every 1). Two independent layers silently
dropped that fact:

1. `_list-gamma-tasks-json.ps1` (the PowerShell task enumerator) never read/emitted the
   trigger's `DaysInterval` property at all.
2. `unattended_health.py::expected_gap_minutes()` therefore had no way to see it, and its
   `elif "Daily" in ttype:` branch scored **every** `DailyTrigger` at a flat 1440min (1-day)
   cadence regardless of the task's real interval.

The module's own stated design intent (`_MULT_DAILY_PLUS = 2.0`, comment: "daily/weekly
ones get 2, which tolerates EXACTLY ONE missed run") was silently violated for any
every-N-day (N>=2) task: budget = wrongly-assumed-1-day-cadence * 2 = 2 days flat, which
gives **zero** slack for a single missed run once the task's real interval is >=2 days.
`Gamma_GitHubAudit` missed its 2026-08-27 evening run (the same evening-reboot-window
class already root-caused for `Gamma_DressRehearsal` on 2026-08-26 -- Kernel-Power reboots
land in the 18:00-22:00 MT slot most nights) and the mis-scored budget turned one missed
run into an immediate RED, when the module's own design says one missed run should still
be tolerated.

**Fix (2026-08-28):** `_list-gamma-tasks-json.ps1` now emits `days_interval` for
`DailyTrigger` entries; `expected_gap_minutes()` multiplies the daily cadence by that
value (`n > 1 -> cadence = 1440 * n`), defaulting to `n=1` (unchanged behavior) when the
field is absent. Guard tests: `backtest/tests/test_unattended_health.py` --
`test_every_n_day_trigger_scored_at_its_real_cadence`,
`test_missing_days_interval_defaults_to_plain_daily`,
`test_every_n_day_budget_tolerates_one_missed_run`. Live re-run confirmed `github-audit`
unit dropped RED -> GREEN with the corrected cadence (overall `unattended-health.json`
verdict RED -> YELLOW, no other unit changed).

**Generalizable:** any monitoring/health-check instrument that classifies a Windows
scheduled task purely by `CimClassName` (Daily/Weekly/Monthly) without also reading the
trigger's own interval-refining property (`DaysInterval` for Daily, and note
`WeeklyTrigger` has an analogous `WeeksInterval` that is ALSO not currently captured --
not audited this fire, same blind spot could exist there if any Gamma task ever uses a
multi-week interval; none currently do, verified via the same live sweep this fire ran)
will silently mis-budget any task whose author reaches for the "every N" checkbox instead
of N separate triggers. The fix pattern is: capture the interval-refining field at the
enumeration boundary, never assume the CimClass name alone describes the cadence.

**Not chased this fire (out of bounded scope):** `WeeksInterval` on `MSFT_TaskWeeklyTrigger`
is not currently read either, but zero live Gamma tasks currently set it >1 (verified via
`Get-ScheduledTask -TaskName 'Gamma_*' | ... WeeksInterval -gt 1` returning empty), so it is
a latent-but-currently-inert instance of the same class -- worth a follow-up if a future
task ever wants a "every 2 weeks" cadence.
