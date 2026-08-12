# Chef Inbox — US Dollar Index (DXY) strength/weakness as a cross‑asset directional c

**Routed by:** Gamma_Prospector 2026-08-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `cross_asset_signals` surfaced: US Dollar Index (DXY) strength/weakness as a cross‑asset directional cue -- A strong dollar typically suppresses US equity prices, whereas dollar weakness supports SPY and MES/MNQ upside moves. Data source: ICE Data Services ticker DX (US Dollar Index) – available through Bloomberg or ICE Direct. Cost: paid. Instrument fit: both.

## Research Question for Chef
US Dollar Index (DXY) strength/weakness as a cross‑asset directional cue -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: ICE Data Services ticker DX (US Dollar Index) – available through Bloomberg or ICE Direct
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: cross_asset_signals:us-dollar-index-dxy-strengthweakness-as-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
