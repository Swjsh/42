# Chef Inbox — Opening Range Breakout (ORB) predictive power for 0DTE SPY

**Routed by:** Gamma_Prospector 2026-07-29
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `academic_intraday_anomalies` surfaced: Opening Range Breakout (ORB) predictive power for 0DTE SPY -- The first 30‑minute price range often establishes the day's directional bias, and a breakout beyond that range predicts continuation with a measurable edge. Data source: Intraday SPY minute bars from NYSE TAQ (or Polygon.io free tier). Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
Opening Range Breakout (ORB) predictive power for 0DTE SPY -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: Intraday SPY minute bars from NYSE TAQ (or Polygon.io free tier)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: academic_intraday_anomalies:opening-range-breakout-orb-predictive-po) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
