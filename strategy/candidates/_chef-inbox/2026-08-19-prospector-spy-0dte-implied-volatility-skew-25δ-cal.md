# Chef Inbox — SPY 0DTE Implied Volatility Skew (25Δ Call vs 25Δ Put)

**Routed by:** Gamma_Prospector 2026-08-19
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Implied Volatility Skew (25Δ Call vs 25Δ Put) -- A steep skew indicates asymmetric demand for protection and can reveal hidden directional pressure that standard IV misses. Data source: CBOE Options Chain data for SPY (LiveVol or CBOE Market Data Platform). Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Implied Volatility Skew (25Δ Call vs 25Δ Put) -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Options Chain data for SPY (LiveVol or CBOE Market Data Platform)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-implied-volatility-skew-25δ-cal) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
