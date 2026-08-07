# Chef Inbox — VIX term‑structure contango/backwardation signal

**Routed by:** Gamma_Prospector 2026-08-07
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: VIX term‑structure contango/backwardation signal -- When short‑dated VIX (VIX1D) is much higher than longer‑dated VIX (VIX1M) it signals heightened near‑term volatility pressure that often precedes SPY 0DTE directional moves. Data source: CBOE VIX1D (^VIX1D) and VIX1M (^VIX1M) tickers via free CBOE data feed or Polygon.io API. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
VIX term‑structure contango/backwardation signal -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE VIX1D (^VIX1D) and VIX1M (^VIX1M) tickers via free CBOE data feed or Polygon.io API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:vix-termstructure-contangobackwardation-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
