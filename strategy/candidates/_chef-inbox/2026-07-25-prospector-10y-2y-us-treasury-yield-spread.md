# Chef Inbox — 10Y-2Y US Treasury yield spread

**Routed by:** Gamma_Prospector 2026-07-25
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y-2Y US Treasury yield spread -- Widening (steepening) spread reflects growing recession expectations and tends to precede downside moves in equity index futures. Data source: FRED series DGS10 and DGS2 (10‑year and 2‑year Treasury yields), downloadable via the FRED API. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y-2Y US Treasury yield spread -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: FRED series DGS10 and DGS2 (10‑year and 2‑year Treasury yields), downloadable via the FRED API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y-2y-us-treasury-yield-spread) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
