# Staleness clocks must reset on the last ACTUAL action, not the original creation date

**Found:** 2026-08-26, conductor AFTERHOURS fire, while investigating why `task_scorer.py --top`
kept ranking `TWIN-DOCTRINE-FIRST-DEPLOY` (`gp-2026-07-23-twin-doctrine-001`) #1 as
"STALE J-PING" every single fire since 2026-08-08, despite the item having actually been
re-pinged on Discord on 2026-08-18 (only 8 days before this fire).

**Root cause:** `_proposal_age_days()` in `setup/scripts/task_scorer.py` computed staleness as
`now - conductor-proposals.jsonl#created_at`. `created_at` is written once, at filing time, and
never updated. A "resurface as re-ping task past N days" rule built on a clock that never resets
will keep firing forever past day N, regardless of whether the thing it's nagging about ("please
re-ping") already happened recently. The bug's symptom looked exactly like its own fix's stated
purpose working correctly (a stale item correctly resurfacing) — the fix silently regressed into
the anti-pattern it was built to prevent (queue.md 2026-08-04: "would be spam ... not progress").

**Generalizable pattern:** any "N days since X, do Y again" rule needs to ask "N days since X, OR
since the last time Y actually happened" — otherwise Y's own execution doesn't register as
evidence and the rule nags at a fixed cadence relative to a frozen origin point forever. Check
other staleness/reminder logic in the repo for the same shape: a clock anchored to a creation/
filing timestamp with no way to observe "was the reminded action already taken since then."

**Fix:** `setup/scripts/task_scorer.py` — new `_last_ping_days()` scans `discord-outbox.jsonl`
for the newest row that actually names the proposal id (not a status-line claim of having pinged
— see the sibling 2026-08-18 lesson "conductor claimed re-ping never landed"). The resurfacing
branch now requires the original ask AND the last real re-ping (if any) to BOTH be stale.
Commit `d6e3ebaf`.

**Guard:** `backtest/tests/test_task_scorer_awaiting_j.py` — `test_recently_repinged_proposal_does_not_resurface` / `test_old_repinged_proposal_still_resurfaces` / `_last_ping_days` unit tests + an updated live-parity assertion.
