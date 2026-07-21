# Chef Inbox — Auto Support & Resistance Zones (community script by Zeiierman) – auto

**Routed by:** Gamma_Prospector 2026-07-11
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Auto Support & Resistance Zones (community script by Zeiierman) – automatically draws dynamic S/R zones based on swing high/low clustering -- Adapts to changing volatility, providing zones that capture institutional order clusters missed by static trendlines. Data source: TradingView public Pine script 'Auto Support & Resistance' by Zeiierman (https://www.tradingview.com/script/...). Cost: $0. Instrument fit: both.

## Research Question for Chef
Auto Support & Resistance Zones (community script by Zeiierman) – automatically draws dynamic S/R zones based on swing high/low clustering -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView public Pine script 'Auto Support & Resistance' by Zeiierman (https://www.tradingview.com/script/...).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:auto-support-resistance-zones-community-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
