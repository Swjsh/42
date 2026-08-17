# Chef Inbox — NYSE TICK index (TICK5) – real‑time net buy/sell pressure

**Routed by:** Gamma_Prospector 2026-08-17
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:openai/gpt-oss-20b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: NYSE TICK index (TICK5) – real‑time net buy/sell pressure -- A sudden surge in the TICK index indicates a burst of buying or selling that often precedes intraday volatility spikes useful for 0‑DTE option timing. Data source: NYSE TICK data feed via Bloomberg Terminal (Ticker: TICK5) or Nasdaq TotalView-ITCH. Cost: paid. Instrument fit: both.

## Research Question for Chef
NYSE TICK index (TICK5) – real‑time net buy/sell pressure -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: NYSE TICK data feed via Bloomberg Terminal (Ticker: TICK5) or Nasdaq TotalView-ITCH
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:nyse-tick-index-tick5-realtime-net-buyse) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
