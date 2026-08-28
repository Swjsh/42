# Chef Inbox — SPY 0DTE Vanna Exposure aggregated from OCC open interest

**Routed by:** Gamma_Prospector 2026-08-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Vanna Exposure aggregated from OCC open interest -- Captures volatility‑driven delta hedging pressure; spikes in Vanna often precede sharp moves when IV changes. Data source: OCC daily options open interest files (free) combined with CBOE volatility surface data. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Vanna Exposure aggregated from OCC open interest -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: OCC daily options open interest files (free) combined with CBOE volatility surface data
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-vanna-exposure-aggregated-from-) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
