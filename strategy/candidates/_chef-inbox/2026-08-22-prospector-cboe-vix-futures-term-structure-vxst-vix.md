# Chef Inbox — CBOE VIX Futures Term Structure (VXST, VIX, VIX9D)

**Routed by:** Gamma_Prospector 2026-08-22
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: CBOE VIX Futures Term Structure (VXST, VIX, VIX9D) -- The steepness of the VIX futures curve anticipates near‑term volatility spikes that drive 0DTE SPY option premiums. Data source: CBOE website free CSV download (https://www.cboe.com/publish/scheduled/data_series/vix_futures.csv). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
CBOE VIX Futures Term Structure (VXST, VIX, VIX9D) -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE website free CSV download (https://www.cboe.com/publish/scheduled/data_series/vix_futures.csv)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cboe-vix-futures-term-structure-vxst-vix) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
