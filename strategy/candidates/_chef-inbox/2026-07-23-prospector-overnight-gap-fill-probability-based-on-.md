# Chef Inbox — Overnight Gap Fill probability based on gap size and VIX regime

**Routed by:** Gamma_Prospector 2026-07-23
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Overnight Gap Fill probability based on gap size and VIX regime -- Statistically determines the likelihood of a gap fill based on the ratio of the gap size to the 20-day ATR. Data source: Yahoo Finance / Alpha Vantage for daily SPY OHLC and VIX levels. Cost: $0. Instrument fit: both.

## Research Question for Chef
Overnight Gap Fill probability based on gap size and VIX regime -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Yahoo Finance / Alpha Vantage for daily SPY OHLC and VIX levels
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:overnight-gap-fill-probability-based-on-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
