# Chef Inbox — ICE Dollar Index (DXY) relative strength

**Routed by:** Gamma_Prospector 2026-08-21
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: ICE Dollar Index (DXY) relative strength -- A stronger dollar typically depresses equity valuations and commodity‑linked futures, giving directional bias for SPY 0DTE and MES/MNQ. Data source: ICE DXY ticker, free via Yahoo Finance API or paid via Bloomberg. Cost: $0. Instrument fit: both.

## Research Question for Chef
ICE Dollar Index (DXY) relative strength -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE DXY ticker, free via Yahoo Finance API or paid via Bloomberg
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:ice-dollar-index-dxy-relative-strength) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
