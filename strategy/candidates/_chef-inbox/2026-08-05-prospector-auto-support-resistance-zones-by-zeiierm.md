# Chef Inbox — Auto Support & Resistance Zones by Zeiierman (public Pine Script) – au

**Routed by:** Gamma_Prospector 2026-08-05
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Auto Support & Resistance Zones by Zeiierman (public Pine Script) – automatically draws S/R zones based on recent swing highs/lows and volume clustering -- Provides adaptive, structure-based levels that update with market context, complementing static trendlines and improving entry/exit timing. Data source: TradingView price data (high/low/close) and volume. Cost: $0. Instrument fit: both.

## Research Question for Chef
Auto Support & Resistance Zones by Zeiierman (public Pine Script) – automatically draws S/R zones based on recent swing highs/lows and volume clustering -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView price data (high/low/close) and volume.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:auto-support-resistance-zones-by-zeiierm) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
