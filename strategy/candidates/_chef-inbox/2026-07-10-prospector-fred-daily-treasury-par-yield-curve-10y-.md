# Chef Inbox — FRED Daily Treasury Par Yield Curve (10Y-2Y spread)

**Routed by:** Gamma_Prospector 2026-07-10
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:google/gemma-4-31b-it:free

## The Finding
Prospector beat `data_feeds_free` surfaced: FRED Daily Treasury Par Yield Curve (10Y-2Y spread) -- Identifies regime shifts in macro risk appetite that correlate with SPY trend persistence or reversals. Data source: Federal Reserve Economic Data (FRED) API. Cost: $0. Instrument fit: both.

## Research Question for Chef
FRED Daily Treasury Par Yield Curve (10Y-2Y spread) -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: Federal Reserve Economic Data (FRED) API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: data_feeds_free:fred-daily-treasury-par-yield-curve-10y-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
