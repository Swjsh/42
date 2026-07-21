# Chef Inbox — NYSE TICK index measuring net upticks vs downticks across NYSE stocks

**Routed by:** Gamma_Prospector 2026-07-13
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: NYSE TICK index measuring net upticks vs downticks across NYSE stocks -- Extreme TICK readings signal short-term overbought/oversold conditions that often precede intraday reversals in SPY and equity index futures. Data source: NYSE TICK index symbol $TICK, available via Bloomberg, Refinitiv, or paid feeds such as Polygon.io. Cost: paid. Instrument fit: both.

## Research Question for Chef
NYSE TICK index measuring net upticks vs downticks across NYSE stocks -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE TICK index symbol $TICK, available via Bloomberg, Refinitiv, or paid feeds such as Polygon.io
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:nyse-tick-index-measuring-net-upticks-vs) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
