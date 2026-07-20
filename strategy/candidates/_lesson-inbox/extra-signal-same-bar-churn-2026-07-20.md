# Lesson candidate: extra-setup lane had no re-entry memory after a stop-out

> Queued by conductor (AFTERHOURS) 2026-07-20 ~17:15 ET. lesson-author picks up at next wake fire.

## Symptom

2026-07-20 09:51-09:55 ET, safe account, extra_exec lane `vix_regime_dayside`: THREE 3-lot
748C entries in 5 minutes (fills 1.13/0.79/0.76), each stopped out in 40-60s (0.98/0.73/0.68),
net -$87. Two of the five heartbeat ticks in that window were blocked only by the
nondeterministic free-model veto (HTF-conflict reasoning) -- not a real gate.

## Root cause

`heartbeat_core._route_extra_setups` (`setup/scripts/heartbeat_core.py`) had a `placed_this_tick`
guard preventing two placements on the SAME heartbeat tick, and the underlying watchers have
"current-bar guards" preventing a DUPLICATE signal from firing twice within one 5m bar -- but
nothing tracked "did this setup already attempt (and fail) an entry on this trigger bar." Once
a stop-out returned the account to flat mid-bar, the SAME setup's signal (still valid for the
still-current 5m bar) could re-fire on the very next tick and place again, repeatedly, until
the bar finally rolled over or the nondeterministic veto happened to block it. The watcher-level
"current-bar" protection and the entry-path's "flat account" check compose to ALLOW exactly
this churn -- neither one individually was wrong, but together they left no memory of a failed
attempt.

## Fix

Added a per-arm, per-setup "last trigger-bar attempted" ledger:
`exit_actuator.load_last_entry_bars` / `record_entry_bar` / `same_bar_cooldown_active`
(`automation/state/fleet/exit_actuator.py`, additive, new functions only) + wired into
`_route_extra_setups`: refuse a new entry attempt for a setup on the SAME trigger bar it
already attempted one on this session (`SKIP_COOLDOWN_SAME_BAR`); record only on an actual
PLACED/PLACING/WOULD_PLACE outcome. Chose bar-boundary ("requires-new-trigger-bar") over a
hand-picked N-minute cooldown deliberately -- this is a brand-new mechanism with no existing
trade population to pre-register a duration against, so the bar boundary is the smallest
non-arbitrary unit available (no magic number to defend). Guard:
`backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py` (10/10). Fail-open throughout.

## Encoded in

`backtest/tests/test_extra_signal_churn_cooldown_2026_07_20.py` (guard, RED-proofed via
git-stash) + the fix itself (structural, not a doc). Scoped to the extra-setup lane only --
**the PRIMARY ribbon path (`ENTER_BEAR`/`ENTER_BULL` -> `_execute`) has NO equivalent same-bar
re-entry guard.** It is currently protected only by the one-position-at-a-time flat-check +
its own gate discipline (structure_veto, HTF gates, etc.), which is a materially different (and
so far untested-for-this-exact-churn-shape) safety net. If a future incident shows the primary
path re-entering the same trigger bar after a stop-out, this is the FIRST place to look --
the fix pattern (per-setup/per-account last-attempted-bar ledger) generalizes directly.

## L## (optional)

Not suggested -- let lesson-author grep for max and assign next (index currently through L201
per CLAUDE.md OP-25).
