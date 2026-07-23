# Chef Inbox — The Opening Range Breakout (ORB) predictive power for intraday trend d

**Routed by:** Gamma_Prospector 2026-07-23
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: The Opening Range Breakout (ORB) predictive power for intraday trend direction -- Exploits the price discovery phase where the first 15-30 minutes of trading establish the day's dominant bias. Data source: Tukey's 'Exploratory Data Analysis' principles applied to SPY 1m OHLC data via Polygon.io API. Cost: paid. Instrument fit: both.

## Research Question for Chef
The Opening Range Breakout (ORB) predictive power for intraday trend direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Tukey's 'Exploratory Data Analysis' principles applied to SPY 1m OHLC data via Polygon.io API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:the-opening-range-breakout-orb-predictiv) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
