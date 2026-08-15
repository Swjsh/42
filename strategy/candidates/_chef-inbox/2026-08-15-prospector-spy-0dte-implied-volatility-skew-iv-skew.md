# Chef Inbox — SPY 0DTE Implied Volatility Skew (IV Skew) using the 25‑Delta Call vs 

**Routed by:** Gamma_Prospector 2026-08-15
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Implied Volatility Skew (IV Skew) using the 25‑Delta Call vs 25‑Delta Put spread -- Skew captures market bias toward upside or downside moves; extreme skew often precedes sharp directional spikes in the underlying. Data source: OptionMetrics US Equity Options Database (historical IV surface) – paid subscription. Cost: paid. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Implied Volatility Skew (IV Skew) using the 25‑Delta Call vs 25‑Delta Put spread -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: OptionMetrics US Equity Options Database (historical IV surface) – paid subscription
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-implied-volatility-skew-iv-skew) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
