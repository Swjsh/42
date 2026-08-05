# LESSON CANDIDATE: a self-heal watchdog can silently FAIL to heal and look identical to one that worked

**Date:** 2026-07-31 (conductor AFTERHOURS fire, ~09:12-09:35 ET)

**Symptom:** `self_check.py` reported `TV-CDP UNREACHABLE (RED)` ~18 minutes before
market open. Live-verified: `Gamma_TvWatchdog` (5-min cadence) had already logged
`RELAUNCH_KILL` at BOTH 09:05 ET (`CDP dead for 3896s`) and 09:10 ET (`CDP dead for
4196s` -- the counter grew by exactly the 300s between checks, i.e. CDP was still down
going into the second check). Both lines landed in `STATUS.md` looking like routine,
successful self-heal activity. Nothing distinguished "the relaunch script ran" from
"CDP is actually back" -- `self_check.py`, a completely independent producer, was the
only thing that eventually surfaced the outage as RED.

**Root cause:** `Invoke-TvLaunchSafe` (`setup/scripts/_shared.ps1`) invoked
`launch_tv_debug.ps1` and returned only `{skipped: bool}` -- true if the 30s lock
was held, false if the launch script was invoked. It never checked whether the launch
actually restored CDP. `run-tv-watchdog.ps1`'s three call sites (`relaunch_kill`,
`relaunch_fresh`, `relaunch_hung_bridge`) treated "we invoked the launch script" as
success and logged the same `tvAction` string every cycle regardless of outcome.

**Why it matters (C7 class):** a self-heal mechanism that can silently no-op while
LOOKING like it's actively healing is worse than no self-heal at all -- it manufactures
false confidence in STATUS.md ("TvWatchdog: tv=relaunch_kill ... kill+relaunch" reads
as remediation, not as an ongoing outage) and delays the moment a human/session
actually investigates. This incident's outage duration (>70min across at least 2
relaunch cycles) was bounded only by luck (a manual conductor fire happening to run
right then) -- on a quieter night it could have run through market open.

**Fix shipped (commit `c941567c`):** `Test-CdpReady` (poll helper, `_shared.ps1`) +
`Invoke-TvLaunchSafe` now returns `{skipped, healed}` by self-verifying CDP post-launch.
`run-tv-watchdog.ps1` branches into `*_healed` / `*_FAILED` tvActions; a `*_FAILED`
outcome writes a distinct, append-only `### BROKEN:` block to STATUS.md instead of
blending into the routine relaunch line. Guard: `test_tv_launch_safe_2026_07_06.py`
(`test_shared_defines_test_cdp_ready`, `test_no_lock_allows_launch_and_cleans_up`'s new
`HEALED=False` assertion, `test_watchdog_escalates_on_failed_selfheal`).

**Open question (not fully root-caused, logged not chased further):** why the relaunch
attempt at 09:05/09:10 ET failed to restore CDP in production while two manual
reproductions of the identical code path (same LogonType=Interactive task principal)
both succeeded minutes later. Ruled out: AppX package query flakiness under
`-WindowStyle Hidden -NonInteractive` (5/5 manual reps succeeded), window-station
mismatch (task principal confirmed `LogonType=Interactive`, same session as manual
tests). Left open rather than over-invested per debugging discipline -- the shipped fix
makes a RECURRENCE of this exact failure mode loud and immediate regardless of the
underlying mechanism, which is the higher-leverage fix.

**Generalizable pattern:** any self-heal/watchdog function that "does the repair
action" MUST verify the repair's effect before reporting success, not just that the
repair action was invoked without an exception. Worth auditing `Invoke-LevelRefreshSafe`
and `state_freshness_selfheal.py` for the same class of gap (do they confirm the
producer file's mtime actually advanced / the process actually became healthy, or just
that `Start-ScheduledTask`/the relaunch command returned without throwing?).
