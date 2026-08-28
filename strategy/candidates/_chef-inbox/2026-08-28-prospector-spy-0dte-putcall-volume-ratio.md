# Chef Inbox — SPY 0DTE Put/Call Volume Ratio

**Routed by:** Gamma_Prospector 2026-08-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Put/Call Volume Ratio -- Measures same-day bullish vs bearish pressure in 0DTE options, often preceding intraday reversals or continuations. Data source: CBOE Equity Options Volume CSV (free download) or CBOE DataShop API. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Put/Call Volume Ratio -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Equity Options Volume CSV (free download) or CBOE DataShop API
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-putcall-volume-ratio) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
