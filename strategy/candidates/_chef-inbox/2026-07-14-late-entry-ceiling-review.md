# Chef research item: late-entry ceiling calibration

> Queued by Analyst 2026-07-14 (from the 2026-07-13 zero-supervision full audit).

## Observation

On 2026-07-13, `BEARISH_REJECTION_RIDE_THE_RIBBON` fired repeatedly for core Bold and core Safe
between 15:16 and 15:25 ET — passing scoring, trigger, and (where checked) the free-model veto
each time — and was killed by `SKIP_LATE_ENTRY` 8 times for bold and 6 times for safe (some of
safe's later fires were killed by `SKIP_DOJI_ENTRY_BAR` instead). Zero of these converted to a
fill. This is the SAME level/signal re-confirming itself repeatedly late in the session with
nothing entering.

## Hypothesis to test

The late-entry time ceiling (need exact threshold — appears to sit somewhere in the
15:00-15:15 ET window based on the self-check's "8 ENTER after 15:00 ET" framing) is too
conservative for a signal that keeps re-confirming cleanly, and is discarding legitimate
0DTE setups that still have 30-40 minutes to work before the 15:50 flatten.

## Backtest specification

- Date range: last 30 trading days, isolate every `SKIP_LATE_ENTRY` block event and simulate
  what the fill/exit would have looked like had it been allowed (using the actual bars from
  that point forward).
- Engine flag: the late-entry ceiling parameter (locate in `params.json` / entry_manager gate
  config — exact knob name not confirmed this session).
- Knob change (proposed): test moving the ceiling later in 15-minute increments (15:15 →
  15:30 → 15:40) and measure win rate / expectancy / hold-time-to-flatten for entries that
  would newly qualify.
- Edge_capture floor (per OP-16): must hit ≥771 to be PROMISING if it touches J-edge days;
  otherwise standard OOS + WF ≥0.70 bar applies.

## Why now

2026-07-13's own ledger shows the ceiling ate 14 gate-passing re-confirmations of one signal
in a single session — a concrete, countable cost, not speculation.
