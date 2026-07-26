# Chef Inbox — Intraday moves in the US Dollar Index (DXY)

**Routed by:** Gamma_Prospector 2026-07-25
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: Intraday moves in the US Dollar Index (DXY) -- A sharp DXY rise often correlates with risk‑off sentiment and short‑term weakness in SPY/MES, while a fall supports rallies. Data source: ICE US Dollar Index (ticker ^DXY or DX.Y.N), available free from most data feeds. Cost: $0. Instrument fit: both.

## Research Question for Chef
Intraday moves in the US Dollar Index (DXY) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE US Dollar Index (ticker ^DXY or DX.Y.N), available free from most data feeds
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:intraday-moves-in-the-us-dollar-index-dx) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
