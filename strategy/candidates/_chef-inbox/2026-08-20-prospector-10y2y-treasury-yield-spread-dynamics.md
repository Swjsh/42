# Chef Inbox — 10Y‑2Y Treasury yield spread dynamics

**Routed by:** Gamma_Prospector 2026-08-20
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y‑2Y Treasury yield spread dynamics -- Widening spread often precedes risk‑off moves, providing a macro‑risk signal for both SPY options and MES/MNQ futures. Data source: Federal Reserve Economic Data (FRED) series DGS10 and DGS2 via the FRED API. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y‑2Y Treasury yield spread dynamics -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series DGS10 and DGS2 via the FRED API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y2y-treasury-yield-spread-dynamics) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
