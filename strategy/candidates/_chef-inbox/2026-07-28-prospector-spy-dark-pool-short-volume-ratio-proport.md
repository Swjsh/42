# Chef Inbox — SPY Dark Pool Short Volume Ratio – proportion of short sales executed 

**Routed by:** Gamma_Prospector 2026-07-28
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY Dark Pool Short Volume Ratio – proportion of short sales executed in dark pools relative to total volume -- Elevated dark‑pool shorting often precedes downward pressure, offering a short‑term bearish edge for 0DTE options. Data source: FINRA Short Volume File (daily) for ticker SPY, freely downloadable from FINRA website; ratio = short volume / total volume. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY Dark Pool Short Volume Ratio – proportion of short sales executed in dark pools relative to total volume -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: FINRA Short Volume File (daily) for ticker SPY, freely downloadable from FINRA website; ratio = short volume / total volume
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-dark-pool-short-volume-ratio-proport) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
