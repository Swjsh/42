---
filed: 2026-08-12
filed_by: fable (EOD investigation, ~16:05 ET)
kind: lesson
status: pending
---

# An intraday "what is the engine doing" answer read ONE ledger (core) and was reported as the BOOK — while a fleet arm was already short, 13 minutes earlier

## Symptom

At 10:17 ET J asked whether we played the open rejection. The answer given: "the engine
never generated a single bearish verdict today — 93 ticks, 30 ENTER_BULL, zero ENTER_BEAR."
That was computed from `automation/state/core-decisions.jsonl` alone. **risky-3 had bought
771 puts at 09:46:09** — the book WAS short the open rejection, via the fleet path, before
the question was even asked.

## Root cause

The book has (at least) two execution paths with separate ledgers: core (safe-2/bold-2 →
`core-decisions.jsonl`) and fleet (`fleet/<arm>/decisions.jsonl` × 3 live arms). A query
against one path was presented with book-wide language ("the engine"). Exact sibling of
L244 (fill-funnel monitor blind to a second execution path reported a real trading day
IDLE) — same blindness, this time in a live conversational read instead of a monitor.

## Rule to carry forward

1. Any intraday activity answer ("did we trade X", "are we long/short", "did we play Y")
   must sweep core + ALL live fleet ledgers, or say explicitly which path it covers.
2. Direction-coverage asymmetry is load-bearing information: core produced zero bear
   verdicts today while the loosest fleet arm shorted — "the engine's view" is per-path,
   and per-path divergence is itself a finding to report, not noise to average away.
3. Candidate instrument (OP-33e, repeated-question class): a `book_activity_now.py` that
   unions all ledgers + broker fills for "what has the book done today" — one command,
   no per-path grepping, impossible to scope-miss.

Kin: L244/C7, L234 (arm-scope filter goes stale when the lineup moves).
