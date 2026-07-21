# Chef Inbox — Market Profile (TPO) built-in indicator – plots time-price opportuniti

**Routed by:** Gamma_Prospector 2026-07-11
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Market Profile (TPO) built-in indicator – plots time-price opportunities to show value area, point of control, and initial balance -- Reveals auction market structure, highlighting where price spends most time and where it is likely to revert. Data source: TradingView built-in Market Profile indicator (Indicators → Market Profile). Cost: $0. Instrument fit: both.

## Research Question for Chef
Market Profile (TPO) built-in indicator – plots time-price opportunities to show value area, point of control, and initial balance -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView built-in Market Profile indicator (Indicators → Market Profile).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:market-profile-tpo-built-in-indicator-pl) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
