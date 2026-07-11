# THE TWIN PROGRAM — operating system for the 24/7 crypto twin (Fable design, 2026-07-11)

> Account live as of 2026-07-11 (~09:04 ET): dedicated paper acct PA38EG1JTFBT, crypto_status
> ACTIVE, twin `account_status: LIVE`. This doc is the THINKING; build order at the bottom.
> Standing doctrine: the twin validates MECHANISM, never edge. Twin P&L = health gauge.
> Twin findings may only propose changes to CODE, never to SPY parameters.

## Reframe
SPY = ~1 uncontrolled experiment/day. The twin = unlimited CONTROLLED experiments, any hour.
Don't wait for the market to exercise a code path — SCHEDULE the path.

## Value streams (ranked)
1. **Scenario scheduler / path-coverage battery.** Force every exit lifecycle branch through
   REAL paper fills daily (TP1→trail, structure-stop, cat-cap, max-hold, restart-with-open
   -position). Scoreboard: paths exercised / paths green, per day. A HOLD-all-day twin
   validates nothing — coverage-oriented by design, opposite of production selectivity.
2. **Twin Gauntlet.** `twin_gauntlet --paths <changed>` forces N real lifecycles through a
   just-changed code path and diffs vs expected. Conductor hook: trading-path commits without
   a gauntlet pass get flagged. This mechanizes "fix → live-verified in minutes."
3. **Transferable execution research.** Broker-interaction mechanics are instrument-agnostic:
   fill-poll reconciliation (T-AUDIT-03 class), exit refire dedupe (F7 class), partials,
   passive-limit entry machinery (T-W5) runs LIVE here and graduates on real fills before SPY.
4. **Chaos drills (weekly).** Injected failures we'd never dare on SPY: process kill
   mid-position, corrupt state file, stale feed, breaker mid-trip. Resilience ledger.
5. **Detector telemetry (shadow).** Pattern-grammar rules log-only on live crypto: firing
   rates, repaint-safety, C6 closed-bar discipline. Never edge claims.
6. **Learn-loop reps.** Autopsy/funnel/hypothesis machinery cycles dozens of times daily.
   Twin-hypothesis lane restricted to CODE fixes.

## Design decisions (the subtle stuff)
- **UNIT-LOT MODE (required):** fractional crypto would silently skip integer-qty arithmetic
  (2/1 TP1-runner split, int floors). Twin trades qty=3 fixed units (1 unit = small BTC
  quantum) so exit_manager.from_entry's exact production integer paths run live.
- **Long-only limitation:** Alpaca crypto can't short → bear-side (P) lifecycles stay
  fixture-tested (side-mirrored unit tests). Documented gap, not hidden.
- **Attribution discipline:** every row/fill/journal entry twin-tagged; firm brief gets a
  TWIN line with the path-coverage scoreboard (P&L small, labeled health-only).
- **Param freeze:** twin signal/exit params change only for COVERAGE reasons, never chasing
  twin P&L. No new symbols until BTC mechanics prove limiting.
- **Fee model note:** Alpaca crypto taker fees ≠ options economics — one more reason twin
  P&L is never comparable/transferable.

## ROI metric (honesty rail)
`mechanism_bugs_caught_before_RTH` (twin-attributed findings that produced a code fix before
the next SPY session). If not accumulating within ~2 weeks, re-examine the program.

## Build order
- **B1 (now, Sonnet):** unit-lot mode + scenario scheduler + path-coverage scoreboard state.
- **B2 (now, Sonnet):** twin gauntlet + conductor hook; attribution + twin-autopsy lane +
  firm-brief scoreboard line.
- **B3 (queued):** entry_manager live measurement on twin (graduate T-W5).
- **B4 (queued):** weekly chaos drill + resilience ledger.
- **B5 (queued):** pattern-grammar shadow telemetry on twin.
- **Doctrine:** CLAUDE.md one-liner proposal (propose-only) folding the amended crypto
  boundary + this program's existence; memory entry.
