# Chef Inbox — Auto Fibonacci Retracement Levels by Zeiierman – automatically draws F

**Routed by:** Gamma_Prospector 2026-08-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Auto Fibonacci Retracement Levels by Zeiierman – automatically draws Fibonacci retracement bands based on the most recent swing high/low -- Identifies natural price‑ratio support/resistance zones that complement existing trend‑following tools. Data source: TradingView public script: 'Auto Fibonacci Retracement' by Zeiierman (https://www.tradingview.com/script/...). Cost: $0. Instrument fit: both.

## Research Question for Chef
Auto Fibonacci Retracement Levels by Zeiierman – automatically draws Fibonacci retracement bands based on the most recent swing high/low -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView public script: 'Auto Fibonacci Retracement' by Zeiierman (https://www.tradingview.com/script/...)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:auto-fibonacci-retracement-levels-by-zei) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
