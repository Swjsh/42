# Chef Inbox — 10Y-2Y Treasury yield spread (DGS10-DGS2) from FRED as a macro‑risk ga

**Routed by:** Gamma_Prospector 2026-07-31
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y-2Y Treasury yield spread (DGS10-DGS2) from FRED as a macro‑risk gauge for equity direction -- Flattening or inversion of the spread reflects rising recession fears and tends to precede bearish equity moves, whereas steepening signals growth optimism and bullish bias. Data source: Federal Reserve Economic Data (FRED) series DGS10 and DGS2, accessible via the FRED API or Quandl. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y-2Y Treasury yield spread (DGS10-DGS2) from FRED as a macro‑risk gauge for equity direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series DGS10 and DGS2, accessible via the FRED API or Quandl
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y-2y-treasury-yield-spread-dgs10-dgs2-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
