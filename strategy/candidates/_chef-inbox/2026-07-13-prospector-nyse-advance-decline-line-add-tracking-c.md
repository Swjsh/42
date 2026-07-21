# Chef Inbox — NYSE Advance-Decline Line (ADD) tracking cumulative breadth

**Routed by:** Gamma_Prospector 2026-07-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: NYSE Advance-Decline Line (ADD) tracking cumulative breadth -- Divergence between ADD and price indicates weakening/strengthening market internals, useful for filtering false breakouts in 0DTE options and futures. Data source: NYSE Advance-Decline Line data, symbol $ADLINE, distributed by Bloomberg, Refinitiv, or free via Quandl dataset NYSE/ADLINE. Cost: paid. Instrument fit: both.

## Research Question for Chef
NYSE Advance-Decline Line (ADD) tracking cumulative breadth -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE Advance-Decline Line data, symbol $ADLINE, distributed by Bloomberg, Refinitiv, or free via Quandl dataset NYSE/ADLINE
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:nyse-advance-decline-line-add-tracking-c) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
