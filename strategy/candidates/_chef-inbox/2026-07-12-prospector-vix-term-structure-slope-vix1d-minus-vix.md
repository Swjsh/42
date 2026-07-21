# Chef Inbox — VIX term structure slope (VIX1D minus VIX30) from CBOE

**Routed by:** Gamma_Prospector 2026-07-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: VIX term structure slope (VIX1D minus VIX30) from CBOE -- A steep backwardation (near-term VIX much higher than 30‑day) signals heightened short‑term fear and often precedes intraday reversals in SPY 0DTE options and MES/MNQ futures. Data source: CBOE VIX1D index (^VIX1D) and VIX30 index (^VIX) available free via most market‑data vendors or the CBOE website API. Cost: $0. Instrument fit: both.

## Research Question for Chef
VIX term structure slope (VIX1D minus VIX30) from CBOE -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: CBOE VIX1D index (^VIX1D) and VIX30 index (^VIX) available free via most market‑data vendors or the CBOE website API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:vix-term-structure-slope-vix1d-minus-vix) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
