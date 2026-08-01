# Chef Inbox — NYSE Advance-Decline Line (ADD) – cumulative net advancing issues

**Routed by:** Gamma_Prospector 2026-08-01
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: NYSE Advance-Decline Line (ADD) – cumulative net advancing issues -- Divergence between ADD and price can signal weakening breadth, predictive of pullbacks in SPY and futures. Data source: NYSE Advance-Decline data published on NYSE.com and available via Quandl dataset NYSE/AD_LINE. Cost: paid. Instrument fit: both.

## Research Question for Chef
NYSE Advance-Decline Line (ADD) – cumulative net advancing issues -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE Advance-Decline data published on NYSE.com and available via Quandl dataset NYSE/AD_LINE
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:nyse-advance-decline-line-add-cumulative) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
