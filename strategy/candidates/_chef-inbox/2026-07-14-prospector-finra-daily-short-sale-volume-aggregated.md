# Chef Inbox — FINRA daily short-sale volume aggregated by ticker

**Routed by:** Gamma_Prospector 2026-07-14
**Priority:** MED
**Category:** New data signal / exogenous idea
**Source:** swarm:nvidia/nemotron-3-super-120b-a12b:free

## The Finding
Prospector beat `microstructure_internals` surfaced: FINRA daily short-sale volume aggregated by ticker -- Elevated short-sale volume in SPY constituents predicts near-term downward pressure, useful for biasing 0DTE put/call skew and futures direction. Data source: FINRA Short Sale Volume files, downloadable free from FINRA website (https://www.finra.org/filing-reporting/short-sale-volume). Cost: $0. Instrument fit: both.

## Research Question for Chef
FINRA daily short-sale volume aggregated by ticker -- this carries a testable directional/timing edge for both.

## Backtest Request
Data: FINRA Short Sale Volume files, downloadable free from FINRA website (https://www.finra.org/filing-reporting/short-sale-volume)
Null hypothesis: the signal has no measurable effect on entry/exit quality vs the existing engine baseline over the same days.
Pass bar: OOS positive AND walk-forward >= 0.70 AND sub-window stable AND anchor-day no-regression (the standing OP-11/OP-16 autoresearch bar) before any wiring proposal reaches conductor-proposals.jsonl.

## Files for Reference
analysis/prospector/ideas-ledger.jsonl (dedupe_key: microstructure_internals:finra-daily-short-sale-volume-aggregated) · markdown/infra/PROSPECTOR-SPEC.md

## Priority / Dependencies
depends:none
