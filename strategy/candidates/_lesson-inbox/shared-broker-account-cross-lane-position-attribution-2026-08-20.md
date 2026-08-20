---
filed: 2026-08-20
filed_by: conductor (AFTERHOURS, desk_allocator.py "DECISION ROTTING" -- futures desk MES mirror arming)
kind: lesson
status: pending
---

# Two independent execution lanes on the SAME broker account + instrument cannot tell their own fill from the other lane's -- `is_flat()`/position queries are account-truth, not lane-truth

## Symptom (caught before shipping, not in production)

Arming the MES mirror-shadow signal (`futures_mirror_shadow.py`, cleared its 20-round-trip
bar 2026-08-19: 59 trips, +$1,268.66, beats null) for real broker execution looked like a
pure "flip the switch" task -- `place_bracket()` / `make_broker("tastytrade")` already exist,
already proven end-to-end live (2026-08-09: dry run, resting order, filled marketable order).
It is not a flip-the-switch task: `Gamma_FuturesBrokerLane` (the `should_take_v3` signal)
already trades REAL sandbox orders on the exact same account (`5WW73759`) and the exact same
instrument (`MES`) -- confirmed live via `trader-broker/open-position.json`
(`{"symbol": "/MESU6", "qty": "2", ...}`, dated the prior trading day).

## Root cause

`TastytradeBroker.is_flat(instrument)` and `.get_positions()` query the BROKER's actual
account state. A broker position is not partitioned by which local script opened it -- there
is no "lane" concept on the wire. Two independently-scheduled lanes trading the same
instrument on the same account are, from the broker's point of view, indistinguishable
callers sharing one pool of risk and one position slot.

## Why this did NOT need a redesign (the fix that generalises)

The SAME primitive that creates the risk also resolves it for free, IF both lanes read it as
their own no-stack gate: `broker.is_flat(instrument)` already reflects BOTH lanes' fills, so a
lane that gates new entries on "is the broker flat" naturally defers to whatever position
ANY lane already holds -- no shared lock file, no new coordination primitive, no cross-lane
awareness needed. `futures_trader_core.run_tick()`'s existing step 5 ("No stacking") already
does this for the `should_take_v3` lane; the new `_broker_execute_entry()` does the same
check before placing. Two lanes independently checking the SAME account-level truth is
sufficient coordination for a 5-minute polling cadence -- NOT sufficient for anything faster
(a genuine same-second race is disclosed, not solved: see "residual risk" below).

## The generalisation worth keeping

**Before wiring a SECOND execution lane onto an account/instrument an existing lane already
trades, ask three questions in order:**
1. Does the new lane's no-stack gate read BROKER truth (`is_flat`/`get_positions`), or only
   its own local state file? Local-only state is blind to the other lane and WILL stack.
2. Do the risk rails (account floor, session loss cap) read LIVE broker equity, or a
   per-lane assumed starting balance? Equity read live already reflects both lanes' fills,
   so account-floor protection is automatically shared-correct; a per-lane static equity
   number is not.
3. What is the polling cadence of both lanes, and is a same-window double-fire tolerable?
   Bounded by per-trade dollar caps and paper money, a residual low-probability race can be a
   disclosed, not-solved risk -- but it must be DISCLOSED, in the code comment and the task
   description, not silently assumed away.

## Residual risk (disclosed, not solved, 2026-08-20)

A same-5-minute-window TOCTOU race between `Gamma_FuturesMirror --armed` and
`Gamma_FuturesBrokerLane` remains possible in principle: both could read `is_flat()=True`
before either places an order. Bounded by: paper money, each lane's own per-trade dollar cap
($100 broker lane / $150 mirror lane), and the account floor reading live combined equity.
A shared OS-level claim file (same pattern as the 2026-08-19 SPY-engine atomic-entry-claim
fix, `msvcrt.locking`) is the correct eventual fix if this ever needs tightening -- not built
tonight; follow-up filed to `queue.md`.

## Guards

- `backtest/tests/test_futures_mirror_shadow.py::TestArmedExecution::test_armed_refuses_to_stack_on_the_broker_account`
  -- proves a broker-reported open position (regardless of which lane opened it) blocks a new
  mirror entry.
- 11 sibling tests in the same class cover: default-off zero-behavior-change, env read fresh
  (not cached at import), buffered marketable-limit sign correctness (long buffers up, short
  buffers down), broker-not-connected fail-open, per-trade-risk-cap rejection (never resized),
  internal-exception fail-open, and the full `run_once()` integration proving the shadow
  ledger and the broker ledger are written independently (arming the broker leg never mutates
  the pre-existing arming-bar evidence stream).
