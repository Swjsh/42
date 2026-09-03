# WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM (2026-09-03)

Filed off WALKER-REANCHOR-FULL-ENGINE-POPULATION's 42-row stage-disagree bucket (56% of the
pooled full-population dollar error). Full data + citations:
[`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03.json`](WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03.json).
Extractor (read-only, reuses `walker_full_population_anchor.py` unmodified):
[`backtest/tools/walker_structure_stop_misfire_extract.py`](../../backtest/tools/walker_structure_stop_misfire_extract.py).

## Correction to the queue item's own premise

The queue item assumed the 42 misfire rows were identifiable in the published
`WALKER-FULL-POPULATION-ANCHOR-2026-09-03.json`. They are not: that tool's `main()` only ever
persists `_bucket_stats(...)` aggregates (n/ratio/median/verdict) into the JSON, never
`hv["rows"]` itself -- verified by reading the file (no `"rows"` key anywhere) and the tool's
own source. Rows were re-derived tonight by rerunning the exact same
`run_via_harness_validation` monkeypatch path at `exit_slippage=None`, zero new OPRA calls (all
96 contracts already disk-cached). The reproduced n=42 and 55.98% disagree-share match the
published numbers exactly.

## Histogram (42 rows)

| Class | n | $ abs error | share of disagree error |
|---|---|---|---|
| **TIMING** (replay `walked_stage=="structure_stop"`, recorded something else) | 14 | $3,456.00 | 45.2% |
| &nbsp;&nbsp;of which high-impact (sign-flip or >=$100) | 10 | $3,397.00 | 44.4% |
| &nbsp;&nbsp;of which low-impact (same sign, <$100) | 4 | $59.00 | 0.8% |
| **OTHER** (replay picks a non-structure stage; includes 5 rows where LIVE recorded structure_stop and replay under-fires it) | 28 | $4,188.40 | 54.8% |
| STOP_MODE_MISMATCH | 0 | -- | ruled out |
| LEVEL_SOURCE_MISMATCH | 0 | -- | ruled out |
| BAR_FIELD_MISMATCH | 0 | -- | ruled out (folded into TIMING as a cadence question) |

## Why STOP_MODE_MISMATCH and LEVEL_SOURCE_MISMATCH are ruled out

- **Level source**: `trades_enriched.py:429-437` (core) and `:479-484` (fleet) document and
  implement that `trigger_level` is the PLACEMENT-stage level `exit_manager.py` actually armed
  live (`exec.trigger_level` / fleet `placement.trigger_level`) -- the same field
  `anchor_trigger_level()` feeds the replay with. Same level, same source, both sides.
- **Stop mode**: `anchor_trigger_level()` returns `0.0` whenever `stop_mode=="premium"`, so
  `walk_exit_manager(..., structure_stop_enabled=bool(trigger_level), ...)` correctly disables
  structure for every premium-mode row. Verified: 0 of the 42 rows have an unrecorded
  (`None`) stop_mode, and 0 of the premium-mode rows have `walked_stage=="structure_stop"`.
- **Bar field**: `exit_manager_walk.last_closed_bar_close_at`'s own docstring: "Mirrors
  heartbeat_core.py's `bc["bar"]["close"]` (trig_idx=n-2) convention." Confirmed at
  `heartbeat_core.py:1762`: `_closed_5m_close = bc["bar"]["close"]`. Same field (closed 5-min
  bar close), same trig_idx=n-2 selection, both sides.

## The mechanism

The replay recomputes the closed-5-min-bar close **deterministically, once per 1-minute step,
from a complete cached SPY CSV**. Live only re-evaluates that same value **once per actual
heartbeat tick**, using whatever bar was current at that tick's fetch -- and for fleet arms
(safe-3/risky-1, `fleet_live.py:938`) the feed is a shared `shared-signal.json` written by the
core process, gated dead (`_closed_5m_close=None`, check skipped that tick) whenever it is
older than `SIGNAL_MAX_AGE_SEC=420s` (7 min). A transient dip through the trigger level that the
replay's exhaustive per-bar scan always catches can be a dip live's discrete, tick-gated (and
for fleet arms, staleness-gated) polling never armed on.

**Worked example** (`2026-08-13 SPY260813C00777000`): one CALL signal fired 09:51:05-09:52:10
ET across bold-2/risky-1/safe-2/safe-3, trigger_level=776.85. Live: all 4 won via `tp1+trail`
(+$534/+$405/+$332/+$348). Replay: all 4 walked `structure_stop` (+$25/-$25/+$9/-$18) -- one
misfire event, replicated 4x by sizing, not four independent failures.

## Recurrence

27 distinct (symbol, date) keys across the 42 rows; **11 of them are hit by more than one arm**,
covering **26/42 rows (62%)**. The mechanism is signal-day-correlated, not
independently-distributed per-arm noise.

## safe-2 contrast

safe-2 carries the *most* disagree rows of any arm (13/42) -- it is not spared the mechanism,
and it is IN the 08-13 four-way recurrence. It still PASSES (ratio 0.963) because its ATM /
lower-leverage sizing dampens the dollar impact of the same misfire event relative to bold-2's
OTM-2 aggressive sizing on the identical trigger (08-13: safe-2 -$323 vs bold-2 -$509, same
signal). It is not explained by more premium-mode trades (safe-2 32% premium-mode vs
bold-2/safe-3 0%) or a different level/bar-field path -- both are identical code for every arm.

## Fix location

Neither adapter (level + stop_mode already correctly threaded) nor walker bar-field logic
(field convention already matches live's own documented design) is wrong. The gap is
**live-poll-semantics representation**: the replay has no model of the actual historical tick
cadence or the fleet-arm staleness gate. `core-decisions.jsonl` / fleet `decisions.jsonl` do log
a per-tick `trigger_bar_et` + spot, so a tick-faithful walk is theoretically buildable, but that
is real new work, not attempted tonight (budget) -- flagged as the next research step, not a
code change proposed here.

## UNVERIFIED

- Exact live tick-by-tick `bc["bar"]["close"]` history for the 10 high-impact TIMING rows was
  not cross-referenced against the ledgers to directly prove the dip-and-recover pattern
  (asserted from documented design + the existing SIGHT-FRESHNESS-GUARD precedent, not
  re-measured this session).
- Whether the walker's `spy_by_day()` union-of-CSV SPY series could itself carry a stray/lower
  close than live ever fetched (data-provenance check, not attempted).
- The 28-row OTHER bucket's sub-mechanism is asserted from `exit_manager_walk.py`'s own
  documented fill-price-convention gap, not independently re-derived per row tonight.

## Queue closure

`WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM :: status:done` -- mechanism named (TIMING: replay's
exhaustive per-bar structure check vs live's discrete/tick-gated, and for fleet arms
staleness-gated, poll). STOP_MODE_MISMATCH and LEVEL_SOURCE_MISMATCH ruled out with code
citations; BAR_FIELD_MISMATCH ruled out as a field-type question and folded into TIMING as a
cadence question. No code change proposed. WALKER-CONSUMERS-MIGRATE-TO-EXIT-MANAGER-WALK stays
Fable's call.
