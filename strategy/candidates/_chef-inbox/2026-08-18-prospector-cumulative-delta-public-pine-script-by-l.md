# Chef Inbox — Cumulative Delta public Pine script by LazyBear measuring buying vs se

**Routed by:** Gamma_Prospector 2026-08-18
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Cumulative Delta public Pine script by LazyBear measuring buying vs selling pressure -- Cumulative delta highlights order‑flow imbalances that often precede short‑term price moves. Data source: TradingView public script "Cumulative Delta" by LazyBear (https://www.tradingview.com/script/...). Cost: $0. Instrument fit: both.

## Research Question for Chef
Cumulative Delta public Pine script by LazyBear measuring buying vs selling pressure -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView public script "Cumulative Delta" by LazyBear (https://www.tradingview.com/script/...)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:cumulative-delta-public-pine-script-by-l) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
