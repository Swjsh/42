# Lesson candidate: a freshness watchdog that only the manual CLI writes is not a watchdog

**Date:** 2026-08-10
**Theme:** C7 (silent success is failure) / C9-adjacent (producer/consumer wiring)
**Source:** Gamma_Conductor AFTERHOURS fire, `engine-health.json` state_freshness RED

## Symptom

`automation/state/futures/data-freshness.json` was dated 2026-08-09 while the live
`Gamma_FuturesTrader` task ticked cleanly all session on 2026-08-10 (heartbeat GREEN,
dispatch GREEN, positions flat as expected). `state_freshness_audit.py` caught it:
"STALE BY SESSION: written_at_et=2026-08-09 but expected 2026-08-10".

## Root cause

`futures_live_data.py`'s `write_freshness_snapshot()` -- the function that persists the
freshness file -- was only ever called from that module's own `main()` (the
`--append`/`--check` CLI entry points). The actual live consumer,
`futures_trader_core.refresh_data()` (called every 5 minutes by the real trading tick),
READ `fld.FRESHNESS_FILE` to decide whether to rate-limit its own re-fetch, but never
WROTE it back. So the persisted snapshot silently froze at whatever a human's last
manual `--check` run happened to write, while the underlying live bar cache kept
refreshing correctly through a completely separate code path (`fld.append_live`,
called directly, not through the snapshot writer).

This module's own docstring explicitly names the C7 class it was built to prevent
(a two-month-stale bar file that "returns SOMETHING" without being current) -- and
then shipped with its own watchdog wired only to a CLI entry point nobody runs on a
schedule, not to the live call site. The watchdog needed a watchdog.

## Fix

`refresh_data()` now calls `fld.write_freshness_snapshot((root,), interval)` on every
call, unconditionally (both the "should refetch" and "rate-limited, skip" branches),
so the persisted file always reflects the live tick's real cadence. Guard:
`backtest/tests/test_futures_refresh_data_persists_freshness.py`.

## Generalizable rule for L## encoding

**A staleness/freshness snapshot file is only trustworthy if the CONSUMER-FACING
write path is called from the SAME code path as the actual live producer loop --
never only from a CLI entry point, a test fixture, or a "someone will run this
manually" assumption.** When adding any `write_*_snapshot()` / `write_*_health()`
style function, grep for every call site and confirm at least one of them is inside
the scheduled live tick, not just `if __name__ == "__main__"`. This is the same shape
as L241/L285/L286 (silent success) but specifically about *self-monitoring* code:
the monitor itself can go stale exactly like the thing it monitors, and nothing
catches that unless a SEPARATE, independent auditor (here: `state_freshness_audit.py`
+ `engine-health.json`) checks the monitor's own age too.

Candidate C-theme: fold into C7 (silent success is failure) row, or spin a new
C-theme if lesson-author judges "self-monitoring can itself go silently stale" as a
distinct enough pattern from the existing C7 examples.
