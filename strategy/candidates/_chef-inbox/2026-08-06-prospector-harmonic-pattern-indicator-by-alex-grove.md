# Chef Inbox — Harmonic Pattern Indicator by Alex Grover (public Pine Script) – detec

**Routed by:** Gamma_Prospector 2026-08-06
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Harmonic Pattern Indicator by Alex Grover (public Pine Script) – detects Gartley, Butterfly, Bat, Crab patterns and projects Potential Reversal Zones (PRZ) -- Identifies geometric price ratios that historically precede reversals, offering high-probability entry points for short-term trades. Data source: TradingView price data (OHLC) used to calculate pattern ratios. Cost: $0. Instrument fit: both.

## Research Question for Chef
Harmonic Pattern Indicator by Alex Grover (public Pine Script) – detects Gartley, Butterfly, Bat, Crab patterns and projects Potential Reversal Zones (PRZ) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView price data (OHLC) used to calculate pattern ratios.
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:harmonic-pattern-indicator-by-alex-grove) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
