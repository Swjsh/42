---
filed: 2026-07-30
filed_by: conductor (AFTERHOURS fire, ~19:12-19:35 ET)
kind: lesson
status: pending
---

# A 5-min scheduled task can go silently dark for hours with zero Task Scheduler signal — a proven "kill+relaunch" watchdog pattern only covered ONE instance of the failure class

## Symptom

`engine-health.json` RED 2026-07-30: `levels_blind` — 0 of 770 RTH decision rows carried
ANY active key level all day. The engine fell through to its statistically worst cohort
(trendline-only, -$1,830/WR .19 vs +$6,895/66 for level-tied trades).

## Root cause

`Gamma_LevelRefresh`'s own Task Scheduler config (`PT5M` repetition, `MultipleInstances=
IgnoreNew`, `PT3M` `ExecutionTimeLimit`) went dark for ~20 hours — last good run
2026-07-29 22:43 ET, nothing until a manual repair at 18:57 ET on 2026-07-30 — with
**zero errors logged** in either day's `level-refresh-*.log` and **zero Task Scheduler
recovery of its own**. All other scheduled tasks (`Gamma_TvWatchdog`) kept firing fine in
the same window, ruling out a machine-wide sleep/reboot — this was specific to the one
task. `IgnoreNew` + a multi-hop hidden-launch wrapper chain (wscript.exe -> pythonw.exe ->
run_ps1_hidden.py -> powershell.exe -> python.exe) is the suspected mechanism: if
Task Scheduler's own job-object tracking only reliably reaches the direct child it
launched, `ExecutionTimeLimit` can silently fail to reach a hang several process
generations deep, and `IgnoreNew` then blocks every subsequent 5-min trigger indefinitely
because Task Scheduler still believes an instance is "running."

**The alerting itself was NOT broken** — `self_check.py` and `engine_health.py`'s
fail-loud beacon correctly paged J via Discord starting at 09:42 ET (the very first RTH
tick) with a DEGRADED `level_feed` alert, then repeated RED `levels_blind` alerts through
the evening. The gap was purely on the REMEDIATION side: nothing existed to force-kill and
relaunch a stuck instance, the way `Invoke-TvLaunchSafe` already does for the exact
analogous TV/CDP-hang failure mode.

## Generalizable rule

**A 5-min-cadence scheduled task with `MultipleInstances=IgnoreNew` + a multi-hop hidden
launch wrapper is a latent silent-stall risk, not just the one that already had a
watchdog.** Detecting staleness (a check that reads a file's mtime and turns RED) is
necessary but not sufficient — without a paired self-heal (kill the stuck process tree by
command-line match, then relaunch directly, serialized via a lock file), staleness alerts
only page a human; they never fix themselves. `Invoke-TvLaunchSafe` proved the pattern
once (2026-07-06) for TV/CDP; this incident is the second instance of the identical shape
(`Invoke-LevelRefreshSafe`, 2026-07-30, `_shared.ps1`). **Audit every other 5-min-or-tighter
scheduled task with `IgnoreNew` for the same latent gap** (candidates: `Gamma_LevelMemory`,
`Gamma_KeyLevelsSnapshot`, and any other frequent producer feeding a live-path state
file) — the fix cost is small (one shared helper + one wiring block into an existing
watchdog cadence) relative to a full trading day traded blind.

## Suggested L# slot

Fold into CLAUDE.md's C8 (Headless Windows spawn) or C9/new theme — cross-references C11
(broker is source of truth / verify flat) and C7 (silent success is failure — audit
outputs, not exit codes) since the underlying producer failed with a CLEAN exit and no
error, and only an independent consumer-side ratio check (`levels_blind_check.py`,
2026-07-30 earlier commit) caught it at all.
