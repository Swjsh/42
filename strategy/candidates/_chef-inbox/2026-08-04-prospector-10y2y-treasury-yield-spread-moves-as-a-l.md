# Chef Inbox — 10Y‑2Y Treasury yield spread moves as a leading indicator for equity i

**Routed by:** Gamma_Prospector 2026-08-04
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y‑2Y Treasury yield spread moves as a leading indicator for equity index futures direction -- A steepening 10Y‑2Y spread reflects growth/inflation expectations and tends to precede bullish moves in SPY 0DTE and MES/MNQ futures; flattening or inversion precedes bearish moves. Data source: FRED series GS10 (10‑year) and GS2 (2‑year) yields, downloadable via FRED API, Quandl, or Bloomberg. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y‑2Y Treasury yield spread moves as a leading indicator for equity index futures direction -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: FRED series GS10 (10‑year) and GS2 (2‑year) yields, downloadable via FRED API, Quandl, or Bloomberg
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y2y-treasury-yield-spread-moves-as-a-l) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
