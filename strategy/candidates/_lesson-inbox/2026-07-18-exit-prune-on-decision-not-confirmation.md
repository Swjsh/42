---
title: exit ledger must prune on CONFIRMED sell, not on the DECISION to sell
filed: 2026-07-18
filed_by: conductor-weekend
source: F7-EXIT-SELL-ALL-REFIRE (queue.md, filed 2026-07-08 G10 audit tail)
---

## Symptom (as originally filed)
"exit engine re-fires a full-size SELL_ALL every tick while the prior exit order is
pending_new -> duplicate sells risk."

## What was actually found (2026-07-18 investigation)
The literal symptom didn't reproduce from the code as filed -- but the SAME root
defect class was real, in the opposite direction. `exit_actuator.manage_tick`
computed `dec.closes_position` (True whenever `plan_exit_actions` decided to emit a
SELL_ALL) and used THAT to prune the tracked exit-state ledger entry
(`del states[symbol]`) -- **unconditionally, regardless of whether
`broker.market_sell` actually succeeded.** Two failure modes hid behind one line:

1. **Silent orphan (worse than a re-fire):** if `market_sell` errored (API
   rejection, network failure), the ledger entry was deleted anyway. The position
   stayed open on the broker but exit_actuator would never manage it again --
   NOT a re-fire, a permanent forget, until the 15:55 ET EOD-flatten backstop
   caught it.
2. **Genuine duplicate-sell risk (the originally-feared case), one layer deeper
   than "pending_new":** a `urllib` request can raise `TimeoutError`/`URLError`
   on reading the RESPONSE even after Alpaca already accepted the POST server-side.
   A naive "retry on failure" fix (undoing #1 alone) would have reintroduced this
   exact risk -- stacking a second real market sell on an order that already landed.

## The general lesson
**A ledger/state-machine transition driven by a system with an unreliable
confirmation channel (network calls, async fills, eventual-consistency reads) must
gate its prune/finalize step on CONFIRMED completion, not on the DECISION to act.**
"We decided to do X" and "X happened" are different facts; conflating them either
loses track of failures (orphaning) or, if naively fixed by blind retry, risks
duplicating already-successful actions. The correct pattern needs BOTH halves
together:
  - don't finalize/prune on decision alone -- only on confirmed success (or an
    explicit "safe to abandon" signal, e.g. WATCH-mode preview);
  - before retrying an apparently-failed action, check the EXTERNAL system's own
    state for evidence the action already landed (here: `open_sell_orders` --
    is there already a resting sell order for this symbol?) so retry-on-failure
    doesn't become duplicate-on-success-that-looked-like-failure.

## Where else this pattern might apply
Any other place in this codebase that calls a broker/API mutation and then
unconditionally updates local state assuming success, without checking the
response for `_error`/`_refused`, is a candidate for the SAME two-sided bug.
`place_bracket` / atomic entry placement was NOT audited this fire (narrower,
bounded-task scope) -- worth a follow-up sweep.

## Fix shipped
`automation/state/fleet/fleet_broker.py` (`open_sell_orders`) +
`automation/state/fleet/exit_actuator.py` (`manage_tick`'s SELL_PARTIAL/SELL_ALL
branch + the `closes_position` prune gate). Guard: `test_exit_actuator.py`, 4 new
tests (duplicate-guard skip, failed-sell-not-pruned-retries, WATCH-mode
unaffected, base-FakeBroker-without-the-method unaffected), RED-proofed via
`git stash`. Both core (Safe/Bold via `heartbeat_core._manage_exits`) and all 4
fleet arms share this one code path -- one fix, both lanes.
