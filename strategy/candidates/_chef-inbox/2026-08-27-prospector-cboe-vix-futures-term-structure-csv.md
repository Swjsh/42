# Chef Inbox — CBOE VIX Futures Term Structure CSV

**Routed by:** Gamma_Prospector 2026-08-27
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `data_feeds_free` surfaced: CBOE VIX Futures Term Structure CSV -- The slope of the VIX futures curve encodes market‑wide volatility expectations, which can improve timing of 0DTE SPY and MES/MNQ trades. Data source: CBOE Data Shop – free daily CSV of VIX Futures (ticker VIX) – https://www.cboe.com/data/historical-data/. Cost: $0. Instrument fit: both.

## Research Question for Chef
CBOE VIX Futures Term Structure CSV -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CBOE Data Shop – free daily CSV of VIX Futures (ticker VIX) – https://www.cboe.com/data/historical-data/
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:cboe-vix-futures-term-structure-csv) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
