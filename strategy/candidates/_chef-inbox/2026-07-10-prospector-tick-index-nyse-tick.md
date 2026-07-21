# Chef Inbox — TICK Index (NYSE Tick)

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `data_feeds_free` surfaced: TICK Index (NYSE Tick) -- Measures the number of stocks ticking up vs down to identify extreme intraday exhaustion points for mean reversion. Data source: TradingView (Ticker: TICK) or Yahoo Finance via ^TICK. Cost: $0. Instrument fit: both.

## Research Question for Chef
TICK Index (NYSE Tick) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView (Ticker: TICK) or Yahoo Finance via ^TICK
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:tick-index-nyse-tick) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
