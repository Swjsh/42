# Chef Inbox — Anchored VWAP (AVWAP) – computes volume-weighted average price from a 

**Routed by:** Gamma_Prospector 2026-09-12
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `tv_community_indicators` surfaced: Anchored VWAP (AVWAP) – computes volume-weighted average price from a user-selected anchor point (e.g., session open, swing high/low) -- Provides a dynamic fair value benchmark; price tends to revert to AVWAP, offering intraday support/resistance for 0DTE options and futures. Data source: TradingView community script 'Anchored VWAP' by Alex Grover (Public Pine Script). Cost: $0. Instrument fit: both.

## Research Question for Chef
Anchored VWAP (AVWAP) – computes volume-weighted average price from a user-selected anchor point (e.g., session open, swing high/low) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: TradingView community script 'Anchored VWAP' by Alex Grover (Public Pine Script).
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: tv_community_indicators:anchored-vwap-avwap-computes-volume-weig) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
