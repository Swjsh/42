# Lesson candidate: strict-priority starvation + dead-letter queue events

> Queued by evening fix session 2026-07-09. lesson-author picks up at next wake fire.

## Symptom

The kitchen seeder's meta-task brainstorm lane went SILENT for 17 days (last
`source=seeder` create event 2026-06-22T14:23:43) while the scheduled task kept
firing hourly and exiting 0. Verified 2026-07-09: 20 `priority=low` seeder
tasks pending 37–49 days, live `llm_pending=36 >= MAX_PENDING_BACKLOG=25`, so
the seeder's Step-2 skip-gate was permanently tripped. Separately, 13
historical `requeue reason=archived*` events and 12 `close` events (failure
cleanup purge/quarantine) had been emitted over weeks with ZERO effect.

## Root cause

Two independent mechanisms, same file:

1. **Strict-priority scheduling + continuous inflow = permanent starvation.**
   `kitchen_daemon._pick_next_task` ranked by raw label then age. Reviewer /
   grinder-auto / analyst-eod-auto inject medium/high tasks continuously, so a
   `low` task could NEVER be picked — and the seeder's own prompt instructs
   the model to label brainstorm tasks `low`. The starved backlog then kept
   the producer's backpressure gate tripped: starvation upstream compounded
   into silence downstream.
2. **Documented queue-control events nobody's code honored (dead letters).**
   KITCHEN-SPEC step 6 grants "emit a `requeue` event with reason=archived to
   clear stale tasks", and `kitchen_failure_cleanup.py` emits `close` events —
   but `_load_queue` forced EVERY `requeue` to `status=pending` and ignored
   `close` entirely. Archive attempts silently RESURRECTED their targets
   (task `25a0d08d` was "archived" 2026-06 and still sat pending 2026-07-09).
   C14-adjacent: the knob existed in doctrine and in producers, but the
   consumer never applied it; nothing asserted the round-trip.

## Fix

Commit on branch `claude/gracious-mclean-39ce9a` (2026-07-09):
- `setup/scripts/kitchen_daemon.py`: `_effective_priority` — pending tasks age
  one priority tier per 24h (`PRIORITY_AGE_PROMOTE_HOURS`), capped at `high`;
  oldest-first within a tier makes every task eventually win. `critical`
  unreachable by aging. `_load_queue` now collapses `requeue reason~=archived*`
  to terminal `archived` and `close` to terminal `closed`.
- `setup/scripts/kitchen_queue_gc.py`: repeatable dry-run-first prune tool
  with post-apply self-verification.
- Live queue pruned: 20/20 stale seeder lows archived, pending 50→30,
  llm_pending 36→16.

## Encoded in

- `backtest/tests/test_kitchen_daemon_starvation.py` (17 guard tests: tier
  math, starved-low-beats-continuous-high-inflow regression, raw-predicate
  grinder deferral, archived/closed collapse, GC dry-run/apply).
- `markdown/infra/KITCHEN-SPEC.md` "Scheduler starvation + priority aging"
  note + updated Prune step.

## L## (optional)

Generalizable rules: (a) a strict-priority queue with a continuously-refilled
upper tier starves its bottom tier FOREVER — any scheduler needs aging or a
starvation floor, and any priority guidance that says "mark X low" is a
delete-X instruction until it has one; (b) an event type that producers emit
but no consumer collapses is a dead letter — grep the consumer for every event
kind the spec/tools emit, and guard the round-trip (emit → collapse → status)
with a test. Candidate themes: C7 (silent success), C14 (dead knobs), C15
(gates interact multiplicatively: starvation tripped the backlog gate).
