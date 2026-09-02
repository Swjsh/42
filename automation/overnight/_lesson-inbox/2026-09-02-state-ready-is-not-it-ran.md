# `State=Ready` + `LastTaskResult=0` is not "it ran" — the safety suite was dark for two days and every surface said green

**Date:** 2026-09-02 (Opus session, executing `markdown/planning/OPUS-WORK-ORDER-2026-09.md`)
**Theme:** C7 (silent success is failure) / C15 (gates interact multiplicatively)

## Symptom

`Gamma_GuardsFull` — the ~11,400-test regression suite, the rig's main safety net — produced
no verdict between 2026-08-31 and 2026-09-02. Nothing reported it. Every health surface in
the repo showed it healthy the entire time:

```
State              : Ready          <- task_state_guard.py checks exactly this
LastTaskResult     : 0              <- ...and this
LastRunTime        : 8/31 07:31     <- nothing read this
NumberOfMissedRuns : 2              <- nothing read this either
```

`task_state_guard.py` was built for a real scar (a silently-Disabled task is never
recovered) and it does its job. But **neither field it reads moves when a task simply never
starts.** `Ready` means "eligible to run", not "ran". `LastTaskResult=0` is the exit code of
the *last* run, however long ago. A task can go dark forever without either changing.

## Root cause of the darkness

Quiet mode (`setup/scripts/quiet_mode.py`) disables ~120 `Gamma_*` tasks for J's evening and
**holds the blackout past its own 23:00 ET clock** whenever a fullscreen app is foreground
(plus a 15-minute linger). A task whose trigger fires inside a hold is skipped — and because
the task was *Disabled* rather than merely unavailable, Windows' `StartWhenAvailable` cannot
recover the fire. Nothing re-runs it. The nightly maintenance band, 23:00–01:00 ET, is
exactly where the guard/audit instruments live.

The differential settles it. On 2026-09-01 the holds ran 23:02–23:22 and 00:07–00:42 ET;
every task inside a hold missed, every task outside it ran:

| ET | task | outcome |
|---|---|---|
| 23:05 | `Gamma_FuturesBrokerProbe` | MISSED |
| 23:15 | `Gamma_GuardsFull` | MISSED |
| 23:30 | `Gamma_SpendSummary` | RAN |
| 23:40 | `Gamma_OosCheck` | RAN |
| 23:58 | `Gamma_LicenseMonitor` | RAN |
| 00:30 | `Gamma_GuardsNightly` | MISSED |
| 01:00 | `Gamma_GateExpiryCheck` | RAN |

Seven tasks, seven correct predictions from one rule, no counter-examples.

## The two lessons

**1. A liveness check must read a field that MOVES when the thing happens.** `State` and
`LastTaskResult` are *configuration and history*; `LastRunTime` and `NumberOfMissedRuns` are
*evidence of execution*. This is the same shape as the two August futures outages, where
`futures_eod` graded GREEN through 15 dead sessions because it measured trades rather than
ticks — and it is why that digest's headline metric is now TICK COVERAGE. When you build a
health check, ask: **what value would look different if this had not run at all?** If the
answer is "nothing", the check cannot detect the outage it exists for.

**2. A monitor its own subject can switch off is not a monitor.** Quiet mode disables tasks;
the instrument that reports what quiet mode disabled must be in quiet mode's `ESSENTIAL`
set, or the first thing the blackout silences is the alarm about the blackout. Same family
as the `prereg_hygiene` orphan-proxy bug found the night before, where *filing* the
adjudication named all six stale preregs and drove the flagged count 6 → 0 with nothing
resolved — documenting a problem made the instrument stop reporting it.

## Guard shipped

`setup/scripts/scheduled_task_staleness.py` (`Gamma_TaskStaleness`, daily 05:45 ET) reads
`LastRunTime` + `NumberOfMissedRuns` for every `Gamma_*` task, derives a staleness bar from
each task's own trigger cadence, and **names the quiet-hold cause** when the evidence
supports it — an alarm that explains itself gets acted on. Report only; never enables,
disables, starts or kills anything (pinned by a source-level test). Guard:
`backtest/tests/test_scheduled_task_staleness_2026_09_02.py` (53).

## Coda: my own first cut reported 37 RED

Only 8 were real. Two false-positive classes, both found by *reading the output* rather than
trusting the number:

1. **Bounded repeaters.** `Gamma_RosterLiveness` repeats every 20 minutes *for 40 minutes*,
   then is idle by design for 23 hours. Judged against a 4-interval bar it was RED almost
   all day. A monitor that cries wolf daily gets muted — which is how the real outages
   survived in the first place.
2. **Windows' never-ran sentinel.** `LastRunTime` reads `1999-11-30` for a task that has
   never run. Taken literally that is a 26-year staleness, and the script duly reported
   `last ran 234553.6h ago` for two tasks registered the previous day: a precise, confident,
   wrong number. Never-ran and long-dark are different findings and must render differently.

Both are the same mistake in different clothes: **applying a bar to a population it was not
derived for.** And note the asymmetry that makes the check worth running — the first draft's
output was plausible enough to ship and wrong enough to make the instrument useless.

## Open item, deliberately not built tonight

The *cause* is unfixed: quiet mode still eats those runs and never settles the debt. A
catch-up sweep on `QUIET OFF` is the obvious fix, but it needs a design decision this
session refused to guess at — **which tasks may be auto-restarted hours late?** A report-only
producer, yes. `Gamma_KalshiAuto` places orders off a next-day weather prediction; restarting
it at 04:00 ET on stale NOAA data is a different act from re-running an audit. And a HEAVY
task restarted into the next presence hold gets killed 45 minutes in by
`_stop_heavy_processes()`, burning CPU for nothing. Filed with those constraints rather than
shipped on a guess.
