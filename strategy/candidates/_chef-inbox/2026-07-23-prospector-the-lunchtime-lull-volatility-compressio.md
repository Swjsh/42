# Chef Inbox — The 'Lunchtime Lull' volatility compression and mean reversion

**Routed by:** Gamma_Prospector 2026-07-23
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: The 'Lunchtime Lull' volatility compression and mean reversion -- Captures the decrease in institutional volume between 12:00 PM and 1:30 PM EST leading to predictable range-bound behavior. Data source: CME Group Volume and Open Interest data for MES/MNQ. Cost: $0. Instrument fit: both.

## Research Question for Chef
The 'Lunchtime Lull' volatility compression and mean reversion -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CME Group Volume and Open Interest data for MES/MNQ
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:the-lunchtime-lull-volatility-compressio) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
