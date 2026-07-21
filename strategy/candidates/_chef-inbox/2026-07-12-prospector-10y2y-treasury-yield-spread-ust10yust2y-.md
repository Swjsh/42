# Chef Inbox — 10Y‑2Y Treasury yield spread (UST10Y‑UST2Y) from FRED

**Routed by:** Gamma_Prospector 2026-07-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: 10Y‑2Y Treasury yield spread (UST10Y‑UST2Y) from FRED -- Flattening or inversion of the spread reflects growing recession expectations and tends to lead equity index moves, providing a macro‑directional cue for 0DTE SPY and MES/MNQ. Data source: Federal Reserve Economic Data (FRED) series GS10 (10‑Yr) and GS2 (2‑Yr) accessible via the FRED API. Cost: $0. Instrument fit: both.

## Research Question for Chef
10Y‑2Y Treasury yield spread (UST10Y‑UST2Y) from FRED -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) series GS10 (10‑Yr) and GS2 (2‑Yr) accessible via the FRED API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:10y2y-treasury-yield-spread-ust10yust2y-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
