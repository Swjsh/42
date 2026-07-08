# G11 — level_memory → key-levels.json producer — REVIEW SPEC (BLOCK-NEEDS-REVIEW)

**Status: BLOCKED-NEEDS-REVIEW (J nod, entry-path level-feed change).** Overnight loop 2026-07-08.

## The idea
`backtest/lib/watchers/level_memory.py` computes **memory-weighted multi-day** horizontal levels
(touches + role-flips + consolidation → `memory_score`) — the thing the live engine lacks
(07-07's 750.90 multi-day rejection was invisible to it; the live engine sees only today's
intraday levels). G11 wires level_memory as a producer into `automation/state/key-levels.json`
so the engine's level set carries battle-tested multi-day levels.

## Why it's entry-path (blast radius)
`key-levels.json` is consumed by the **live hot path**: `heartbeat_core.py`, `setup_dispatch.py`,
`self_check.py`, and the **filter-10 level-tied** entry logic. Producers today:
`refresh_levels_intraday.py` (intraday) + curated premarket levels. Adding level_memory levels
**changes the set of levels the engine reads → changes which entries filter-10 permits/blocks →
changes what the engine trades.** That is an entry behavior change, not a display change.

## Required before ship (A/B FIRST)
1. Feed-harness A/B: run the engine over the eval window with level_memory levels ADDED vs NOT,
   compare the ENTER set (extra/missed entries, and their real-fills P&L). A level producer that
   only ADDS levels can both help (catches 750.90-class rejections) and hurt (more level-tied
   blocks / false S/R). Must show net-positive or net-neutral edge capture, disclosed.
2. Schema/role parity: level_memory emits `role` (support/resistance) + `memory_score`; map to the
   key-levels schema WITHOUT re-introducing the contradictory-role bug (LEVELS-CONTRADICTORY-ROLES
   drain, queue.md) — one polarity role per price, price-cluster dedup at the producer.
3. Dedup vs existing producers (refresh_levels_intraday / curated) so a level isn't double-counted
   with a conflicting role (the same class as the 741.61/741.81 contradiction).

## Why review, not auto-ship
Live level-feed change with filter-10 entry blast radius, unproven net edge, and a known
role-contradiction foot-gun. Needs a supervised A/B + J's nod. The DETECT/ALERT half already
ships safely (G5: `level_memory.emit_reject_alert` pings J on a high-memory reject, notify-only) —
so the multi-day-level *awareness* is already live without touching the entry path; only the
*feed-into-entries* wiring is gated here.

Revert = drop the producer registration. Recommended: A/B in a supervised session; if net edge
capture ≥ baseline with roles clean, wire it.
