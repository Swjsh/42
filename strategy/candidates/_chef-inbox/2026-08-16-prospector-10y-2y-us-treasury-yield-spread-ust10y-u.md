# Chef Inbox — 10Y-2Y US Treasury yield spread (UST10Y - US2Y) as leading indicator f

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y-2Y US Treasury yield spread (UST10Y - US2Y) as leading indicator for MES/MNQ futures direction -- Widening spread reflects growth expectations and often coincides with equity rallies; flattening or inversion precedes equity pullbacks. Data source: Federal Reserve Economic Data (FRED) series GS10 and GS2, accessible via FRED API or Bloomberg tickers USGG10YR Index and USGG2YR Index. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y-2Y US Treasury yield spread (UST10Y - US2Y) as leading indicator for MES/MNQ futures direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series GS10 and GS2, accessible via FRED API or Bloomberg tickers USGG10YR Index and USGG2YR Index.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y-2y-us-treasury-yield-spread-ust10y-u) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
