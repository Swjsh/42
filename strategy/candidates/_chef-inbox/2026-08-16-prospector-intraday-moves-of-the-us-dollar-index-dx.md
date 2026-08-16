# Chef Inbox — Intraday moves of the US Dollar Index (DXY) inversely correlated with 

**Routed by:** Gamma_Prospector 2026-08-16
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `cross_asset_signals` surfaced: Intraday moves of the US Dollar Index (DXY) inversely correlated with equity index futures -- A rising DXY signals dollar strength and risk‑off sentiment, often dragging SPY/MES lower; a falling DXY supports risk‑on and upward moves. Data source: ICE Futures US DXY ticker DX.Y.NYB, available free via Yahoo Finance (^DXJ) or most data vendors. Cost: $0. Instrument fit: both.

## Research Question for Chef
Intraday moves of the US Dollar Index (DXY) inversely correlated with equity index futures -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE Futures US DXY ticker DX.Y.NYB, available free via Yahoo Finance (^DXJ) or most data vendors.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:intraday-moves-of-the-us-dollar-index-dx) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
