# Chef Inbox — SPY 0DTE Max Pain Level derived from daily open interest across all st

**Routed by:** Gamma_Prospector 2026-08-15
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:cerebras:gpt-oss-120b

## The Finding
Prospector beat `options_structure_metrics` surfaced: SPY 0DTE Max Pain Level derived from daily open interest across all strikes -- The strike where total option holder loss is minimized (max pain) tends to attract price gravitation, especially in short‑dated contracts. Data source: CBOE Open Interest CSV files (https://www.cboe.com/delayed-data/oi) – free download. Cost: $0. Instrument fit: 0dte.

## Research Question for Chef
SPY 0DTE Max Pain Level derived from daily open interest across all strikes -- this carries a testable directional/timing edge for 0dte.

## Backtest Request
Data: CBOE Open Interest CSV files (https://www.cboe.com/delayed-data/oi) – free download
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: options_structure_metrics:spy-0dte-max-pain-level-derived-from-dai) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
